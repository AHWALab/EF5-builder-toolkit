"""KW inference using the supplied Python models; no model training."""
from contextlib import ExitStack
from pathlib import Path
from importlib.resources import files
import pickle
import re
import warnings
from tempfile import TemporaryDirectory

import numpy as np
from pandas import DataFrame
import rasterio
from rasterio.windows import Window

NODATA = -9999.0


def _windows(src, size=512):
    for row in range(0, src.height, size):
        for col in range(0, src.width, size):
            yield Window(col, row, min(size, src.width-col), min(size, src.height-row))


def _sources(stack, paths):
    sources = [stack.enter_context(rasterio.open(p)) for p in paths]
    ref = sources[0]
    for src in sources:
        if src.count != 1 or src.crs is None:
            raise ValueError(f'Expected a single-band raster with CRS: {src.name}')
        if (src.shape != ref.shape or src.crs != ref.crs
                or src.transform != ref.transform):
            raise ValueError(f'Input grids must already be aligned: {src.name}')
    return sources


def _profile(src):
    profile = src.profile.copy()
    profile.pop('blockxsize', None)
    profile.pop('blockysize', None)
    profile.update(driver='GTiff', count=1, dtype='float32', nodata=NODATA,
                   tiled=False, interleave="pixel", compress='deflate', BIGTIFF='IF_SAFER')
    return profile


def _read(src, window):
    a = src.read(1, window=window, masked=True).astype('float64')
    return a.data, ~np.ma.getmaskarray(a) & np.isfinite(a.data)


def _check_self_fam(self_fam):
    if not isinstance(self_fam, (bool, np.bool_)):
        raise ValueError('self_fam must be explicitly True or False, matching EF5 SELFFAM.')


def _check_fac(data, valid, self_fam):
    if np.any(valid & (data < int(self_fam))):
        raise ValueError(f'Valid FAC values must be >= {int(self_fam)} for self_fam={self_fam}. '
                         'Check SELFFAM and the raster NoData definition.')


def _outputs(paths, inputs, overwrite):
    resolved = [p.resolve() for p in paths]
    if len(set(resolved)) != len(resolved):
        raise ValueError('Output filenames must be unique.')
    for path in paths:
        if path.resolve() in {Path(p).resolve() for p in inputs}:
            raise ValueError(f'Output would replace an input: {path}')
        if path.exists() and not overwrite:
            raise FileExistsError(f'{path} exists; use overwrite=True.')


def get_kw_parameters(basin_area, temperature, precipitation, relief_ratio,
                      flow_accumulation, output_dir, *, model_dir=None,
                      layer_th=2, self_fam, precipitation_units=None,
                      precipitation_factor=None, overwrite=False):
    """Write alpha/beta and return their paths and prediction threshold.

    Area is in km², temperature in °C, relief ratio dimensionless. The
    precipitation_units selects conversion to inches/month: in or in/year
    divides by 12; mm or mm/year divides by 25.4 and 12; in/month is
    unchanged; mm/month divides by 25.4. Bare in and mm mean annual totals
    by API convention. Alternatively, pass the legacy precipitation_factor
    explicitly; it cannot be combined with precipitation_units.
    FAC and both thresholds are counts of contributing grid cells.
    self_fam must explicitly match EF5 SELFFAM: True includes the current
    cell (minimum 1); False excludes it (minimum 0). FAC is not converted.
    Predictions use FAC > layer_th (default 2). Control-file TH must exceed it.
    Bundled models are found automatically, independently of the working directory.
    Optional model_dir overrides them with trusted scaler.p, alpha_model.p, beta_model.p.
    Pickle loading executes code: never use untrusted model files.
    """
    _check_self_fam(self_fam)
    if not np.isfinite(layer_th) or layer_th < 0:
        raise ValueError('layer_th must be finite and nonnegative in FAC units.')
    if precipitation_units is not None:
        if precipitation_factor is not None:
            raise ValueError('Supply precipitation_units or precipitation_factor, not both.')
        factors = {'in': 1/12, 'in/year': 1/12, 'in/month': 1.,
                   'mm': 1/(25.4*12), 'mm/year': 1/(25.4*12), 'mm/month': 1/25.4}
        if precipitation_units not in factors:
            raise ValueError(f'Unsupported precipitation_units: {precipitation_units!r}. '
                             f'Choose from {tuple(factors)}.')
        precipitation_factor = factors[precipitation_units]
    if precipitation_factor is None:
        raise ValueError('Supply precipitation_units or precipitation_factor explicitly.')
    if not np.isfinite(precipitation_factor) or precipitation_factor <= 0:
        raise ValueError('precipitation_factor must be finite and positive.')
    warnings.warn(f'Selected layer TH is {layer_th}. TH in the EF5 control-file '
                  'KW parameter block must be strictly greater than this value.',
                  UserWarning, stacklevel=2)
    model_dir = (files("ef5_builder").joinpath("models").joinpath("kw")
                 if model_dir is None else Path(model_dir))
    output_dir = Path(output_dir)
    models = []
    for name in ('scaler.p', 'alpha_model.p', 'beta_model.p'):
        with (model_dir / name).open('rb') as stream:
            models.append(pickle.load(stream, encoding='latin1'))
    scaler, alpha_model, beta_model = models
    inputs = [basin_area, temperature, precipitation, relief_ratio, flow_accumulation]
    outputs = [output_dir / 'kw_alpha.tif', output_dir / 'kw_beta.tif']
    _outputs(outputs, inputs, overwrite)
    with ExitStack() as stack:
        sources = _sources(stack, inputs)
        output_dir.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix='.ef5-kw-', dir=output_dir) as temp:
            staged = [Path(temp) / p.name for p in outputs]
            with ExitStack() as writers:
                dsts = [writers.enter_context(rasterio.open(p, 'w', **_profile(sources[0])))
                        for p in staged]
                for dst in dsts:
                    dst.update_tags(layer_th=str(layer_th), control_th_requirement="strictly greater than layer_th",
                                    self_fam=str(bool(self_fam)).lower(), fac_units='grid cells',
                                    precipitation_factor=str(precipitation_factor),
                                    precipitation_input_units=precipitation_units or 'unspecified',
                                    precipitation_conversion_target='in/month' if precipitation_units else 'unspecified')
                for window in _windows(sources[0]):
                    arrays = [_read(s, window) for s in sources]
                    area, temp_c, precip, rr, fac = [a for a, _ in arrays]
                    _check_fac(fac, arrays[-1][1], self_fam)
                    valid = np.logical_and.reduce([m for _, m in arrays])
                    valid &= (area > 0) & (precip >= 0) & (rr >= 0) & (fac > layer_th)
                    alpha = np.full(area.shape, NODATA, dtype='float32')
                    beta = alpha.copy()
                    if valid.any():
                        x = np.column_stack((np.log10(area[valid]), temp_c[valid],
                                             precip[valid]*precipitation_factor, rr[valid]))
                        if hasattr(scaler, 'feature_names_in_'):
                            x = DataFrame(x, columns=scaler.feature_names_in_)
                        x = scaler.transform(x)
                        with np.errstate(over='ignore', under='ignore'):
                            a = np.power(10., alpha_model.predict(x))
                            b = beta_model.predict(x)
                            negative = b < 0
                            b[negative] = np.exp(b[negative]*10.)
                        good_a = np.isfinite(a) & (a > 0) & (a <= 1000)
                        good_b = np.isfinite(b) & (b > 0) & (b <= np.finfo('float32').max)
                        alpha[valid] = np.where(good_a, a, NODATA)
                        beta[valid] = np.where(good_b, b, NODATA)
                    for dst, data in zip(dsts, (alpha, beta)):
                        dst.write(data, 1, window=window)
            for staged_path, output in zip(staged, outputs):
                staged_path.replace(output)
    return {'alpha': outputs[0], 'beta': outputs[1], 'layer_th': layer_th,
            'th': layer_th, 'self_fam': bool(self_fam)}


def _alpha0_filename(manning):
    years = set(re.findall(r'(?<!\d)((?:19|20)\d{2})(?!\d)', Path(manning).stem))
    if len(years) > 1:
        raise ValueError(f'Manning filename contains multiple years: {manning}')
    suffix = f'_{years.pop()}' if years else ''
    return f'kw_alpha0{suffix}.tif'


def get_kw_alpha0(manning, slope, flow_accumulation, output_dir, *, self_fam, overwrite=False):
    """Write one alpha0 per Manning raster; return {input Path: output Path}.

    manning accepts one path or a sequence of paths (e.g. annual layers).
    Outputs use kw_alpha0_YEAR.tif when the filename contains a year
    (1900-2099), or kw_alpha0.tif otherwise. Output names must be unique.
    All rasters must be aligned. Manning n: s m^-1/3; slope: m/m.
    Uses (n/sqrt(slope))**(3/5); retains legacy clipping behavior.
    Preserves its global clipping rule: values >=1000 become the maximum
    valid value below 1000 for that layer. self_fam explicitly specifies
    whether FAC includes the current cell (EF5 SELFFAM); no conversion occurs.
    Zero slope has an infinite raw result and follows that clipping rule.
    Missing/nonfinite inputs, n<=0 and slope<0 become NoData.
    """
    _check_self_fam(self_fam)
    paths = [Path(manning)] if isinstance(manning, (str, Path)) else [Path(p) for p in manning]
    if not paths:
        raise ValueError('Provide at least one Manning raster.')
    if len({p.resolve() for p in paths}) != len(paths):
        raise ValueError('Manning inputs must be unique.')
    output_dir = Path(output_dir)
    outputs = [output_dir / _alpha0_filename(p) for p in paths]
    _outputs(outputs, [*paths, slope, flow_accumulation], overwrite)
    # Validate every grid before producing any annual output.
    with ExitStack() as stack:
        _sources(stack, [slope, flow_accumulation, *paths])
    output_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix='.ef5-alpha0-', dir=output_dir) as temp:
        staged = []
        for path, output in zip(paths, outputs):
            target = Path(temp) / output.name
            with ExitStack() as stack:
                n_src, s_src, f_src = _sources(stack, [path, slope, flow_accumulation])
                maximum = None
                with rasterio.open(target, 'w', **_profile(n_src)) as dst:
                    dst.update_tags(equation='(n / sqrt(slope)) ** (3/5)',
                                    self_fam=str(bool(self_fam)).lower(), fac_units='grid cells',
                                    equation_status='selected EF5 Global Parameters formulation; legacy clipping',
                                    manning_source=str(path))
                    for window in _windows(n_src):
                        n, nv = _read(n_src, window)
                        s, sv = _read(s_src, window)
                        fac, fv = _read(f_src, window)
                        _check_fac(fac, fv, self_fam)
                        valid = nv & sv & fv & (n > 0) & (s >= 0) & (fac >= 0)
                        data = np.full(n.shape, NODATA, dtype='float64')
                        with np.errstate(divide='ignore', over='ignore'):
                            data[valid] = (n[valid]/np.sqrt(s[valid]))**(3/5)
                        below = valid & (data < 1000)
                        if below.any():
                            value = float(data[below].max())
                            maximum = value if maximum is None else max(maximum, value)
                        # A finite sentinel avoids writing infinities to GeoTIFF.
                        data[valid & (data >= 1000)] = np.finfo('float32').max
                        dst.write(data.astype('float32'), 1, window=window)
                if maximum is None:
                    raise ValueError(f'No valid alpha0 below 1000 for notebook clipping: {path}')
                with rasterio.open(target, 'r+') as dst:
                    for window in _windows(dst):
                        data = dst.read(1, window=window)
                        data[data == np.finfo('float32').max] = maximum
                        dst.write(data, 1, window=window)
            staged.append(target)
        for target, output in zip(staged, outputs):
            target.replace(output)
    return dict(zip(paths, outputs))


def get_kw_alpha0_from_dem(manning, dem, output_dir, *, min_slope=None,
                           overwrite=False):
    """Calculate ALPHA0 from aligned Manning n and a north-up DEM in metres.

    Horn 3x3 slope uses projected CRS linear units converted to metres, or
    ellipsoidal geodesic distances for geographic CRSs. All nine elevations
    must be valid; outer edges are NoData. No resampling is performed.
    min_slope=None masks zero slopes. An explicit positive floor replaces
    smaller valid slopes, including zero, and changes flat-terrain ALPHA0.
    Manning n must be in s m^-1/3. Returns the output Path. No clipping to
    1000 is applied; nonrepresentable Float32 results become NoData.
    Output is kw_alpha0_YEAR.tif when the Manning filename contains a year
    (1900-2099), or kw_alpha0.tif otherwise.
    """
    from pyproj import CRS

    if min_slope is not None and (isinstance(min_slope, bool)
            or not np.isfinite(min_slope) or min_slope <= 0):
        raise ValueError('min_slope must be None or a finite positive value in m/m.')
    output_dir = Path(output_dir)
    output = output_dir / _alpha0_filename(manning)
    _outputs([output], [manning, dem], overwrite)
    with ExitStack() as stack:
        dsrc, nsrc = _sources(stack, [dem, manning])
        t = dsrc.transform
        if t.b or t.d or t.a <= 0 or t.e >= 0:
            raise ValueError('DEM must use a north-up, unrotated grid.')
        crs = CRS.from_user_input(dsrc.crs)
        if not (crs.is_projected or crs.is_geographic):
            raise ValueError('DEM requires a projected or geographic CRS.')
        if crs.is_geographic:
            if any(abs(a.unit_conversion_factor - np.pi/180) > 1e-12
                   for a in crs.axis_info[:2]):
                raise ValueError('Geographic CRS must use degree coordinates.')
            geod = crs.get_geod()
        else:
            factors = [a.unit_conversion_factor for a in crs.axis_info[:2]]
            if len(factors) != 2 or not np.all(np.isfinite(factors)):
                raise ValueError('Projected CRS must define horizontal linear units.')
        output_dir.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix='.ef5-alpha0-dem-', dir=output_dir) as temp:
            staged = Path(temp) / output.name
            with rasterio.open(staged, 'w', **_profile(dsrc)) as dst:
                dst.update_tags(equation='(n / sqrt(slope)) ** (3/5)',
                                units='s^0.6 m^-0.2', manning_units='s m^-1/3',
                                dem_vertical_units='m', slope_units='m/m',
                                slope_method='Horn 3x3', min_slope=str(min_slope),
                                dem_source=str(dem), manning_source=str(manning))
                for window in _windows(dsrc):
                    # A one-cell halo prevents artificial seams between windows.
                    halo = Window(window.col_off-1, window.row_off-1,
                                  window.width+2, window.height+2)
                    z = dsrc.read(1, window=halo, boundless=True,
                                  masked=True, out_dtype='float64')
                    valid_z = ~np.ma.getmaskarray(z) & np.isfinite(z.data)
                    h, w = int(window.height), int(window.width)
                    cells = [z.data[i:i+h, j:j+w] for i in range(3) for j in range(3)]
                    valid = np.logical_and.reduce([
                        valid_z[i:i+h, j:j+w] for i in range(3) for j in range(3)])
                    a,b,c,d,_,f,g,hz,i = cells
                    if crs.is_geographic:
                        rows = np.arange(window.row_off, window.row_off+window.height)
                        lat = t.f + (rows+.5)*t.e
                        lon = np.full(lat.shape, t.c+(window.col_off+.5)*t.a)
                        _,_,dx = geod.inv(lon-t.a, lat, lon+t.a, lat)
                        _,_,dy = geod.inv(lon, lat-t.e, lon, lat+t.e)
                        dx,dy = np.asarray(dx)[:,None]/2, np.asarray(dy)[:,None]/2
                    else:
                        dx,dy = t.a*factors[0], -t.e*factors[1]
                    with np.errstate(invalid='ignore', divide='ignore', over='ignore'):
                        slope = np.hypot((c+2*f+i-a-2*d-g)/(8*dx),
                                         (g+2*hz+i-a-2*b-c)/(8*dy))
                    n,nv = _read(nsrc, window)
                    valid &= nv & (n > 0) & np.isfinite(slope) & (slope >= 0)
                    if min_slope is None:
                        valid &= slope > 0
                    else:
                        slope = np.maximum(slope, min_slope)
                    data = np.full(n.shape, NODATA, dtype='float32')
                    with np.errstate(over='ignore', divide='ignore', invalid='ignore'):
                        values = (n[valid]/np.sqrt(slope[valid]))**.6
                    good = np.isfinite(values) & (values > 0) & (values <= np.finfo('float32').max)
                    converted = np.where(good, values, 0).astype('float32')
                    good &= converted > 0
                    data[valid] = np.where(good, converted, NODATA)
                    dst.write(data, 1, window=window)
            staged.replace(output)
    return output

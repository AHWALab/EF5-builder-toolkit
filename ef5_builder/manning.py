"""Annual overland Manning n from MCD12Q1.061 LC_Type2 exports.

Lookup is crosswalked by meaning, NOT by equal numeric codes, from Flamig
et al. (2020), Table 5: https://doi.org/10.5194/gmd-13-4943-2020.
C6.1 legend: https://lpdaac.usgs.gov/documents/1409/MCD12_User_Guide_V61.pdf
"""
from contextlib import ExitStack
import json
import fnmatch
from pathlib import Path
import re
from tempfile import TemporaryDirectory

import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.windows import Window

# LC_Type2 code: (C6.1 class, Table 5 class, Manning n).
# Woodland / wooded grassland in the older UMD legend correspond to the
# woody savanna / savanna tree-cover categories, respectively.
UMD_CROSSWALK = {
    0: ('Water', 0, .001),
    1: ('Evergreen needleleaf forest', 1, .1),
    2: ('Evergreen broadleaf forest', 2, .1),
    3: ('Deciduous needleleaf forest', 3, .1),
    4: ('Deciduous broadleaf forest', 4, .1),
    5: ('Mixed forest', 5, .1),
    6: ('Closed shrubland', 8, .3),
    7: ('Open shrubland', 9, .2),
    8: ('Woody savanna (woodland)', 6, .1),
    9: ('Savanna (wooded grassland)', 7, .3),
    10: ('Grassland', 10, .17),
    12: ('Cropland', 11, .035),
    13: ('Urban and built-up', 13, .015),
}
VALID_CODES = frozenset([*UMD_CROSSWALK, 15])
CLASS15_REFERENCE = "https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.6/developing-a-terrain-model-and-geospatial-layers/creating-land-cover-mannings-n-values-and-impervious-layers"
NODATA = -9999


def _year_pattern(template):
    if template is None:
        return None
    if (not isinstance(template, str) or template.count('YYYY') != 1
            or '/' in template or '\\' in template):
        raise ValueError('filename_template must be a filename glob containing exactly one YYYY token.')
    pattern = fnmatch.translate(template.replace('YYYY', 'EF5YEARPLACEHOLDER'))
    return re.compile(pattern.replace('EF5YEARPLACEHOLDER', r'(?P<year>\d{4})'))


def _year(path, pattern=None):
    if pattern is not None:
        return int(pattern.fullmatch(path.name).group('year'))
    # Acquisition year takes precedence over MODIS production timestamps.
    modis = re.findall(r'A(\d{4})\d{3}(?!\d)', path.stem)
    found = modis or re.findall(r'(?<![A-Za-z0-9])(\d{4})(?:\d{4})?(?!\d)', path.stem)
    years = set(map(int, found))
    if len(years) != 1 or not all(1000 <= y <= 9999 for y in years):
        raise ValueError(f'Filename must identify one unambiguous four-digit year: {path.name}; '
                         'use filename_template with YYYY for custom names.')
    return years.pop()


def _codes(src, window):
    values = src.read(1, window=window, masked=True)
    data = values.data
    valid = ~np.ma.getmaskarray(values) & (data != 255)
    unexpected = np.unique(data[valid & ~np.isin(data, list(VALID_CODES))])
    if unexpected.size:
        raise ValueError(f'Unexpected LC_Type2 codes in {src.name}: {unexpected.tolist()}. '
                         'C6.1 excludes classes 11 and 14; 255 is fill.')
    return np.where(valid, data, 255).astype('uint8')


def annual_manning_from_modis(input_dir, output_dir, *, years=None, file_pattern="*", filename_template=None, class15_n=0.025, overwrite=False):
    """Convert single-band EPSG:4326 LC_Type2 GeoTIFFs into annual mosaics.

    Finds .tif/.tiff files recursively, filtered by file_pattern (e.g.
    "MCD12Q1_UMD_*.tif" for a directory also containing other rasters).
    Extracts acquisition year from
    AYYYYDDD, isolated YYYY, or YYYYMMDD names. years optionally selects a
    subset; requested missing years raise an error. No dataset-year range is
    imposed. filename_template optionally specifies where to read YYYY,
    e.g. "MCD12Q1_UMD_YYYY_Global_*.tif"; * and ? are filename wildcards.
    Files not matching that template are skipped. Returns {year: Path}.
    Inputs must already share resolution and pixel alignment within each
    year; no resampling is performed. Identical overlap is accepted, fill
    pixels do not obscure valid tiles, and conflicting class overlaps fail.
    Unexpected codes fail. Class 15 (barren including snow/ice) uses
    class15_n=0.025, a user-selected provisional value pending research,
    NOT a Flamig Table 5 value. Override class15_n when research is updated.
    User-provided reference for this provisional choice:
    https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.6/developing-a-terrain-model-and-geospatial-layers/creating-land-cover-mannings-n-values-and-impervious-layers
    The HEC page describes land-cover roughness assignment, not a verified
    MODIS LC_Type2 class-15 coefficient.
    Unclassified 255 and input masks become -9999. Water (0) is valid.
    Coefficients are assigned directly in s m^-1/3; no unit scaling is applied.
    Output: manning_n_YYYY.tif, float32, striped Deflate, native export grid.
    Alignment to the model DEM is a separate resample_and_subset operation.
    Processing is blockwise, and each annual output is written atomically.
    Files must actually contain LC_Type2; values alone cannot identify a
    classification when export metadata is absent. No missing years are made.
    """
    if (isinstance(class15_n, (bool, str)) or not np.isscalar(class15_n)
            or not np.isreal(class15_n) or not np.isfinite(class15_n)
            or class15_n <= 0 or class15_n > np.finfo('float32').max):
        raise ValueError('class15_n must be a positive finite float32-compatible coefficient.')
    year_pattern = _year_pattern(filename_template)
    input_dir = Path(input_dir).resolve()
    output_dir = Path(output_dir).resolve()
    if not input_dir.is_dir():
        raise NotADirectoryError(input_dir)
    groups = {}
    for path in sorted(input_dir.rglob(file_pattern)):
        if path.is_file() and path.suffix.lower() in ('.tif', '.tiff'):
            if year_pattern is not None and not year_pattern.fullmatch(path.name):
                continue
            if path.is_relative_to(output_dir):
                raise ValueError('Output directory must not contain input rasters.')
            groups.setdefault(_year(path, year_pattern), []).append(path)
    if not groups:
        raise ValueError('No annual GeoTIFF files found.')
    if years is not None:
        requested = tuple(years)
        if not requested or any(not isinstance(y, (int, np.integer)) or isinstance(y, bool)
                                or not 1000 <= y <= 9999 for y in requested):
            raise ValueError('years must be a nonempty sequence of four-digit integer years.')
        missing = set(requested) - groups.keys()
        if missing:
            raise ValueError(f'Missing annual files: {sorted(missing)}')
        groups = {y: groups[y] for y in sorted(set(requested))}
    outputs = {y: output_dir / f'manning_n_{y}.tif' for y in sorted(groups)}
    for path in outputs.values():
        if path.exists() and not overwrite:
            raise FileExistsError(f'{path} exists; use overwrite=True.')
    for year in sorted(groups):
        with ExitStack() as stack:
            sources = [stack.enter_context(rasterio.open(p)) for p in groups[year]]
            ref = sources[0]
            for src in sources:
                t = src.transform
                if src.count != 1 or src.crs is None or src.crs.to_epsg() != 4326:
                    raise ValueError(f'Expected single-band EPSG:4326 LC_Type2: {src.name}')
                if t.b or t.d or t.a <= 0 or t.e >= 0:
                    raise ValueError(f'Expected north-up unrotated grid: {src.name}')
                if not np.allclose((t.a, t.e), (ref.transform.a, ref.transform.e), rtol=1e-9, atol=0):
                    raise ValueError('Annual tiles must share pixel resolution.')
                if src.nodata in VALID_CODES:
                    raise ValueError(f'NoData {src.nodata} conflicts with a valid UMD class in {src.name}. '
                                     'Export with fill=255 to preserve water and land classes.')
                descriptions = ' '.join(d or '' for d in src.descriptions)
                if re.search(r'LC_Type[1345]', descriptions):
                    raise ValueError(f'Input band is not LC_Type2: {src.name}')
            offsets = []
            for src in sources:
                col, row = (~ref.transform) * (src.transform.c, src.transform.f)
                if abs(col-round(col)) > 1e-6 or abs(row-round(row)) > 1e-6:
                    raise ValueError('Annual tiles must align on the same pixel grid.')
                offsets.append((round(col), round(row)))
            left = min(x for x, _ in offsets); top = min(y for _, y in offsets)
            right = max(x+s.width for s, (x, _) in zip(sources, offsets))
            bottom = max(y+s.height for s, (_, y) in zip(sources, offsets))
            transform = ref.transform * Affine.translation(left, top)
            grid = dict(driver='GTiff', crs=ref.crs, transform=transform,
                        width=right-left, height=bottom-top, count=1,
                        tiled=False, interleave="pixel", compress='deflate', BIGTIFF='IF_SAFER')
            output_dir.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix='.ef5-manning-', dir=output_dir) as temp:
                temp = Path(temp)
                classes = temp / 'classes.tif'
                # Disk-backed class mosaic preserves overlap validation even
                # when two forest classes happen to have equal coefficients.
                with rasterio.open(classes, 'w+', **grid, dtype='uint8', nodata=255) as dst:
                    for _, window in dst.block_windows(1):
                        dst.write(np.full((int(window.height), int(window.width)), 255, dtype='uint8'), 1, window=window)
                    for src, (x, y) in zip(sources, offsets):
                        for _, window in src.block_windows(1):
                            data = _codes(src, window)
                            target = Window(x-left+window.col_off, y-top+window.row_off,
                                            window.width, window.height)
                            existing = dst.read(1, window=target)
                            both = (existing != 255) & (data != 255)
                            if np.any(both & (existing != data)):
                                raise ValueError(f'Conflicting overlapping tile classes for {year}: {src.name}')
                            dst.write(np.where(data != 255, data, existing), 1, window=target)
                lookup = np.full(256, NODATA, dtype='float32')
                for code, (_, _, coefficient) in UMD_CROSSWALK.items():
                    lookup[code] = coefficient
                lookup[15] = class15_n
                crosswalk = dict(UMD_CROSSWALK)
                crosswalk[15] = ('Barren including snow/ice; provisional', None, float(class15_n))
                staged = temp / 'manning.tif'
                with rasterio.open(classes) as src, rasterio.open(staged, 'w', **grid, dtype='float32', nodata=NODATA) as dst:
                    dst.update_tags(**ref.tags())
                    dst.update_tags(year=str(year), source_product='MCD12Q1.061', source_band='LC_Type2',
                                    source_files=json.dumps([p.name for p in groups[year]]),
                                    reference_doi='10.5194/gmd-13-4943-2020', reference_table='5',
                                    crosswalk=json.dumps(crosswalk), units='s m^-1/3',
                                    class15_n=str(float(class15_n)), class15_status='user-selected provisional',
                                    class15_reference=CLASS15_REFERENCE)
                    dst.set_band_description(1, "Annual overland Manning's n")
                    for _, window in src.block_windows(1):
                        dst.write(lookup[src.read(1, window=window)], 1, window=window)
                staged.replace(outputs[year])
    return outputs

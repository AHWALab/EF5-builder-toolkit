"""CREST soil parameter estimation from aligned SoilGrids 2017 inputs.

Equations, texture rules, and lookup values follow
OLD_Builder/4_Crest_parameters_estimation.ipynb. The legacy table is retained
as supplied; this module does not independently validate its scientific source.
"""
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory

import logging

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.windows import Window
from rasterio.features import geometry_mask
from shapely.geometry import box

SOIL_PARAMETERS = {
    1: {'eff_porosity': 0.417, 'hydraulic_cond': 11.78, 'b': 2.79},  # Sand
    2: {'eff_porosity': 0.401, 'hydraulic_cond': 2.99, 'b': 4.26},   # Loamy Sand
    3: {'eff_porosity': 0.412, 'hydraulic_cond': 1.09, 'b': 4.74},   # Sandy Loam
    4: {'eff_porosity': 0.4349, 'hydraulic_cond': 0.34, 'b': 5.25},  # Loam
    5: {'eff_porosity': 0.486, 'hydraulic_cond': 0.65, 'b': 5.33},   # Silt Loam
    6: {'eff_porosity': 0.330, 'hydraulic_cond': 0.15, 'b': 7.22},   # Silt
    7: {'eff_porosity': 0.330, 'hydraulic_cond': 0.15, 'b': 6.77},   # Sandy Clay Loam
    8: {'eff_porosity': 0.309, 'hydraulic_cond': 0.1, 'b': 8.17},    # Clay Loam
    9: {'eff_porosity': 0.432, 'hydraulic_cond': 0.1, 'b': 8.72},    # Silty Clay Loam
    10: {'eff_porosity': 0.321, 'hydraulic_cond': 0.06, 'b': 10.73}, # Sandy Clay
    11: {'eff_porosity': 0.423, 'hydraulic_cond': 0.05, 'b': 10.39}, # Silty Clay
    12: {'eff_porosity':  0.385, 'hydraulic_cond': 0.03, 'b': 11.55},# Clay
}

def _classify_soil_texture(mean_sand, mean_clay):
    """
    Classifies soil texture based on sand and clay percentages.
    The percentage of silt is calculated as 100 - (sand + clay).

    :param mean_sand: Array or value of sand percentage
    :param mean_clay: Array or value of clay percentage
    :return: Array with soil classification based on specified categories
    """

    #Calculate silt
    mean_silt = 100 - (mean_sand + mean_clay)

    # Ensure percentages sum to 100
    if np.any(mean_sand + mean_clay > 100):
        raise ValueError("Sand and clay percentages cannot exceed 100%.")

    # Create an array for classification
    texture_array = np.full_like(mean_sand, fill_value=np.nan, dtype=np.float32)

    # Classification
    texture_array[(mean_silt + 1.5 * mean_clay < 15)] = 1  # Sand
    texture_array[(mean_silt + 1.5 * mean_clay >= 15) & (mean_silt + 2 * mean_clay < 30)] = 2  # Loamy Sand
    texture_array[
        ((mean_clay >= 7) & (mean_clay < 20) & (mean_sand > 52) & (mean_silt + 2 * mean_clay >= 30)) |
        ((mean_clay < 7) & (mean_silt < 50) & (mean_silt + 2 * mean_clay >= 30))
    ] = 3  # Sandy Loam
    texture_array[(mean_clay >= 7) & (mean_clay < 27) & (mean_silt >= 28) & (mean_silt < 50) & (mean_sand <= 52)] = 4  # Loam
    texture_array[
        ((mean_silt >= 50) & (mean_clay >= 12) & (mean_clay < 27)) |
        ((mean_silt >= 50) & (mean_silt < 80) & (mean_clay < 12))
    ] = 5  # Silt Loam
    texture_array[(mean_silt >= 80) & (mean_clay < 12)] = 6  # Silt
    texture_array[(mean_clay >= 20) & (mean_clay < 35) & (mean_silt < 28) & (mean_sand > 45)] = 7  # Sandy Clay Loam
    texture_array[(mean_clay >= 27) & (mean_clay < 40) & (mean_sand > 20) & (mean_sand <= 45)] = 8  # Clay Loam
    texture_array[(mean_clay >= 27) & (mean_clay < 40) & (mean_sand <= 20)] = 9  # Silty Clay Loam
    texture_array[(mean_clay >= 35) & (mean_sand > 45)] = 10  # Sandy Clay
    texture_array[(mean_clay >= 40) & (mean_silt >= 40)] = 11  # Silty Clay
    texture_array[(mean_clay >= 40) & (mean_sand <= 45) & (mean_silt < 40)] = 12  # Clay

    return texture_array

def _prepare_lakes(lakes, crs):
    """Repair a copy of lake polygons and retain polygonal components."""
    frame = lakes.copy() if isinstance(lakes, gpd.GeoDataFrame) else gpd.read_file(lakes)
    if frame.crs is None or frame.empty:
        raise ValueError("Lakes must contain polygons with a defined CRS.")
    geometry = frame.geometry
    if geometry.isna().any() or geometry.is_empty.any():
        raise ValueError("Lakes contain missing or empty geometries.")
    if not geometry.geom_type.isin(["Polygon", "MultiPolygon"]).all():
        raise ValueError("Lakes must contain Polygon or MultiPolygon geometries.")
    frame = frame.to_crs(crs)
    invalid = ~frame.geometry.is_valid
    if invalid.any():
        logging.getLogger(__name__).warning("Repairing %d invalid lake geometries.", int(invalid.sum()))
        frame.geometry = frame.geometry.make_valid()
        while frame.geometry.geom_type.isin(["GeometryCollection", "MultiPolygon"]).any():
            frame = frame.explode(index_parts=False, ignore_index=True)
        polygons = frame.geometry.geom_type.eq("Polygon") & ~frame.geometry.is_empty
        discarded = int((~polygons).sum())
        if discarded:
            logging.getLogger(__name__).warning("Discarding %d non-polygon lake repair components.", discarded)
        frame = frame.loc[polygons].copy()
    if frame.empty or not frame.geometry.is_valid.all():
        raise ValueError("Lake repair did not produce valid polygons.")
    return frame


def _lake_mask(frame, index, ref, window, all_touched):
    shape = (int(window.height), int(window.width))
    selected = index.query(box(*ref.window_bounds(window)), predicate="intersects")
    if not len(selected):
        return np.zeros(shape, dtype=bool)
    return geometry_mask(frame.geometry.iloc[selected], out_shape=shape,
                         transform=ref.window_transform(window), invert=True,
                         all_touched=all_touched)


def _nearest_land_donors(sources, dem, frame, lake_index, all_touched):
    """Index original complete land boundary cells, not all domain pixels.

    A nearest complete cell to an incomplete cell must lie on the boundary
    of complete coverage. Retaining only these cells gives an exact nearest
    neighbor under the fixed raster-coordinate metric, with a smaller tree.
    """
    from scipy.spatial import cKDTree

    pieces = []
    for row in range(0, dem.height, 512):
        for col in range(0, dem.width, 512):
            height, width = min(512, dem.height-row), min(512, dem.width-col)
            top, left = max(0, row-1), max(0, col-1)
            bottom, right = min(dem.height, row+height+1), min(dem.width, col+width+1)
            window = Window(left, top, right-left, bottom-top)
            values = dem.read(1, window=window, masked=True)
            complete = ~np.ma.getmaskarray(values) & np.isfinite(values.data)
            complete &= ~_lake_mask(frame, lake_index, dem, window, all_touched)
            for index, src in enumerate(sources):
                values = src.read(1, window=window, masked=True)
                valid = ~np.ma.getmaskarray(values) & np.isfinite(values.data) & (values.data >= 0)
                if index < 14:
                    valid &= values.data <= 100
                complete &= valid
            padded = np.pad(complete, 1, constant_values=False)
            interior = complete.copy()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy or dx:
                        interior &= padded[1+dy:1+dy+complete.shape[0], 1+dx:1+dx+complete.shape[1]]
            core = (slice(row-top, row-top+height), slice(col-left, col-left+width))
            rr, cc = np.nonzero((complete & ~interior)[core])
            if len(rr):
                pieces.append(np.column_stack(((rr+row)*abs(dem.transform.e),
                                               (cc+col)*abs(dem.transform.a))))
    if not pieces:
        return None
    coordinates = np.concatenate(pieces)
    return cKDTree(coordinates)


def get_crest_parameters(input_dir, output_dir, *, dem=None, lakes=None,
                         all_touched=False, diagnostics_dir=None, overwrite=False):
    """Estimate Wm, Fc_Ksat, and b from 15 aligned SoilGrids 2017 rasters.

    Requires SNDPPT_M_sl1_250m.tif through sl7, CLYPPT_M_sl1_250m.tif
    through sl7 (percent), and BDRICM_M_250m.tif (centimetres). All must
    be single-band rasters on exactly the same north-up grid with a CRS.
    No reprojection or resampling is performed.

    Sand and clay are equal averages across all seven point depths, not
    thickness-weighted averages. Missing/nonfinite/out-of-range (0--100%)
    values in any texture layer mask all parameters at that pixel. Valid
    mean sand + mean clay greater than 100 raises ValueError, as in the
    original notebook. Negative/missing/nonfinite bedrock masks Wm only;
    nonnegative depths above 200 cm are accepted without clipping.

    With dem supplied, require its exact alignment and mask outputs to its
    finite, valid cells. Fill incomplete SoilGrids cells only when none of
    their eight neighbors is another incomplete cell inside the DEM and a
    neighbor has all 15 valid inputs. Also allow a coastal exception: an
    original complete neighbor inside the DEM faces a DEM-invalid neighbor
    on its opposite side. This exception can repair connected edge cells.
    Copy only invalid entries from the
    nearest complete original neighbor (distance in raster CRS coordinates;
    deterministic row/column order breaks ties). DEM-invalid neighbors are
    allowed but cannot donate. One pass only; gaps not meeting either rule remain unchanged.
    Valid existing entries are preserved. Out-of-range entries count as
    invalid. crest_filled_mask.tif records 0=unchanged, 1=isolated, 2=coastal, with
    NoData outside the DEM. It is written in diagnostics_dir (default: the sibling crest_diagnostics folder),
    separate from the three parameter outputs. Supply a distinct diagnostics_dir
    when multiple parameter sets share the same parent directory.
    Without dem, retain the original behavior without filling or a fill mask.

    Optional lakes (polygon path or GeoDataFrame with a CRS) require dem.
    Lake geometries are transformed to the raster CRS; invalid polygons are
    repaired on a copy with make_valid and non-polygon repair components are
    discarded with a warning. Pixel centers determine membership unless
    all_touched=True. Lake SoilGrids entries become NaN in memory before
    filling. Lake cells cannot be candidates or donors and all parameter
    outputs and the fill mask use NoData there. Sources are never modified.
    With lakes, fill every incomplete non-lake DEM cell from the nearest
    original non-lake donor with all 15 valid entries. Only invalid entries
    are replaced. Distances are Euclidean in raster CRS coordinates (angular
    for geographic grids), with no distance limit; equal-distance ties may
    choose any nearest donor. A spatial tree indexes boundary donor cells
    using an extra windowed input pass. Memory scales with boundary count,
    not the 15 full rasters. Raise if missing land exists but no donor exists.
    Fill-mask code 3 identifies these repairs. No lakes retains the previous
    isolated/coastal filling behavior.

    The original texture rules and table give Wm = eff_porosity * 10 *
    bedrock_cm (mm), Fc_Ksat = hydraulic_cond * 10 (legacy conversion),
    and b = table b. No imperviousness layer is calculated. The table's
    conductivity units are not documented in the source notebook.

    Returns absolute Paths keyed by 'wm', 'fc', and 'b'. Outputs are
    crest_Wm.tif, crest_Fc_Ksat.tif, crest_b.tif: striped, Deflate-compressed
    float32 GeoTIFFs with NoData=-9999. Processing uses 512 x 512 windows.
    Existing outputs require overwrite=True. All outputs are staged before
    replacement; each replacement is atomic, not the three-file set.
    """
    if lakes is not None and dem is None:
        raise ValueError("dem is required when lakes are supplied.")
    input_dir = Path(input_dir).resolve()
    output_dir = Path(output_dir).resolve()
    names = [f"{prefix}_M_sl{level}_250m.tif"
             for prefix in ("SNDPPT", "CLYPPT") for level in range(1, 8)]
    names.append("BDRICM_M_250m.tif")
    inputs = [input_dir / name for name in names]
    outputs = dict(zip(("wm", "fc", "b"),
                       (output_dir / name for name in
                        ("crest_Wm.tif", "crest_Fc_Ksat.tif", "crest_b.tif"))))
    diagnostics_dir = (Path(diagnostics_dir).resolve() if diagnostics_dir is not None
                       else output_dir.parent / "crest_diagnostics")
    if dem is not None and diagnostics_dir == output_dir:
        raise ValueError("diagnostics_dir must differ from the parameter output directory.")
    fill_output = diagnostics_dir / "crest_filled_mask.tif" if dem is not None else None
    protected_inputs = inputs + ([Path(dem).resolve()] if dem is not None else [])
    for path in inputs:
        if not path.is_file():
            raise FileNotFoundError(f"Required SoilGrids 2017 input not found: {path}")
    for path in [*outputs.values(), *([fill_output] if fill_output else [])]:
        if path in protected_inputs:
            raise ValueError("Outputs must not replace input rasters.")
        if path.exists() and not overwrite:
            raise FileExistsError(f"{path} already exists; use overwrite=True.")
    with ExitStack() as stack:
        sources = [stack.enter_context(rasterio.open(path)) for path in inputs]
        ref = sources[0]
        dem_src = stack.enter_context(rasterio.open(dem)) if dem is not None else None
        for path, src in zip(protected_inputs, sources + ([dem_src] if dem_src else [])):
            t = src.transform
            if src.count != 1 or src.crs is None or t.b or t.d or t.a <= 0 or t.e >= 0:
                raise ValueError(f"Expected a single-band north-up raster with a CRS: {path}")
            if (src.crs, src.transform, src.shape) != (ref.crs, ref.transform, ref.shape):
                raise ValueError(f"Input grid does not match {inputs[0]}: {path}")
        lake_frame = _prepare_lakes(lakes, ref.crs) if lakes is not None else None
        lake_index = lake_frame.sindex if lake_frame is not None else None
        donor_tree = (_nearest_land_donors(sources, dem_src, lake_frame, lake_index, all_touched)
                      if lake_frame is not None else None)
        output_dir.mkdir(parents=True, exist_ok=True)
        if fill_output is not None:
            diagnostics_dir.mkdir(parents=True, exist_ok=True)
        # Construct a fresh profile to avoid inherited tile/compression settings.
        profile = dict(driver="GTiff", width=ref.width, height=ref.height,
                       crs=ref.crs, transform=ref.transform, count=1,
                       dtype="float32", nodata=-9999, tiled=False, interleave="pixel",
                       compress="deflate", BIGTIFF="IF_SAFER")
        with TemporaryDirectory(prefix=".ef5-crest-", dir=output_dir) as temp:
            staged = {key: Path(temp) / path.name for key, path in outputs.items()}
            if fill_output:
                mask_temp = stack.enter_context(TemporaryDirectory(prefix=".ef5-crest-mask-", dir=diagnostics_dir))
                staged["fill_mask"] = Path(mask_temp) / fill_output.name
            lake_count = 0
            filled_count = 0
            isolated_count = 0
            coastal_count = 0
            with ExitStack() as writers:
                targets = {key: writers.enter_context(rasterio.open(path, "w", **profile))
                           for key, path in staged.items()}
                for key, dst in targets.items():
                    dst.update_tags(
                        parameter=key, method="legacy_crest_texture_lookup",
                        texture_depth_average="equal_mean_seven_levels",
                        source_notebook="OLD_Builder/4_Crest_parameters_estimation.ipynb",
                        bedrock_units="cm", bedrock_upper_cutoff="none",
                        units={"wm": "mm", "fc": "legacy_table_conductivity_x10", "b": "dimensionless", "fill_mask": "0=unchanged,1=isolated,2=coastal,3=nearest_land"}[key],
                        lake_masking="enabled" if lakes is not None else "disabled",
                        lake_all_touched=str(all_touched),
                        isolated_fill=("all_nonlake_land_nearest" if lake_frame is not None else
                                       "eight_neighbors_single_pass_with_coastal_exception" if dem_src else "disabled"),
                    )
                for row in range(0, ref.height, 512):
                    for col in range(0, ref.width, 512):
                        window = Window(col, row, min(512, ref.width-col), min(512, ref.height-row))
                        # A one-cell halo preserves neighbor decisions at block boundaries.
                        left, top = max(0, col-1), max(0, row-1)
                        right = min(ref.width, col+int(window.width)+1)
                        bottom = min(ref.height, row+int(window.height)+1)
                        read_window = Window(left, top, right-left, bottom-top) if dem_src else window
                        shape = (int(read_window.height), int(read_window.width))
                        data, validity = [], []
                        for index, src in enumerate(sources):
                            values = src.read(1, window=read_window, masked=True).astype("float64")
                            valid = (~np.ma.getmaskarray(values) & np.isfinite(values.data)
                                     & (values.data >= 0))
                            if index < 14:
                                valid &= values.data <= 100
                            data.append(values.data.copy())
                            validity.append(valid)
                        domain = np.ones(shape, dtype=bool)
                        filled = np.zeros(shape, dtype=bool)
                        fill_codes = np.zeros(shape, dtype="uint8")
                        lake_mask = np.zeros(shape, dtype=bool)
                        if lake_frame is not None:
                            selected = lake_index.query(box(*ref.window_bounds(read_window)), predicate="intersects")
                            if len(selected):
                                lake_mask = geometry_mask(
                                    lake_frame.geometry.iloc[selected], out_shape=shape,
                                    transform=ref.window_transform(read_window), invert=True,
                                    all_touched=all_touched,
                                )
                            for values, valid in zip(data, validity):
                                values[lake_mask] = np.nan
                                valid[lake_mask] = False
                        if dem_src:
                            dem_values = dem_src.read(1, window=read_window, masked=True)
                            domain = ~np.ma.getmaskarray(dem_values) & np.isfinite(dem_values.data)
                            complete = np.logical_and.reduce(validity)
                            land = domain & ~lake_mask
                            candidates = land & ~complete
                            if lake_frame is not None:
                                rr, cc = np.nonzero(candidates)
                                if len(rr):
                                    if donor_tree is None:
                                        raise ValueError("Cannot fill land gaps: no complete non-lake SoilGrids donor exists inside the DEM.")
                                    query = np.column_stack(((rr+int(read_window.row_off))*abs(ref.transform.e),
                                                             (cc+int(read_window.col_off))*abs(ref.transform.a)))
                                    _, nearest = donor_tree.query(query)
                                    unique, inverse = np.unique(nearest, return_inverse=True)
                                    donor_coordinates = donor_tree.data[unique]
                                    donor_rows = np.rint(donor_coordinates[:, 0]/abs(ref.transform.e)).astype("int64")
                                    donor_cols = np.rint(donor_coordinates[:, 1]/abs(ref.transform.a)).astype("int64")
                                    xx, yy = rasterio.transform.xy(ref.transform, donor_rows, donor_cols)
                                    xy = list(zip(xx, yy))
                                    for index, src in enumerate(sources):
                                        needed = ~validity[index][rr, cc]
                                        if not needed.any():
                                            continue
                                        sampled = np.fromiter((value[0] for value in src.sample(xy, indexes=1)),
                                                              dtype="float64", count=len(unique))
                                        data[index][rr[needed], cc[needed]] = sampled[inverse[needed]]
                                        validity[index][rr[needed], cc[needed]] = True
                                    filled[rr, cc] = True
                                    fill_codes[rr, cc] = 3
                            else:
                                # Convolution by eight shifts, with no full-domain arrays or SciPy dependency.
                                padded = np.pad(candidates, 1, constant_values=False)
                                adjacent_missing = np.zeros(shape, dtype=bool)
                                offsets = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                                           if dy or dx]
                                for dy, dx in offsets:
                                    adjacent_missing |= padded[1+dy:1+dy+shape[0], 1+dx:1+dx+shape[1]]
                                eligible = candidates & ~adjacent_missing
                                donors = np.pad(land & complete, 1, constant_values=False)
                                # Beyond the raster extent is unknown, not a verified DEM NoData cell.
                                outside_domain = np.pad(~domain, 1, constant_values=False)
                                original = [np.pad(values, 1, constant_values=np.nan) for values in data]
                                offsets.sort(key=lambda d: (np.hypot(d[1]*ref.transform.a, d[0]*ref.transform.e), d[0], d[1]))
                                for dy, dx in offsets:
                                    neighbor_slice = (slice(1+dy, 1+dy+shape[0]), slice(1+dx, 1+dx+shape[1]))
                                    opposite_slice = (slice(1-dy, 1-dy+shape[0]), slice(1-dx, 1-dx+shape[1]))
                                    coastal = candidates & outside_domain[opposite_slice]
                                    take = (eligible | coastal) & ~filled & donors[neighbor_slice]
                                    fill_codes[take & eligible] = 1
                                    fill_codes[take & ~eligible] = 2
                                    for index in range(15):
                                        repair = take & ~validity[index]
                                        data[index][repair] = original[index][neighbor_slice][repair]
                                        validity[index][repair] = True
                                    filled |= take
                        core = (slice(row-int(read_window.row_off), row-int(read_window.row_off)+int(window.height)),
                                slice(col-int(read_window.col_off), col-int(read_window.col_off)+int(window.width)))
                        data = [values[core] for values in data]
                        validity = [valid[core] for valid in validity]
                        domain = domain[core]
                        lake_mask = lake_mask[core]
                        lake_count += int((domain & lake_mask).sum())
                        land = domain & ~lake_mask
                        filled = filled[core]
                        fill_codes = fill_codes[core]
                        isolated_count += int((fill_codes == 1).sum())
                        coastal_count += int((fill_codes == 2).sum())
                        filled_count += int(filled.sum())
                        shape = domain.shape
                        valid_texture = land & np.logical_and.reduce(validity[:14])
                        sand = np.where(valid_texture, sum(data[:7]) / 7, np.nan)
                        clay = np.where(valid_texture, sum(data[7:14]) / 7, np.nan)
                        texture = _classify_soil_texture(sand, clay)
                        bedrock = data[14]
                        valid_bedrock = land & validity[14]
                        results = {key: np.full(shape, -9999, dtype="float32") for key in outputs}
                        for soil_class, params in SOIL_PARAMETERS.items():
                            mask = texture == soil_class
                            wm_mask = mask & valid_bedrock
                            wm = params["eff_porosity"] * 10 * bedrock[wm_mask]
                            if np.any(wm > np.finfo("float32").max):
                                raise ValueError("Calculated Wm exceeds float32 range.")
                            results["wm"][wm_mask] = wm
                            results["fc"][mask] = params["hydraulic_cond"] * 10
                            results["b"][mask] = params["b"]
                        if dem_src:
                            results["fill_mask"] = np.where(land, fill_codes.astype("float32"), -9999)
                        for key, dst in targets.items():
                            dst.write(results[key], 1, window=window)
                for dst in targets.values():
                    dst.update_tags(lake_cells=str(lake_count), filled_input_cells=str(filled_count),
                                    isolated_filled_cells=str(isolated_count),
                                    coastal_filled_cells=str(coastal_count),
                                    nearest_land_filled_cells=str(filled_count-isolated_count-coastal_count))
            for key, path in staged.items():
                path.replace(fill_output if key == "fill_mask" else outputs[key])
    return outputs

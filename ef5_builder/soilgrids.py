"""Download regional SoilGrids layers at their native resolution and CRS."""

import logging
import math
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds

LOGGER = logging.getLogger(__name__)
NODATA = -9999
FORMER_SERVER = "https://files.isric.org/soilgrids/former/2017-03-10/data"
V2_SERVER = "https://files.isric.org/soilgrids/latest/data"
TEXTURES = {"sand": "SNDPPT", "clay": "CLYPPT", "silt": "SLTPPT"}
DEPTHS_2017 = {"sl1": 0, "sl2": 5, "sl3": 15, "sl4": 30,
               "sl5": 60, "sl6": 100, "sl7": 200}
DEPTHS_V2 = ("0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm")


def _selection(values, choices, label):
    if isinstance(values, str):
        values = (values,)
    try:
        values = tuple(values)
    except TypeError as exc:
        raise ValueError(f"{label} must be a nonempty selection from {tuple(choices)}.") from exc
    if not values or any(not isinstance(v, str) or v not in choices for v in values):
        raise ValueError(f"{label} must be a nonempty selection from {tuple(choices)}.")
    if len(set(values)) != len(values):
        raise ValueError(f"{label} must not contain duplicates.")
    return values


def _dem_domain(dem):
    with rasterio.open(dem) as src:
        t = src.transform
        if src.crs is None or src.count != 1 or t.b or t.d or t.a <= 0 or t.e >= 0:
            raise ValueError("DEM must be a single-band, north-up raster with a CRS.")
        return src.bounds, src.crs


def _native_window(src, bounds, bounds_crs):
    t = src.transform
    if src.crs is None or src.count != 1 or t.b or t.d or t.a <= 0 or t.e >= 0:
        raise ValueError("Expected a single-band, north-up soil raster with a CRS.")
    box = transform_bounds(bounds_crs, src.crs, *bounds, densify_pts=21)
    window = from_bounds(*box, transform=t)
    # Expand to whole source pixels; never change resolution or grid origin.
    left = max(0, math.floor(round(window.col_off, 8)))
    top = max(0, math.floor(round(window.row_off, 8)))
    right = min(src.width, math.ceil(round(window.col_off + window.width, 8)))
    bottom = min(src.height, math.ceil(round(window.row_off + window.height, 8)))
    if right <= left or bottom <= top:
        raise ValueError("Requested bounds do not overlap the soil raster.")
    return Window(left, top, right - left, bottom - top)


def _open_source(url):
    # GDAL reads only the source tiles/ranges needed for the requested grid.
    # Opening the VRT through /vsicurl/ preserves relative remote tile paths.
    return rasterio.open("/vsicurl/" + url)


def _download_layers(layers, output_dir, dem, overwrite, timeout, retries):
    bounds, bounds_crs = _dem_domain(dem)
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be positive seconds.")
    if not isinstance(retries, int) or isinstance(retries, bool) or retries < 0:
        raise ValueError("retries must be a nonnegative integer.")
    output_dir = Path(output_dir).resolve()
    outputs = {key: output_dir / filename for key, filename, _, _ in layers}
    for path in outputs.values():
        if path == Path(dem).resolve():
            raise ValueError("Output must not replace the DEM raster.")
        if path.exists() and not overwrite:
            raise FileExistsError(f"{path} already exists; use overwrite=True.")
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                      GDAL_HTTP_TIMEOUT=str(timeout), GDAL_HTTP_MAX_RETRY=str(retries),
                      GDAL_HTTP_RETRY_DELAY="1"):
        output_dir.mkdir(parents=True, exist_ok=True)
        for i, (key, _, url, tags) in enumerate(layers):
            LOGGER.info("Downloading SoilGrids %s (%d/%d)", key, i + 1, len(layers))
            with _open_source(url) as src:
                subset = _native_window(src, bounds, bounds_crs)
                grid = dict(crs=src.crs, transform=src.window_transform(subset),
                            width=int(subset.width), height=int(subset.height))
                with TemporaryDirectory(prefix=".ef5-soil-", dir=output_dir) as temp:
                    staged = Path(temp) / "output.tif"
                    count = 0
                    with rasterio.open(staged, "w", driver="GTiff", **grid, count=1,
                                       dtype="float32", nodata=NODATA, tiled=False, interleave="pixel",
                                       compress="deflate", BIGTIFF="IF_SAFER") as dst:
                        for _, window in dst.block_windows(1):
                            read = Window(subset.col_off + window.col_off,
                                          subset.row_off + window.row_off,
                                          window.width, window.height)
                            values = src.read(1, window=read, masked=True)
                            valid = (~np.ma.getmaskarray(values)
                                     & np.isfinite(values.data) & (values.data >= 0))
                            converted = values.data.astype("float32") * float(tags["conversion_factor"])
                            if tags["units"] == "%":
                                valid &= converted <= 100
                            data = np.full(values.shape, NODATA, dtype="float32")
                            data[valid] = converted[valid]
                            count += int(valid.sum())
                            dst.write(data, 1, window=window)
                        dst.update_tags(**tags, source_url=url, grid_processing="native_subset")
                    if not count:
                        raise ValueError(f"No valid soil values in the requested domain: {key}")
                    staged.replace(outputs[key])
    return outputs


def download_soilgrids_2017(
    output_dir, *, dem,
    properties=("sand", "clay"), depths=tuple(DEPTHS_2017),
    include_bedrock=True, overwrite=False, timeout=60, retries=2,
):
    """Download 2017 mean soil texture (%) and optionally bedrock depth (cm).

    dem is the final model DEM path. Its extent defines the download region.
    Outputs retain the source CRS, pixel size and grid alignment. DEM bounds are
    transformed from the DEM CRS to source coordinates and expanded to whole native pixels.
    No resampling or reprojection of raster values occurs. Use the separate
    resample_and_subset function to align downloaded layers to your DEM.
    Defaults to the 15 CREST inputs: seven sand layers, seven clay layers,
    and bedrock. Add "silt" to properties if needed. depths selects sl1..sl7 (point depths
    0, 5, 15, 30, 60, 100, 200 cm). BDRICM is kept in cm for CREST's cm-to-mm
    calculation, not converted to metres. No authentication is needed.

    Returns paths keyed by property_depth (e.g. sand_sl1) and bedrock.
    Filenames SNDPPT_M_sl1_250m.tif etc. match the CREST reader; the suffix
    identifies the source product. Regional reads
    avoid downloading entire global rasters. Float32, NoData=-9999, native CRS.
    Existing files require overwrite=True. Failures retain completed layers
    but leave no partial output for the failed layer.
    """
    properties = _selection(properties, TEXTURES, "properties")
    depths = _selection(depths, DEPTHS_2017, "depths")
    layers = []
    for prop in properties:
        for depth in depths:
            name = f"{TEXTURES[prop]}_M_{depth}_250m"
            tags = dict(soilgrids_version="2017", property=prop, depth_cm=str(DEPTHS_2017[depth]),
                        depth_type="point", statistic="mean", units="%", source_units="%",
                        conversion_factor="1")
            layers.append((f"{prop}_{depth}", name + ".tif", f"{FORMER_SERVER}/{name}_ll.tif", tags))
    if include_bedrock:
        layers.append(("bedrock", "BDRICM_M_250m.tif", f"{FORMER_SERVER}/BDRICM_M_250m_ll.tif",
                       dict(soilgrids_version="2017", property="bedrock", statistic="mean",
                            units="cm", source_units="cm", conversion_factor="1")))
    return _download_layers(layers, output_dir, dem, overwrite, timeout, retries)


def download_soilgrids_v2(
    output_dir, *, dem,
    properties=("sand", "clay"), depths=DEPTHS_V2,
    overwrite=False, timeout=60, retries=2,
):
    """Download v2 mean sand/clay/silt and convert g/kg to percent (divide by 10).

    Domain, output format, overwrite and retry options match
    download_soilgrids_2017. Uses the latest/data WebDAV VRT mosaics and
    retains their native projected CRS and resolution. Reprojection to the
    model DEM is a separate resample_and_subset call.
    Defaults to 12 sand/clay layers; add "silt" to properties if needed.
    depths selects 0-5cm, 5-15cm, 15-30cm, 30-60cm, 60-100cm, 100-200cm.
    Returns property_interval keys, e.g. sand_0-5cm, with filenames such as
    sand_0-5cm_mean_percent.tif. These interval averages are not the seven
    point-depth layers expected by the CREST workflow. No bedrock layer is
    supplied by this function; no depth interpolation or relabelling occurs.
    NoData is masked before conversion. A raw texture value of 350 becomes 35%.
    """
    properties = _selection(properties, TEXTURES, "properties")
    depths = _selection(depths, DEPTHS_V2, "depths")
    layers = []
    for prop in properties:
        for depth in depths:
            name = f"{prop}_{depth}_mean"
            top, bottom = depth.removesuffix("cm").split("-")
            tags = dict(soilgrids_version="2.0", property=prop, depth_type="interval",
                        depth_top_cm=top, depth_bottom_cm=bottom, statistic="mean",
                        units="%", source_units="g/kg", conversion_factor="0.1")
            layers.append((f"{prop}_{depth}", name + "_percent.tif",
                           f"{V2_SERVER}/{prop}/{name}.vrt", tags))
    return _download_layers(layers, output_dir, dem, overwrite, timeout, retries)

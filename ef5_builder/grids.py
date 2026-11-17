"""Align continuous model layers to an existing template grid."""
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT


def resample_and_subset(input_file, output_file, template, *, resampling="nearest",
                        mask_template=False, overwrite=False):
    """Resample/subset a single-band layer to the exact template grid.

    Python equivalent of OLD_Builder/resample_and_subset.csh: template extent
    and pixel size, nearest-neighbor by default, Deflate, float32, NoData=-9999.
    Also matches template CRS and dimensions exactly, reprojecting if needed.
    mask_template=True additionally excludes invalid template cells; False
    follows the script's rectangular extent. Supports nearest, bilinear,
    average. Never use for precomputed FDIR/FACC: regenerate those from a DEM.
    Writes atomically and returns the absolute output Path.
    """
    try:
        method = Resampling[resampling]
    except (KeyError, TypeError) as exc:
        raise ValueError("resampling must be nearest, bilinear, or average.") from exc
    if method not in (Resampling.nearest, Resampling.bilinear, Resampling.average):
        raise ValueError("resampling must be nearest, bilinear, or average.")
    output = Path(output_file).resolve()
    if output in (Path(input_file).resolve(), Path(template).resolve()):
        raise ValueError("Output must not replace the input or template raster.")
    if output.exists() and not overwrite:
        raise FileExistsError(f"{output} already exists; use overwrite=True.")
    with rasterio.open(input_file) as raw, rasterio.open(template) as ref:
        for src in (raw, ref):
            t = src.transform
            if src.count != 1 or src.crs is None or t.b or t.d or t.a <= 0 or t.e >= 0:
                raise ValueError("Input and template must be single-band north-up rasters with a CRS.")
        grid = dict(crs=ref.crs, transform=ref.transform, width=ref.width, height=ref.height)
        output.parent.mkdir(parents=True, exist_ok=True)
        with WarpedVRT(raw, **grid, dtype="float32", nodata=-9999, resampling=method) as src:
            with TemporaryDirectory(prefix=".ef5-grid-", dir=output.parent) as temp:
                staged = Path(temp) / "output.tif"
                with rasterio.open(staged, "w", driver="GTiff", **grid, count=1,
                                   dtype="float32", nodata=-9999, tiled=False, interleave="pixel",
                                   compress="deflate", BIGTIFF="IF_SAFER") as dst:
                    for _, window in dst.block_windows(1):
                        values = src.read(1, window=window, masked=True)
                        valid = ~np.ma.getmaskarray(values) & np.isfinite(values.data)
                        if mask_template:
                            reference = ref.read(1, window=window, masked=True)
                            valid &= ~np.ma.getmaskarray(reference) & np.isfinite(reference.data)
                        dst.write(np.where(valid, values.data.astype("float32"), -9999), 1, window=window)
                    dst.update_tags(**raw.tags())
                    dst.update_tags(resampling=resampling, grid_processing="resample_and_subset")
                staged.replace(output)
    return output

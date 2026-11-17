
"""Prepare aligned EF5 basic grids without resampling drainage rasters."""

from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import geometry_mask, geometry_window
from rasterio.windows import Window

NODATA = -9999
D8 = (64, 128, 1, 2, 4, 8, 16, 32)


def _region(region, crs):
    frame = (
        gpd.read_file(region)
        if isinstance(region, (str, Path))
        else region.copy()
    )

    if frame.crs is None:
        raise ValueError("Region must have a defined CRS.")

    if (
        frame.empty
        or frame.geometry.isna().any()
        or frame.geometry.is_empty.any()
    ):
        raise ValueError("Region must contain nonempty polygon geometries.")

    if (
        not frame.geometry.is_valid.all()
        or not frame.geom_type.isin(["Polygon", "MultiPolygon"]).all()
    ):
        raise ValueError("Region must contain valid Polygon or MultiPolygon geometries.")

    return list(frame.to_crs(crs).geometry)


def _check_grid(src):
    if src.crs is None or src.count != 1:
        raise ValueError(
            "Each input must be a single-band raster with a defined CRS."
        )

    if src.crs.to_epsg() != 4326:
        raise ValueError(
            "Input raster must already use EPSG:4326. "
            "Reprojection of drainage rasters is not performed."
        )

    if (
        src.transform.b != 0
        or src.transform.d != 0
        or src.transform.a <= 0
        or src.transform.e >= 0
    ):
        raise ValueError(
            "Inputs must use a north-up grid without rotation."
        )


def _paths(output_dir, inputs, overwrite):
    output_dir = Path(output_dir).resolve()

    paths = {
        "dem": output_dir / "dem.tif",
        "fdir": output_dir / "ddm.tif",
        "facc": output_dir / "fam.tif",
    }

    sources = {Path(p).resolve() for p in inputs}

    for path in paths.values():
        if path in sources:
            raise ValueError(
                "Output paths must not replace input rasters."
            )

        if path.exists() and not overwrite:
            raise FileExistsError(
                f"{path} already exists; use overwrite=True."
            )

    return paths


def prepare_hydrosheds(
    dem,
    facc,
    fdir,
    output_dir,
    region=None,
    *,
    all_touched=False,
    overwrite=False,
):
    """Prepare precomputed HydroSHEDS grids for EF5.

    DEM, FACC and FDIR are always required.

    If region is provided:
        Clip and mask all three rasters to the region.

    If region is None:
        Convert all three rasters over their full extent.

    Requirements:
        - EPSG:4326
        - Identical CRS, transform and dimensions
        - Single-band rasters
        - ESRI D8 flow direction codes

    Outputs:
        dem.tif, fam.tif, ddm.tif
        Float32, NoData=-9999, EPSG:4326, striped and Deflate-compressed

    No reprojection or resampling is performed.
    Processing uses 512x512 pixel windows.
    """

    if dem is None or facc is None or fdir is None:
        raise ValueError("DEM, FACC and FDIR are required.")

    paths = _paths(output_dir, [dem, facc, fdir], overwrite)

    with ExitStack() as stack:

        sources = {
            key: stack.enter_context(rasterio.open(path))
            for key, path in [
                ("dem", dem),
                ("facc", facc),
                ("fdir", fdir),
            ]
        }

        reference = sources["dem"]

        # Validate grid properties and alignment
        for src in sources.values():
            _check_grid(src)

            if (
                src.crs != reference.crs
                or src.transform != reference.transform
                or src.shape != reference.shape
            ):
                raise ValueError(
                    "DEM, FACC and FDIR must have identical "
                    "CRS, transform and dimensions."
                )

        # ------------------------------------------
        # Determine processing extent
        # ------------------------------------------

        if region is not None:

            shapes = _region(region, reference.crs)

            bounds = np.asarray([g.bounds for g in shapes])

            region_bounds = np.array([
                bounds[:, 0].min(),
                bounds[:, 1].min(),
                bounds[:, 2].max(),
                bounds[:, 3].max(),
            ])

            raster_bounds = np.asarray(reference.bounds)

            tolerance = np.array([
                reference.res[0],
                reference.res[1],
                reference.res[0],
                reference.res[1],
            ]) * 1e-6

            if (
                np.any(
                    region_bounds[:2]
                    < raster_bounds[:2] - tolerance[:2]
                )
                or np.any(
                    region_bounds[2:]
                    > raster_bounds[2:] + tolerance[2:]
                )
            ):
                raise ValueError(
                    "Region is not fully covered by the raster extent."
                )

            window = geometry_window(reference, shapes)

        else:
            shapes = None

            window = Window(
                0, 0,
                reference.width,
                reference.height,
            )

        transform = reference.window_transform(window)

        # ------------------------------------------
        # Read raster blocks
        # ------------------------------------------

        def blocks():

            for row in range(0, int(window.height), 512):
                for col in range(0, int(window.width), 512):

                    local = Window(
                        col,
                        row,
                        min(512, window.width - col),
                        min(512, window.height - row),
                    )

                    read = Window(
                        window.col_off + col,
                        window.row_off + row,
                        local.width,
                        local.height,
                    )

                    arrays = {
                        key: src.read(
                            1,
                            window=read,
                            masked=True,
                        )
                        for key, src in sources.items()
                    }

                    block_shape = (
                        int(local.height),
                        int(local.width),
                    )

                    if shapes is not None:
                        valid = geometry_mask(
                            shapes,
                            block_shape,
                            reference.window_transform(read),
                            invert=True,
                            all_touched=all_touched,
                        )
                    else:
                        valid = np.ones(
                            block_shape,
                            dtype=bool,
                        )

                    # Keep cells valid in all three rasters
                    for array in arrays.values():
                        valid &= (
                            ~np.ma.getmaskarray(array)
                            & np.isfinite(array.data)
                        )

                    yield local, arrays, valid

        # ------------------------------------------
        # Validate raster values
        # ------------------------------------------

        count = 0

        for _, arrays, valid in blocks():

            count += int(valid.sum())

            if np.any(arrays["facc"].data[valid] < 0):
                raise ValueError(
                    "Flow accumulation must be nonnegative."
                )

            if not np.isin(
                arrays["fdir"].data[valid],
                [0, *D8],
            ).all():
                raise ValueError(
                    "FDIR must use ESRI D8 codes."
                )

            # Check that DEM elevations can be represented
            # as finite Float32 values
            dem_values = arrays["dem"].data[valid]

            if np.any(
                np.abs(dem_values)
                > np.finfo(np.float32).max
            ):
                raise ValueError(
                    "DEM contains values outside Float32 range."
                )

        if count == 0:
            raise ValueError(
                "No common valid raster cells found."
            )

        # ------------------------------------------
        # Write EF5 outputs
        # ------------------------------------------

        Path(output_dir).mkdir(
            parents=True,
            exist_ok=True,
        )

        targets = {}

        for key, path in paths.items():

            targets[key] = stack.enter_context(
                rasterio.open(
                    path,
                    "w",
                    driver="GTiff",
                    width=int(window.width),
                    height=int(window.height),
                    count=1,
                    crs=reference.crs,
                    transform=transform,
                    dtype="float32",
                    nodata=NODATA,
                    compress="deflate",
                    tiled=False, interleave="pixel",
                    BIGTIFF="IF_SAFER",
                )
            )

        for local, arrays, valid in blocks():

            for key, dst in targets.items():

                data = np.full(
                    valid.shape,
                    NODATA,
                    dtype=np.float32,
                )

                data[valid] = arrays[key].data[
                    valid
                ].astype(np.float32)

                dst.write(
                    data,
                    1,
                    window=local,
                )

    return paths


def prepare_from_dem(
    dem,
    output_dir,
    region=None,
    *,
    condition=True,
    all_touched=False,
    overwrite=False,
):
    """Derive EF5 drainage grids from a DEM.

    DEM is always required.

    If region is provided:
        Derive drainage and clip all three outputs.

    If region is None:
        Derive drainage over the full DEM extent.

    All outputs use Float32, NoData=-9999 and EPSG:4326.
    GeoTIFFs are striped and Deflate-compressed for EF5 reader compatibility.
    """

    _paths(output_dir, [dem], overwrite)

    try:
        from pysheds.grid import Grid
    except ImportError as exc:
        raise ImportError(
            "Install pysheds to derive drainage grids."
        ) from exc

    with rasterio.open(dem) as src:

        _check_grid(src)

        if region is not None:
            _region(region, src.crs)

        data = src.read(
            1,
            masked=True,
        ).astype("float64")

        valid = (
            ~np.ma.getmaskarray(data)
            & np.isfinite(data.data)
        )

        if not valid.any():
            raise ValueError(
                "DEM contains no valid elevations."
            )

        profile = dict(
            driver="GTiff",
            height=src.height,
            width=src.width,
            count=1,
            dtype="float64",
            crs=src.crs,
            transform=src.transform,
            nodata=np.nan,
            interleave="pixel",
        )

    with TemporaryDirectory(
        prefix="ef5-basic-"
    ) as temp:

        temp = Path(temp)

        clean = temp / "dem.tif"

        with rasterio.open(
            clean,
            "w",
            **profile,
        ) as dst:

            dst.write(
                np.where(
                    valid,
                    data.data,
                    np.nan,
                ),
                1,
            )

        # ------------------------------------------
        # Hydrologic calculations
        # ------------------------------------------

        grid = Grid.from_raster(str(clean))
        elevation = grid.read_raster(str(clean))

        routed = elevation

        if condition:
            routed = grid.resolve_flats(
                grid.fill_depressions(
                    grid.fill_pits(elevation)
                )
            )

        directions = grid.flowdir(
            routed,
            dirmap=D8,
            nodata_out=NODATA,
            pits=0,
            flats=0,
        )

        accumulation = grid.accumulation(
            directions,
            dirmap=D8,
            nodata_out=NODATA,
        )

        # ------------------------------------------
        # Save temporary drainage rasters
        # ------------------------------------------

        for name, array in [
            ("fdir", directions),
            ("facc", accumulation),
        ]:

            with rasterio.open(
                temp / f"{name}.tif",
                "w",
                **profile,
            ) as dst:

                dst.write(
                    np.where(
                        valid,
                        np.asarray(array),
                        np.nan,
                    ),
                    1,
                )

        # ------------------------------------------
        # Convert and optionally clip to EF5
        # ------------------------------------------

        return prepare_hydrosheds(
            dem=clean,
            facc=temp / "facc.tif",
            fdir=temp / "fdir.tif",
            output_dir=output_dir,
            region=region,
            all_touched=all_touched,
            overwrite=overwrite,
        )

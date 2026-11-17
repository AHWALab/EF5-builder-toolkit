# Basic grids

EF5 uses the DEM, flow direction (FDIR/DDM), and flow accumulation (FACC/FAM) to define its computational mesh. Run [notebook 1](../Example/Example_notebooks/1_Basic_grids_library.ipynb), set your input and output paths, and choose a workflow. The notebook imports the installed functions directly:

```python
from ef5_builder import prepare_hydrosheds, prepare_from_dem
```

## Option A: Prepare HydroSHEDS layers

Supply aligned HydroSHEDS DEM, ACC, and DIR rasters. Include a polygon region to clip and mask the outputs:

```python
outputs = prepare_hydrosheds(
    dem="data/hyd_dem.tif",
    facc="data/hyd_acc.tif",
    fdir="data/hyd_dir.tif",
    region="data/region.gpkg",  #Optional. A shapefile is also accepted 
    output_dir="data/basic",
)
```

Omit `region` (or set `region=None`) to convert the full raster extent:

```python
outputs = prepare_hydrosheds(
    dem="data/hyd_dem.tif",
    facc="data/hyd_acc.tif",
    fdir="data/hyd_dir.tif",
    output_dir="data/basic",
)
```

All three rasters are required and must be single-band, already in **EPSG:4326**, with identical CRS, transform, and dimensions. Use ACC upstream-cell counts rather than ACA upstream area. Accumulation must be nonnegative, and flow direction must use ESRI D8 codes (`1, 2, 4, 8, 16, 32, 64, 128`); `0` is also accepted for cells without a downstream direction. 

The function preserves the native grid without resampling or reprojection; vector coordinates are transformed to the raster CRS. Processing uses 512 × 512 pixel windows to support large source rasters. Global mosaicking is not included.

## Option B: Derive drainage from a DEM

Supply a single-band, north-up DEM without rotation, already in **EPSG:4326**, and optionally a polygon region:

```python
outputs = prepare_from_dem(
    dem="data/my_dem.tif",
    region="data/region.gpkg",
    output_dir="data/basic",
)
```

By default (`condition=True`), the function fills pits and depressions, resolves flats, and calculates ESRI D8 direction and accumulation over the full supplied DEM before optionally clipping and masking to the region. Use `condition=False` to skip pit filling, depression filling, and flat resolution when deriving drainage from an already conditioned DEM:

```python
outputs = prepare_from_dem(
    dem="data/conditioned_dem.tif",
    output_dir="data/basic",
    condition=False,
)
```

This example omits `region`, so outputs cover the full DEM extent. Supply the complete upstream catchment even when clipping to a smaller region. If you need a different resolution or need to convert a projected DEM to EPSG:4326, prepare the DEM first, then derive drainage. Geographic routing uses angular pixel distances. The output DEM retains original elevations; conditioning is used only for routing.

## Optional arguments

| Argument | Default | Behavior |
| --- | --- | --- |
| `region` | `None` | Process the full raster extent; supply a vector file path or GeoDataFrame to clip and mask. |
| `all_touched` | `False` | Use the default pixel-center polygon mask; set `True` to include all pixels touched by the region. Applies only when a region is supplied. |
| `overwrite` | `False` | Refuse existing output files; set `True` to replace them. Output paths must never replace input rasters. |
| `condition` | `True` | Fill pits and depressions and resolve flats before routing. Available only in `prepare_from_dem`. |

`all_touched`, `overwrite`, and `condition` are keyword-only arguments.

## Outputs and EF5 settings

When a region is supplied, both functions accept a vector file path or a filtered GeoDataFrame with a defined CRS. All features are included; geometries must be nonempty, valid Polygons or MultiPolygons, and the region must be fully covered by the raster extent. Both functions return `dem`, `fdir`, and `facc`:

| Layer | Output | Data type | NoData |
| --- | --- | --- | --- |
| DEM | `dem.tif` | float32 | -9999 |
| FDIR / DDM | `ddm.tif` | float32 | -9999 |
| FACC / FAM | `fam.tif` | float32 | -9999 |

Accumulation derived by `prepare_from_dem` includes the current cell, so use `SelfFAM=true`; for supplied HydroSHEDS ACC, use the same setting for counts that include the current cell.

```ini
[Basic]
DEM=data/basic/dem.tif
DDM=data/basic/ddm.tif
FAM=data/basic/fam.tif
PROJ=geographic
ESRIDDM=true
SelfFAM=true
```

Use `PROJ=geographic` for these EPSG:4326 outputs. Neither function accepts projected raster inputs or reprojects drainage rasters.

---

## NumPy compatibility for DEM processing

The supported `pysheds` versions use `numpy.in1d` when calculating flow
accumulation. NumPy 2.4 removed that function, so the toolkit specifies
`numpy>=1.24,<2.4` in both `environment.yml` and `pyproject.toml`.
Update the environment from the repository root before running the DEM workflow.
See the [pysheds compatibility issue](https://github.com/pysheds/pysheds/issues/312).

from pathlib import Path
import numpy as np
import geopandas as gpd
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Polygon, box
from ef5_builder import prepare_hydrosheds, prepare_from_dem


def raster(path, data, transform=None, dtype="float64", nodata=-9999):
    with rasterio.open(path, 'w', driver='GTiff', height=data.shape[0], width=data.shape[1], count=1, dtype=dtype, crs='EPSG:4326', transform=transform or from_origin(0, 0.875, 0.125, 0.125), nodata=nodata) as dst:
        dst.write(data.astype(dtype), 1)
    return path


def inputs(tmp_path):
    dem = raster(tmp_path/'dem.tif', np.arange(49).reshape(7, 7))
    facc = raster(tmp_path/'acc.tif', np.full((7, 7), 16777217), dtype="uint32", nodata=4294967295)
    fdir = raster(tmp_path/'dir.tif', np.ones((7, 7)), dtype="uint8", nodata=255)
    region = gpd.GeoDataFrame(geometry=[box(0.125, 0.125, 0.5, 0.75), box(0.5, 0.125, 0.75, 0.375)], crs=4326)
    return dem, facc, fdir, region


def test_clip_alignment_crs_mask_and_output_format(tmp_path):
    dem, facc, fdir, region = inputs(tmp_path)
    shape = tmp_path/'region.shp'
    region.to_crs(3857).to_file(shape)
    result = prepare_hydrosheds(dem, facc, fdir, output_dir=tmp_path/'out', region=shape)
    grids = []
    masks = []
    for key, path in result.items():
        with rasterio.open(path) as src:
            grids.append((src.shape, src.transform, src.crs))
            a = src.read(1, masked=True)
            masks.append(np.ma.getmaskarray(a))
            assert src.nodata == -9999
            assert src.dtypes == ("float32",)
            assert np.all(src.read(1)[np.ma.getmaskarray(a)] == -9999)
            if key == 'facc': assert np.all(a.compressed() == np.float32(16777217))
    assert grids[0] == grids[1] == grids[2]
    assert all(np.array_equal(masks[0], m) for m in masks)
    assert masks[0].any()
    with pytest.raises(FileExistsError):
        prepare_hydrosheds(dem, facc, fdir, output_dir=tmp_path/'out', region=region)


def test_reject_misaligned_and_invalid_region(tmp_path):
    dem, facc, fdir, region = inputs(tmp_path)
    raster(fdir, np.ones((7, 7)), from_origin(0.001, 0.875, 0.125, 0.125))
    with pytest.raises(ValueError, match='identical'):
        prepare_hydrosheds(dem, facc, fdir, output_dir=tmp_path/'out', region=region)
    assert not (tmp_path/'out').exists()


@pytest.mark.parametrize('offset', [0, 1e-8])
def test_matching_extent_applies_polygon_mask_and_converts(tmp_path, offset):
    dem, facc, fdir, _ = inputs(tmp_path)
    data = np.arange(49, dtype=float).reshape(7, 7)
    data[1, 1] = -32768
    data[2, 2] = np.nan
    raster(dem, data, nodata=-32768)
    # A triangular region shares the raster extent but excludes valid cells.
    region = gpd.GeoDataFrame(geometry=[Polygon([
        (-offset, 0), (0.875, 0), (0.875, 0.875 + offset)
    ])], crs=4326)
    result = prepare_hydrosheds(dem, facc, fdir, output_dir=tmp_path/'out', region=region)
    for key, path in result.items():
        with rasterio.open(path) as src:
            assert src.shape == (7, 7)
            assert src.transform == from_origin(0, 0.875, 0.125, 0.125)
            assert src.dtypes == ('float32',)
            assert src.nodata == -9999
            values = src.read(1)
            assert values[1, 1] == values[2, 2] == -9999
            assert values[0, 0] == -9999  # Outside the triangle.
            assert values[6, 6] == (48 if key == 'dem' else
                                    1 if key == 'fdir' else np.float32(16777217))


def test_reject_region_outside_raster(tmp_path):
    dem, facc, fdir, _ = inputs(tmp_path)
    region = gpd.GeoDataFrame(geometry=[box(-0.001, 0, 0.875, 0.875)], crs=4326)
    with pytest.raises(ValueError, match='not fully covered'):
        prepare_hydrosheds(dem, facc, fdir, output_dir=tmp_path/'out', region=region)
    assert not (tmp_path/'out').exists()


def test_dem_only_known_eastward_flow_and_upstream_counts(tmp_path):
    pytest.importorskip("pysheds")
    # Each row slopes east: interior cell at column 4 has 5 contributing cells,
    # including contributions outside the requested output region.
    a = np.tile(np.arange(7, 0, -1, dtype=float), (7, 1))
    dem = raster(tmp_path/'slope.tif', a)
    region = gpd.GeoDataFrame(geometry=[box(0.375, 0.25, 0.75, 0.625)], crs=4326)
    result = prepare_from_dem(dem, output_dir=tmp_path/'out', region=region)
    for path in result.values():
        with rasterio.open(path) as src:
            assert src.dtypes == ("float32",)
            assert src.nodata == -9999
    with rasterio.open(result['fdir']) as src:
        assert np.all(src.read(1) == 1)
    with rasterio.open(result['facc']) as src:
        np.testing.assert_array_equal(src.read(1), np.tile([4, 5, 6], (3, 1)))
    with rasterio.open(result['dem']) as src:
        np.testing.assert_array_equal(src.read(1), a[2:5, 3:6])


def test_dem_nodata_and_pit(tmp_path):
    pytest.importorskip("pysheds")
    a = np.tile(np.arange(9, 0, -1, dtype=float), (9, 1))
    a[4, 4] = -100
    a[1, 1] = -9999
    dem = raster(tmp_path/'pit.tif', a, from_origin(0, 1.125, 0.125, 0.125))
    region = gpd.GeoDataFrame(geometry=[box(0, 0, 1.125, 1.125)], crs=4326)
    result = prepare_from_dem(dem, output_dir=tmp_path/'out', region=region)
    for path in result.values():
        with rasterio.open(path) as src:
            assert src.dtypes == ("float32",)
            assert src.nodata == -9999
    with rasterio.open(result['fdir']) as src:
        directions = src.read(1, masked=True)
        assert directions.mask[1, 1]
        assert directions[4, 4] in [1, 2, 4, 8, 16, 32, 64, 128]

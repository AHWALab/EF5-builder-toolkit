"""Optional lake masking before isolated/coastal SoilGrids filling."""
import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Polygon, box

from ef5_builder import get_crest_parameters


def soil_inputs(tmp_path, width=5):
    folder = tmp_path / 'soil'
    folder.mkdir()
    profile = dict(driver='GTiff', count=1, width=width, height=5, dtype='float32',
                   crs='EPSG:4326', transform=from_origin(0, 5, 1, 1), nodata=-9999,
                   tiled=False, compress='none')
    for prefix, value in [('SNDPPT', 95), ('CLYPPT', 2)]:
        for level in range(1, 8):
            data = np.full((5, width), value, dtype='float32')
            if prefix == 'SNDPPT' and level == 1:
                data[2, 3] = np.nan
            with rasterio.open(folder / f'{prefix}_M_sl{level}_250m.tif', 'w', **profile) as dst:
                dst.write(data, 1)
    with rasterio.open(folder / 'BDRICM_M_250m.tif', 'w', **profile) as dst:
        data = np.full((5, width), 300, dtype='float32')
        data[2, 2] = 1000  # Lake values must never donate to the land gap.
        dst.write(data, 1)
    dem = tmp_path / 'dem.tif'
    with rasterio.open(dem, 'w', **profile) as dst:
        dst.write(np.ones((5, width), dtype='float32'), 1)
    return folder, dem


def test_lakes_excluded_before_filling(tmp_path):
    folder, dem = soil_inputs(tmp_path)
    lakes = gpd.GeoDataFrame(geometry=[box(2.1, 2.1, 2.9, 2.9)], crs='EPSG:4326')
    original = {p: p.read_bytes() for p in folder.glob('*.tif')}
    outputs = get_crest_parameters(folder, tmp_path / 'out', dem=dem, lakes=lakes.to_crs(3857))
    for path in outputs.values():
        with rasterio.open(path) as src:
            assert src.read(1)[2, 2] == -9999
            assert src.read(1)[2, 3] != -9999
            assert src.tags()['lake_cells'] == '1'
            assert not src.profile.get('tiled', False) and src.compression == rasterio.enums.Compression.deflate
    with rasterio.open(outputs['wm']) as src:
        assert src.read(1)[2, 3] == pytest.approx(1251)
    with rasterio.open(tmp_path / 'crest_diagnostics/crest_filled_mask.tif') as src:
        assert src.read(1)[2, 2] == -9999
        assert src.read(1)[2, 3] == 3
    assert all(p.read_bytes() == content for p, content in original.items())
    # Omitting lakes keeps the prior behavior, including parameters at the lake cell.
    previous = get_crest_parameters(folder, tmp_path / 'previous', dem=dem,
                                    diagnostics_dir=tmp_path / 'previous_diagnostics')
    with rasterio.open(previous['wm']) as src:
        assert src.read(1)[2, 2] == pytest.approx(4170)


def test_repair_lakes_and_require_dem(tmp_path):
    folder, dem = soil_inputs(tmp_path)
    bowtie = Polygon([(1, 1), (3, 3), (1, 3), (3, 1), (1, 1)])
    lakes = gpd.GeoDataFrame(geometry=[bowtie], crs=4326)
    outputs = get_crest_parameters(folder, tmp_path / 'out', dem=dem, lakes=lakes)
    assert not lakes.geometry.is_valid.all()  # The caller's layer is unchanged.
    assert all(path.is_file() for path in outputs.values())
    with pytest.raises(ValueError, match='dem is required'):
        get_crest_parameters(folder, tmp_path / 'no_dem', lakes=lakes)


def test_lake_mask_across_window_boundary(tmp_path):
    folder, dem = soil_inputs(tmp_path, width=515)
    lakes = gpd.GeoDataFrame(geometry=[box(511.1, 2.1, 512.9, 2.9)], crs=4326)
    outputs = get_crest_parameters(folder, tmp_path / 'out', dem=dem, lakes=lakes)
    for path in outputs.values():
        with rasterio.open(path) as src:
            assert (src.read(1)[2, 511:513] == -9999).all()
            assert src.tags()['lake_cells'] == '2'


def test_all_land_gaps_use_global_nearest_original_donor(tmp_path):
    folder, dem = soil_inputs(tmp_path, width=515)
    for filename in ('SNDPPT_M_sl1_250m.tif', 'BDRICM_M_250m.tif'):
        with rasterio.open(folder / filename, 'r+') as dst:
            data = dst.read(1)
            if filename.startswith('BDRICM'):
                data[:, 513:] = 600
            data[:, 2:513] = np.nan
            dst.write(data, 1)
    lakes = gpd.GeoDataFrame(geometry=[box(2.1, 2.1, 2.9, 2.9)], crs=4326)
    outputs = get_crest_parameters(folder, tmp_path / 'out', dem=dem, lakes=lakes)
    with rasterio.open(outputs['wm']) as src:
        values = src.read(1)
        assert values[2, 2] == -9999
        assert values[2, 3] == pytest.approx(1251)
        assert values[2, 512] == pytest.approx(2502)  # Donor lies in the next block.
        assert (values == -9999).sum() == 1
    with rasterio.open(tmp_path / 'crest_diagnostics/crest_filled_mask.tif') as src:
        assert src.read(1)[2, 512] == 3


def test_missing_land_without_any_complete_donor_raises(tmp_path):
    folder, dem = soil_inputs(tmp_path)
    with rasterio.open(folder / 'SNDPPT_M_sl1_250m.tif', 'r+') as dst:
        dst.write(np.full((5, 5), np.nan, dtype='float32'), 1)
    lakes = gpd.GeoDataFrame(geometry=[box(2.1, 2.1, 2.9, 2.9)], crs=4326)
    with pytest.raises(ValueError, match='no complete non-lake'):
        get_crest_parameters(folder, tmp_path / 'out', dem=dem, lakes=lakes)
    assert not list((tmp_path / 'out').glob('*.tif'))

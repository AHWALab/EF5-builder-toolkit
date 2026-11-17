"""Regression checks for the legacy CREST calculation and raster contract."""
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from ef5_builder import get_crest_parameters


def inputs(tmp_path):
    folder = tmp_path / 'inputs'
    folder.mkdir()
    profile = dict(driver='GTiff', count=1, width=5, height=1, dtype='float32',
                   crs='EPSG:4326', transform=from_origin(0, 1, 0.1, 0.1), nodata=-9999)
    # All texture classes are sand. Vary depth levels to check equal averaging.
    for prefix, value in [('SNDPPT', 95), ('CLYPPT', 2)]:
        for level in range(1, 8):
            data = np.full((1, 5), value, dtype='float32')
            if prefix == 'SNDPPT' and level == 7:
                data[0, 1] = -9999
                data[0, 3] = 101
            with rasterio.open(folder / f'{prefix}_M_sl{level}_250m.tif', 'w', **profile) as dst:
                dst.write(data, 1)
    with rasterio.open(folder / 'BDRICM_M_250m.tif', 'w', **profile) as dst:
        dst.write(np.array([[300, 300, -9999, 300, 0]], dtype='float32'), 1)
    return folder


def test_parameters_and_masks(tmp_path):
    folder = inputs(tmp_path)
    outputs = get_crest_parameters(folder, tmp_path / 'out')
    expected = {'wm': [1251, -9999, -9999, -9999, 0],
                'fc': [117.8, -9999, 117.8, -9999, 117.8],
                'b': [2.79, -9999, 2.79, -9999, 2.79]}
    for key, path in outputs.items():
        assert path.is_absolute()
        with rasterio.open(path) as src:
            np.testing.assert_allclose(src.read(1)[0], expected[key], rtol=1e-6)
            assert not src.is_tiled
            assert src.compression == rasterio.enums.Compression.deflate
            assert src.nodata == -9999
            assert src.dtypes == ('float32',)
            assert src.transform == from_origin(0, 1, 0.1, 0.1)
    with pytest.raises(FileExistsError):
        get_crest_parameters(folder, tmp_path / 'out')
    get_crest_parameters(folder, tmp_path / 'out', overwrite=True)


def test_alignment_rejected(tmp_path):
    folder = inputs(tmp_path)
    with rasterio.open(folder / 'BDRICM_M_250m.tif', 'r+') as dst:
        dst.transform = from_origin(1, 1, 0.1, 0.1)
    with pytest.raises(ValueError, match='does not match'):
        get_crest_parameters(folder, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_equal_depth_average(tmp_path):
    folder = inputs(tmp_path)
    # Six sandy layers and one clay layer: equal mean gives sandy loam
    # (sand=80%, clay=100/7%), rather than the last layer's clay class.
    for level in range(1, 8):
        for prefix, value in [('SNDPPT', 0 if level == 7 else 560/6),
                              ('CLYPPT', 100 if level == 7 else 0)]:
            with rasterio.open(folder / f'{prefix}_M_sl{level}_250m.tif', 'r+') as dst:
                dst.write(np.full((1, 5), value, dtype='float32'), 1)
    paths = get_crest_parameters(folder, tmp_path / 'out')
    with rasterio.open(paths['fc']) as src:
        np.testing.assert_allclose(src.read(1), 10.9)


def test_invalid_texture_sum_leaves_no_outputs(tmp_path):
    folder = inputs(tmp_path)
    for level in range(1, 8):
        with rasterio.open(folder / f'CLYPPT_M_sl{level}_250m.tif', 'r+') as dst:
            dst.write(np.full((1, 5), 90, dtype='float32'), 1)
    with pytest.raises(ValueError, match='cannot exceed'):
        get_crest_parameters(folder, tmp_path / 'out')
    assert not list((tmp_path / 'out').glob('*.tif'))


@pytest.mark.parametrize('sand,clay,expected', [
    (95, 2, 1), (85, 5, 2), (65, 10, 3), (40, 20, 4),
    (20, 20, 5), (5, 5, 6), (60, 25, 7), (35, 35, 8),
    (10, 35, 9), (50, 40, 10), (10, 45, 11), (25, 50, 12),
])
def test_legacy_texture_classes(sand, clay, expected):
    from ef5_builder.crest import _classify_soil_texture
    actual = _classify_soil_texture(np.array([sand], dtype=float),
                                    np.array([clay], dtype=float))
    assert actual[0] == expected


def test_missing_input(tmp_path):
    folder = inputs(tmp_path)
    (folder / 'CLYPPT_M_sl7_250m.tif').unlink()
    with pytest.raises(FileNotFoundError, match='CLYPPT_M_sl7'):
        get_crest_parameters(folder, tmp_path / 'out')


def test_isolated_fill_coast_and_block_boundary(tmp_path):
    folder = tmp_path / 'soil'
    folder.mkdir()
    shape = (7, 515)
    profile = dict(driver='GTiff', count=1, width=shape[1], height=shape[0],
                   dtype='float32', crs='EPSG:4326',
                   transform=from_origin(0, 1, .01, .01), nodata=-9999)
    # Include a seam-spanning pair, diagonal pair, single seam hole, and coastal hole.
    missing = [(1, 511), (1, 512), (5, 10), (6, 11), (3, 511), (3, 20), (3, 514)]
    for prefix, value in [('SNDPPT', 95), ('CLYPPT', 2)]:
        for level in range(1, 8):
            data = np.full(shape, value, dtype='float32')
            if prefix == 'SNDPPT' and level == 1:
                for row, col in missing:
                    data[row, col] = np.nan
            with rasterio.open(folder / f'{prefix}_M_sl{level}_250m.tif', 'w', **profile) as dst:
                dst.write(data, 1)
    bedrock = np.full(shape, 300, dtype='float32')
    # Preserve a valid bedrock value at the repaired target.
    bedrock[3, 511] = 500
    with rasterio.open(folder / 'BDRICM_M_250m.tif', 'w', **profile) as dst:
        dst.write(bedrock, 1)
    dem = tmp_path / 'dem.tif'
    domain = np.ones(shape, dtype='float32')
    domain[4, 20] = -9999  # DEM-invalid coast neighbor does not disqualify target.
    with rasterio.open(dem, 'w', **profile) as dst:
        dst.write(domain, 1)
    outputs = get_crest_parameters(folder, tmp_path / 'out', dem=dem)
    with rasterio.open(outputs['wm']) as src:
        data = src.read(1)
        assert data[3, 511] == pytest.approx(2085)
        assert data[3, 20] == pytest.approx(1251)
        assert data[3, 514] == pytest.approx(1251)
        for row, col in missing[:4]:
            assert data[row, col] == -9999
        assert data[4, 20] == -9999
        assert src.tags()['filled_input_cells'] == '3'
    with rasterio.open(tmp_path / 'crest_diagnostics/crest_filled_mask.tif') as src:
        mask = src.read(1)
        assert (mask == 1).sum() == 3
        assert mask[4, 20] == -9999
        assert not src.is_tiled and src.compression == rasterio.enums.Compression.deflate
    with rasterio.open(folder / 'SNDPPT_M_sl1_250m.tif') as src:
        assert np.isnan(src.read(1)[3, 511])  # Original inputs remain unchanged.


def test_dem_requires_alignment(tmp_path):
    folder = inputs(tmp_path)
    dem = tmp_path / 'dem.tif'
    with rasterio.open(folder / 'BDRICM_M_250m.tif') as src:
        profile = src.profile.copy()
    profile.update(transform=from_origin(1, 1, .1, .1))
    with rasterio.open(dem, 'w', **profile) as dst:
        dst.write(np.ones((1, 5), dtype='float32'), 1)
    with pytest.raises(ValueError, match='does not match'):
        get_crest_parameters(folder, tmp_path / 'out', dem=dem)


def test_coastal_exception_uses_opposite_dem_nodata(tmp_path):
    folder = tmp_path / 'soil'
    folder.mkdir()
    shape = (8, 8)
    profile = dict(driver='GTiff', count=1, width=8, height=8, dtype='float32',
                   crs='EPSG:4326', transform=from_origin(0, 1, .01, .01), nodata=-9999)
    holes = [(3, 2), (3, 3), (3, 4), (6, 2), (6, 3), (0, 6), (0, 7), (6, 6), (5, 6)]
    names = [(f'{prefix}_M_sl{level}_250m.tif', value)
             for prefix, value in [('SNDPPT', 95), ('CLYPPT', 2)]
             for level in range(1, 8)] + [('BDRICM_M_250m.tif', 300)]
    for name, value in names:
        data = np.full(shape, value, dtype='float32')
        for row, col in holes:
            data[row, col] = -9999
        if name == 'BDRICM_M_250m.tif':
            data[2, 2:5] = 400  # Donors opposite the invalid DEM cells.
        with rasterio.open(folder / name, 'w', **profile) as dst:
            dst.write(data, 1)
    dem = tmp_path / 'dem.tif'
    domain = np.ones(shape, dtype='float32')
    domain[4, 2:5] = np.nan
    domain[4, 7] = -9999  # Diagonal coast: donor at (6, 5), target at (5, 6).
    with rasterio.open(dem, 'w', **profile) as dst:
        dst.write(domain, 1)
    paths = get_crest_parameters(folder, tmp_path / 'out', dem=dem)
    with rasterio.open(paths['wm']) as src:
        data = src.read(1)
        np.testing.assert_allclose(data[3, 2:5], 1668)
        assert (data[6, 2:4] == -9999).all()  # Interior connected holes stay missing.
        assert (data[0, 6:8] == -9999).all()  # Array edge is not DEM NoData.
        assert (data[4, 2:5] == -9999).all()
        assert data[5, 6] == pytest.approx(1251)
        assert data[6, 6] == -9999
        assert src.tags()['coastal_filled_cells'] == '4'
    with rasterio.open(tmp_path / 'crest_diagnostics/crest_filled_mask.tif') as src:
        mask = src.read(1)
        assert (mask[3, 2:5] == 2).all()
        assert mask[5, 6] == 2
        assert (mask == 2).sum() == 4

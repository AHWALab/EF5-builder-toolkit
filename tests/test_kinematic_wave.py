"""Numerical and raster-contract checks for KW inference."""
import pickle

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from ef5_builder import get_kw_alpha0, get_kw_parameters


class IdentityScaler:
    def transform(self, x):
        return x


class AlphaModel:
    def predict(self, x):
        # Verifies area logging, predictor order and precipitation conversion.
        return x[:, 0] + x[:, 2]


class BetaModel:
    def predict(self, x):
        return np.full(len(x), -0.1)


def grid(tmp_path, name, values):
    path = tmp_path / name
    with rasterio.open(path, 'w', driver='GTiff', height=2, width=3,
                       count=1, dtype='float32', crs='EPSG:4326',
                       transform=from_origin(0, 2, 1, 1), nodata=-9999,
                       tiled=False, compress='none') as dst:
        dst.write(np.asarray(values, dtype='float32').reshape(2, 3), 1)
    return path


def check_storage(path):
    with rasterio.open(path) as src:
        assert not src.profile.get('tiled')
        assert src.compression == rasterio.enums.Compression.deflate
        assert src.nodata == -9999
        assert src.transform == from_origin(0, 2, 1, 1)
        return src.read(1)


def test_parameters(tmp_path):
    area = grid(tmp_path, 'area.tif', [10, 10, -9999, 0, 10, 10])
    temp = grid(tmp_path, 'temp.tif', [20]*6)
    precip = grid(tmp_path, 'precip.tif', [12]*6)
    rr = grid(tmp_path, 'rr.tif', [.01]*6)
    fac = grid(tmp_path, 'fac.tif', [8, 7, 9, 9, 9, -9999])
    for name, model in [('scaler', IdentityScaler()), ('alpha_model', AlphaModel()),
                        ('beta_model', BetaModel())]:
        (tmp_path / f'{name}.p').write_bytes(pickle.dumps(model))
    args = (area, temp, precip, rr, fac, tmp_path / 'out')
    kwargs = dict(model_dir=tmp_path, precipitation_factor=1/12, layer_th=7, self_fam=True)
    result = get_kw_parameters(*args, **kwargs)
    assert result['th'] == result['layer_th'] == 7
    with rasterio.open(result['alpha']) as src:
        assert src.tags()['layer_th'] == '7'
        assert src.tags()['control_th_requirement'] == 'strictly greater than layer_th'
    assert result['self_fam'] is True
    alpha = check_storage(result['alpha']).ravel()
    beta = check_storage(result['beta']).ravel()
    np.testing.assert_allclose(alpha[[0, 4]], 100)
    np.testing.assert_allclose(beta[[0, 4]], np.exp(-1))
    assert np.all(alpha[[1, 2, 3, 5]] == -9999)
    assert np.all(beta[[1, 2, 3, 5]] == -9999)
    for invalid in (-1, np.nan, np.inf):
        with pytest.raises(ValueError, match='finite and nonnegative'):
            get_kw_parameters(*args, **{**kwargs, 'layer_th': invalid})
    with pytest.raises(FileExistsError):
        get_kw_parameters(*args, **kwargs)


def test_annual_alpha0(tmp_path):
    slope = grid(tmp_path, 'slope.tif', [.01, 0, .01, .01, -9999, -.01])
    fac = grid(tmp_path, 'fac.tif', [0, 1, -9999, 2, 2, 2])
    first = grid(tmp_path, 'manning_2001.tif', [.1, .1, .1, 0, .1, .1])
    second = grid(tmp_path, 'manning_2002.tif', [.2, .2, .2, .2, .2, .2])
    result = get_kw_alpha0([first, second], slope, fac, tmp_path / 'out', self_fam=False)
    a = check_storage(result[first]).ravel()
    b = check_storage(result[second]).ravel()
    np.testing.assert_allclose(a[:2], 1)
    np.testing.assert_allclose(b[[0, 1, 3]], 2**.6)
    assert np.all(a[2:] == -9999)
    assert np.all(b[[2, 4, 5]] == -9999)
    single = get_kw_alpha0(first, slope, fac, tmp_path / 'single', self_fam=False)
    np.testing.assert_array_equal(check_storage(single[first]), a.reshape(2, 3))


def test_invalid_alpha0_and_alignment(tmp_path):
    n = grid(tmp_path, 'n.tif', [.1]*6)
    flat = grid(tmp_path, 'flat.tif', [0]*6)
    fac = grid(tmp_path, 'fac.tif', [1]*6)
    with pytest.raises(ValueError, match='No valid alpha0 below 1000'):
        get_kw_alpha0(n, flat, fac, tmp_path / 'out', self_fam=True)
    assert not list((tmp_path / 'out').glob('*.tif'))
    with rasterio.open(fac, 'r+') as src:
        src.transform = from_origin(1, 2, 1, 1)
    with pytest.raises(ValueError, match='already be aligned'):
        get_kw_alpha0(n, flat, fac, tmp_path / 'out', self_fam=True)


def test_self_fam_is_explicit_and_checked(tmp_path):
    n = grid(tmp_path, 'n.tif', [.1]*6)
    slope = grid(tmp_path, 'slope.tif', [.01]*6)
    fac = grid(tmp_path, 'fac.tif', [0, 1, 2, 3, 4, 5])
    args = (n, slope, fac, tmp_path / 'out')
    with pytest.raises(TypeError, match='self_fam'):
        get_kw_alpha0(*args)
    with pytest.raises(ValueError, match='explicitly True or False'):
        get_kw_alpha0(*args, self_fam='false')
    with pytest.raises(ValueError, match='Valid FAC values must be >= 1'):
        get_kw_alpha0(*args, self_fam=True)
    result = get_kw_alpha0(*args, self_fam=False)
    with rasterio.open(result[n]) as src:
        assert src.tags()['self_fam'] == 'false'
    with rasterio.open(fac, 'r+') as dst:
        dst.write(np.ones((2, 3), dtype='float32'), 1)
    result = get_kw_alpha0(*args, self_fam=True, overwrite=True)
    with rasterio.open(result[n]) as src:
        assert src.tags()['self_fam'] == 'true'


@pytest.mark.parametrize('units,value', [
    ('in', 12), ('in/year', 12), ('in/month', 1),
    ('mm', 304.8), ('mm/year', 304.8), ('mm/month', 25.4),
])
def test_precipitation_units(tmp_path, units, value):
    inputs = [grid(tmp_path, name, [v]*6) for name, v in
              [('area.tif', 10), ('temp.tif', 20), ('precip.tif', value),
               ('rr.tif', .01), ('fac.tif', 8)]]
    for name, model in [('scaler', IdentityScaler()), ('alpha_model', AlphaModel()),
                        ('beta_model', BetaModel())]:
        (tmp_path / f'{name}.p').write_bytes(pickle.dumps(model))
    kwargs = dict(model_dir=tmp_path, precipitation_units=units,
                  layer_th=7, self_fam=True)
    result = get_kw_parameters(*inputs, tmp_path / 'out', **kwargs)
    np.testing.assert_allclose(check_storage(result['alpha']), 100, rtol=1e-6)
    with rasterio.open(result['alpha']) as src:
        assert src.tags()['precipitation_input_units'] == units
    with pytest.raises(ValueError, match='not both'):
        get_kw_parameters(*inputs, tmp_path / 'other', **kwargs, precipitation_factor=1)
    with pytest.raises(ValueError, match='Unsupported precipitation_units'):
        get_kw_parameters(*inputs, tmp_path / 'other',
                          **{**kwargs, 'precipitation_units': 'unknown'})


def test_default_threshold_warning(tmp_path):
    inputs = [grid(tmp_path, name, [v]*6) for name, v in
              [('area.tif', 10), ('temp.tif', 20), ('precip.tif', 1),
               ('rr.tif', .01), ('fac.tif', 3)]]
    for name, model in [('scaler', IdentityScaler()), ('alpha_model', AlphaModel()),
                        ('beta_model', BetaModel())]:
        (tmp_path / f'{name}.p').write_bytes(pickle.dumps(model))
    with pytest.warns(UserWarning, match='TH is 2.*strictly greater'):
        result = get_kw_parameters(*inputs, tmp_path/'out', model_dir=tmp_path,
                                   precipitation_units='in/month', self_fam=False)
    assert result['layer_th'] == 2
    np.testing.assert_allclose(check_storage(result['alpha']), 100)


@pytest.mark.filterwarnings('error:X does not have valid feature names:UserWarning')
def test_bundled_models_work_outside_repository(tmp_path, monkeypatch):
    """Default package resources and an explicit override produce identical rasters."""
    from importlib.resources import files
    pytest.importorskip('sklearn')
    inputs = [grid(tmp_path, name, [v]*6) for name, v in
              [('area.tif', 10), ('temp.tif', 20), ('precip.tif', 1),
               ('rr.tif', .01), ('fac.tif', 8)]]
    bundled = files('ef5_builder').joinpath('models').joinpath('kw')
    custom = tmp_path/'custom_models'
    custom.mkdir()
    for name in ('scaler.p', 'alpha_model.p', 'beta_model.p'):
        (custom/name).write_bytes(bundled.joinpath(name).read_bytes())
    monkeypatch.chdir(tmp_path)
    kwargs = dict(precipitation_units='in/month', self_fam=True)
    with pytest.warns(UserWarning, match='TH is 2'):
        default = get_kw_parameters(*inputs, tmp_path/'default', **kwargs)
    with pytest.warns(UserWarning, match='TH is 2'):
        explicit = get_kw_parameters(*inputs, tmp_path/'explicit', model_dir=custom, **kwargs)
    for key in ('alpha', 'beta'):
        np.testing.assert_array_equal(check_storage(default[key]), check_storage(explicit[key]))

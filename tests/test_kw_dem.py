"""Analytical terrain and output-format checks."""
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from pyproj import CRS
from ef5_builder import get_kw_alpha0_from_dem


def write(path, a, crs, transform):
    with rasterio.open(path, 'w', driver='GTiff', count=1, height=7, width=7,
                       dtype='float32', crs=crs, transform=transform, nodata=-9999) as dst:
        dst.write(a.astype('float32'), 1)
    return path


@pytest.mark.parametrize('manning_name, output_name', [
    ('n.tif', 'kw_alpha0.tif'),
    ('manning_n_2001_1km.tif', 'kw_alpha0_2001.tif'),
])
@pytest.mark.parametrize('crs', ['EPSG:32614', 'EPSG:2277', 'EPSG:4326'])
def test_plane_and_invalid(tmp_path, crs, manning_name, output_name):
    geographic = CRS(crs).is_geographic
    pixel = .01 if geographic else 10
    t = from_origin(-100 if geographic else 500000, 45 if geographic else 3000000, pixel, pixel)
    y,x = np.indices((7,7))
    z = x*10.
    dem = write(tmp_path/'dem.tif', z, crs, t)
    n = write(tmp_path/manning_name, np.full((7,7), .1), crs, t)
    out = get_kw_alpha0_from_dem(n, dem, tmp_path/'out')
    assert out.name == output_name
    dx = (CRS(crs).get_geod().inv(-100,45-3.5*.01,-99.98,45-3.5*.01)[2]/2
          if geographic else 10*CRS(crs).axis_info[0].unit_conversion_factor)
    with rasterio.open(out) as src:
        assert src.read(1)[3,3] == pytest.approx((.1/np.sqrt(10/dx))**.6, rel=1e-6)
        assert np.all(src.read(1)[0] == -9999)
        assert src.transform == t
        assert src.dtypes == ('float32',) and src.nodata == -9999
        assert src.compression == rasterio.enums.Compression.deflate
        assert not src.profile.get('tiled')
    write(dem, np.zeros((7,7)), crs, t)
    out = get_kw_alpha0_from_dem(n, dem, tmp_path/'flat')
    with rasterio.open(out) as src:
        assert np.all(src.read(1) == -9999)
    out = get_kw_alpha0_from_dem(n, dem, tmp_path/'floor', min_slope=.001)
    with rasterio.open(out) as src:
        np.testing.assert_allclose(src.read(1)[1:-1,1:-1], (.1/np.sqrt(.001))**.6)
    z[3,3] = -9999
    write(dem, z, crs, t)
    rough = np.full((7,7), .1); rough[1,1] = 0; rough[1,5] = np.nan
    write(n, rough, crs, t)
    out = get_kw_alpha0_from_dem(n, dem, tmp_path/'missing')
    with rasterio.open(out) as src:
        a = src.read(1)
        assert np.all(a[2:5,2:5] == -9999)
        assert a[1,1] == a[1,5] == -9999
    for bad in (0,-1,np.nan):
        with pytest.raises(ValueError, match='min_slope'):
            get_kw_alpha0_from_dem(n, dem, tmp_path/'bad', min_slope=bad)

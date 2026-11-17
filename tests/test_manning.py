"""Known-class, mosaic, metadata and failure checks for annual roughness."""
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from ef5_builder import annual_manning_from_modis


def tile(path, values, *, x=0, y=2, pixel=1, nodata=255, crs='EPSG:4326'):
    data = np.asarray(values, dtype='float32')
    with rasterio.open(path, 'w', driver='GTiff', width=data.shape[1], height=data.shape[0],
                       count=1, dtype='float32', crs=crs, transform=from_origin(x, y, pixel, pixel), nodata=nodata) as dst:
        dst.write(data, 1)
        dst.set_band_description(1, 'LC_Type2')
    return path


def test_crosswalk_uses_class_meanings_and_output_format(tmp_path):
    inputs = tmp_path/'input'; inputs.mkdir()
    # Literal verified Table 5 values, including the renumbered UMD classes.
    tile(inputs/'LC_Type2_2001.tif', [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 255]])
    result = annual_manning_from_modis(inputs, tmp_path/'output')
    assert result[2001].name == 'manning_n_2001.tif'
    with rasterio.open(result[2001]) as src:
        np.testing.assert_allclose(src.read(1), [[.001, .1, .1, .1, .1, .1, .3, .2, .1, .3, .17, .035, .015, -9999]])
        assert src.dtypes == ('float32',) and src.nodata == -9999
        assert src.crs.to_epsg() == 4326 and src.transform == from_origin(0, 2, 1, 1)
        assert src.tags()['year'] == '2001'
        assert src.tags()['reference_table'] == '5'
        assert src.tags()['units'] == 's m^-1/3'
        assert src.compression == rasterio.enums.Compression.deflate
        assert not src.profile.get('tiled')


def test_multiple_years_tiles_gaps_and_fill_overlaps(tmp_path):
    inputs=tmp_path/'input'; inputs.mkdir()
    tile(inputs/'MCD12Q1.A2001001.h01v01.061.2025123000000.tif', [[0, 255], [1, 6]])
    tile(inputs/'LC_Type2_2001_tile2.tif', [[12, 13], [6, 7]], x=1)
    tile(inputs/'LC_Type2_2001_tile3.tif', [[10]], x=4)
    tile(inputs/'LC_Type2_20250101.tiff', [[13]])
    result=annual_manning_from_modis(inputs,tmp_path/'output')
    assert set(result)=={2001,2025}
    with rasterio.open(result[2001]) as src:
        np.testing.assert_allclose(src.read(1), [[.001,.035,.015,-9999,.17],[.1,.3,.2,-9999,-9999]])


def test_conflict_detects_classes_even_if_coefficients_match(tmp_path):
    inputs=tmp_path/'input'; inputs.mkdir()
    tile(inputs/'2001_a.tif',[[1]])
    tile(inputs/'2001_b.tif',[[2]])
    with pytest.raises(ValueError,match='Conflicting overlapping'):
        annual_manning_from_modis(inputs,tmp_path/'out')
    assert not (tmp_path/'out/manning_n_2001.tif').exists()
    assert not list((tmp_path/'out').glob('.ef5-manning-*'))


@pytest.mark.parametrize('value',[11,14,16,17,-1,1.5,float('nan')])
def test_unexpected_class_rejected(tmp_path,value):
    inputs=tmp_path/'input'; inputs.mkdir()
    tile(inputs/'2001.tif',[[value]])
    with pytest.raises(ValueError,match='Unexpected LC_Type2'):
        annual_manning_from_modis(inputs,tmp_path/'out')


def test_barren_snow_provisional_coefficient_and_override(tmp_path):
    inputs=tmp_path/'input'; inputs.mkdir()
    tile(inputs/'2001.tif',[[15, 12, 255]])
    result=annual_manning_from_modis(inputs,tmp_path/'out')
    with rasterio.open(result[2001]) as src:
        np.testing.assert_allclose(src.read(1),[[.025,.035,-9999]])
        assert src.tags()['class15_status']=='user-selected provisional'
        assert src.tags()['class15_reference'].startswith('https://www.hec.usace.army.mil/')
    annual_manning_from_modis(inputs,tmp_path/'out',class15_n=.03,overwrite=True)
    with rasterio.open(result[2001]) as src:
        np.testing.assert_allclose(src.read(1),[[.03,.035,-9999]])
        assert src.tags()['class15_n']=='0.03'


@pytest.mark.parametrize('coefficient',[0,-.1,float('nan'),float('inf'),True,'0.025'])
def test_invalid_class15_coefficient(tmp_path,coefficient):
    with pytest.raises(ValueError,match='class15_n'):
        annual_manning_from_modis(tmp_path,tmp_path/'out',class15_n=coefficient)


@pytest.mark.parametrize('name',['landcover.tif','landcover_2001_2002.tif'])
def test_invalid_year_name_rejected(tmp_path,name):
    inputs=tmp_path/'input'; inputs.mkdir()
    tile(inputs/name,[[1]])
    with pytest.raises(ValueError,match='year|Year'):
        annual_manning_from_modis(inputs,tmp_path/'out')


def test_year_selection_missing_and_overwrite(tmp_path):
    inputs=tmp_path/'input'; inputs.mkdir()
    tile(inputs/'2001.tif',[[1]])
    tile(inputs/'2002.tif',[[12]])
    with pytest.raises(ValueError,match='Missing annual'):
        annual_manning_from_modis(inputs,tmp_path/'out',years=[2003])
    result=annual_manning_from_modis(inputs,tmp_path/'out',years=[2001])
    with pytest.raises(FileExistsError):
        annual_manning_from_modis(inputs,tmp_path/'out',years=[2001])
    tile(inputs/'2001.tif',[[11]])
    original=result[2001].read_bytes()
    with pytest.raises(ValueError):
        annual_manning_from_modis(inputs,tmp_path/'out',years=[2001],overwrite=True)
    assert result[2001].read_bytes()==original


def test_misaligned_grid_and_zero_nodata_rejected(tmp_path):
    inputs=tmp_path/'input'; inputs.mkdir()
    tile(inputs/'2001_a.tif',[[1]])
    tile(inputs/'2001_b.tif',[[1]],x=.5)
    with pytest.raises(ValueError,match='align'):
        annual_manning_from_modis(inputs,tmp_path/'out')
    tile(inputs/'2001_b.tif',[[0]],nodata=0)
    with pytest.raises(ValueError,match='conflicts with a valid'):
        annual_manning_from_modis(inputs,tmp_path/'out')


def test_filename_filter_ignores_unrelated_rasters(tmp_path):
    inputs=tmp_path/'input'; inputs.mkdir()
    tile(inputs/'MCD12Q1_UMD_2001_Global_EPSG4326-0000000000-0000000000.tif',[[1]])
    tile(inputs/'DEM.tif',[[900]])
    result=annual_manning_from_modis(inputs,tmp_path/'out',file_pattern='MCD12Q1_UMD_*.tif')
    assert list(result)==[2001]


@pytest.mark.parametrize('year',[2000,2026,2101])
def test_year_not_restricted_to_original_dataset_range(tmp_path,year):
    inputs=tmp_path/'input'; inputs.mkdir()
    tile(inputs/f'LC_Type2_{year}.tif',[[13]])
    result=annual_manning_from_modis(inputs,tmp_path/'out',years=[year])
    assert list(result)==[year]


def test_explicit_year_template_disambiguates_and_filters(tmp_path):
    inputs=tmp_path/'input'; inputs.mkdir()
    tile(inputs/'cover2026_export2027_tile01.tif',[[1]])
    tile(inputs/'unrelated.tif',[[17]])
    result=annual_manning_from_modis(inputs,tmp_path/'out',
                                   filename_template='coverYYYY_export*_tile*.tif')
    assert list(result)==[2026]


@pytest.mark.parametrize('template',['cover*.tif','YYYY_YYYY.tif','folder/YYYY.tif'])
def test_invalid_year_template(tmp_path,template):
    with pytest.raises(ValueError,match='filename_template'):
        annual_manning_from_modis(tmp_path,tmp_path/'out',filename_template=template)

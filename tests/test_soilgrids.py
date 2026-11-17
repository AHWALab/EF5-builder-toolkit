"""Regional download checks with local rasters standing in for remote sources."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from ef5_builder import download_soilgrids_2017, download_soilgrids_v2, resample_and_subset
from ef5_builder import soilgrids as soil


def raster(path, values, transform=None, crs="EPSG:4326"):
    data = np.array(values, dtype="float32")
    with rasterio.open(path, "w", driver="GTiff", count=1, dtype="float32",
                       width=data.shape[1], height=data.shape[0], crs=crs,
                       transform=transform or from_origin(0, 2, 1, 1), nodata=-32768) as dst:
        dst.write(data, 1)
    return path


def domain(tmp_path, bounds=(0, 0, 2, 2)):
    west, south, east, north = bounds
    return raster(tmp_path / "domain.tif", [[1]], from_origin(west, north, east-west, north-south))


def remote(monkeypatch, path):
    calls = []
    def open_source(url):
        calls.append(url)
        return rasterio.open(path)
    monkeypatch.setattr(soil, "_open_source", open_source)
    return calls


def test_v2_native_percent_zero_and_nodata(tmp_path, monkeypatch):
    source = raster(tmp_path / "source.tif", [[350, 0], [-32768, 1000]])
    template = raster(tmp_path / "dem.tif", [[1, -32768], [1, 1]])
    calls = remote(monkeypatch, source)
    outputs = download_soilgrids_v2(tmp_path / "out", dem=domain(tmp_path),
                                   properties="sand", depths="0-5cm")
    assert calls == [soil.V2_SERVER + "/sand/sand_0-5cm_mean.vrt"]
    path = outputs["sand_0-5cm"]
    assert path.is_absolute() and path.name == "sand_0-5cm_mean_percent.tif"
    with rasterio.open(path) as src:
        np.testing.assert_allclose(src.read(1), [[35, 0], [-9999, 100]])
        assert src.transform == from_origin(0, 2, 1, 1)
        assert src.crs.to_epsg() == 4326
        assert src.dtypes == ("float32",) and src.nodata == -9999
        assert src.tags()["source_units"] == "g/kg"
        assert src.tags()["units"] == "%"
        assert src.tags()["depth_type"] == "interval"
    assert not list((tmp_path / "out").glob(".ef5-soil-*"))


def test_v2_dem_extent_percent_conversion_and_valid_zero(tmp_path, monkeypatch):
    remote(monkeypatch, raster(tmp_path / "source.tif", [[350, 0], [-32768, 1000]]))
    result = download_soilgrids_v2(tmp_path / "out", dem=domain(tmp_path),
                                  properties="clay", depths="100-200cm")
    with rasterio.open(result["clay_100-200cm"]) as src:
        np.testing.assert_allclose(src.read(1), [[35, 0], [-9999, 100]])
        assert src.tags()["depth_top_cm"] == "100"
        assert src.tags()["depth_bottom_cm"] == "200"


def test_former_source_names_and_unscaled_percent_and_bedrock_cm(tmp_path, monkeypatch):
    source = raster(tmp_path / "source.tif", [[35, 0], [-32768, 100]])
    calls = remote(monkeypatch, source)
    result = download_soilgrids_2017(tmp_path / "out", dem=domain(tmp_path),
                                    properties=("sand", "clay", "silt"), depths=("sl1", "sl7"))
    assert len(result) == 7
    assert calls[0].endswith("SNDPPT_M_sl1_250m_ll.tif")
    assert calls[-1].endswith("BDRICM_M_250m_ll.tif")
    assert result["sand_sl1"].name == "SNDPPT_M_sl1_250m.tif"
    assert result["bedrock"].name == "BDRICM_M_250m.tif"
    for key, path in result.items():
        with rasterio.open(path) as src:
            np.testing.assert_allclose(src.read(1), [[35, 0], [-9999, 100]])
            assert src.tags()["units"] == ("cm" if key == "bedrock" else "%")
            if key.endswith("sl7"):
                assert src.tags()["depth_cm"] == "200"


def test_average_resampling_with_nodata(tmp_path, monkeypatch):
    source = raster(tmp_path / "source.tif", [[100, 300], [-32768, 800]])
    remote(monkeypatch, source)
    template = raster(tmp_path / "dem.tif", [[1]], from_origin(0, 2, 2, 2))
    downloaded = download_soilgrids_v2(tmp_path / "out", dem=domain(tmp_path),
                                       properties="sand", depths="0-5cm")
    result = resample_and_subset(downloaded["sand_0-5cm"], tmp_path / "aligned.tif",
                                 template, resampling="average")
    with rasterio.open(result) as src:
        np.testing.assert_allclose(src.read(1), [[40]], atol=1e-5)
        assert src.transform == from_origin(0, 2, 2, 2)
        assert src.dtypes == ("float32",) and src.nodata == -9999



def test_projected_source_is_reprojected_to_dem_grid(tmp_path, monkeypatch):
    source = raster(tmp_path / "source.tif", [[350, 350], [350, 350]],
                    from_origin(0, 222684.2085, 111342.10425, 111342.10425), "EPSG:3857")
    remote(monkeypatch, source)
    template = raster(tmp_path / "dem.tif", [[1, 1], [1, 1]])
    downloaded = download_soilgrids_v2(tmp_path / "out", dem=domain(tmp_path),
                                       properties="sand", depths="0-5cm")
    with rasterio.open(downloaded["sand_0-5cm"]) as src:
        assert src.crs.to_epsg() == 3857
        assert src.res == (111342.10425, 111342.10425)
    result = resample_and_subset(downloaded["sand_0-5cm"], tmp_path / "aligned.tif", template)
    with rasterio.open(result) as src:
        np.testing.assert_allclose(src.read(1), np.full((2, 2), 35))
        assert src.crs.to_epsg() == 4326
        assert src.transform == from_origin(0, 2, 1, 1)



@pytest.mark.parametrize("kwargs,match", [
    ({"properties": "bedrock"}, "properties"),
    ({"properties": ("sand", "sand")}, "duplicates"),
    ({"depths": "sl1"}, "depths"),
    ({"depths": ()}, "depths"),
    ({"timeout": 0}, "timeout"),
    ({"retries": -1}, "retries"),
])
def test_invalid_arguments_before_remote_read(tmp_path, monkeypatch, kwargs, match):
    def unexpected(url):
        pytest.fail("Invalid arguments must not access the archive")
    monkeypatch.setattr(soil, "_open_source", unexpected)
    with pytest.raises(ValueError, match=match):
        download_soilgrids_v2(tmp_path / "out", **(dict(dem=domain(tmp_path)) | kwargs))
    assert not (tmp_path / "out").exists()


def test_existing_output_preflight_and_failed_overwrite_keeps_original(tmp_path, monkeypatch):
    source = raster(tmp_path / "source.tif", [[-32768, -32768], [-32768, -32768]])
    calls = remote(monkeypatch, source)
    out = tmp_path / "out"
    out.mkdir()
    existing = out / "sand_0-5cm_mean_percent.tif"
    existing.write_bytes(b"original")
    options = dict(dem=domain(tmp_path), properties="sand", depths="0-5cm")
    with pytest.raises(FileExistsError):
        download_soilgrids_v2(out, **options)
    assert not calls
    with pytest.raises(ValueError, match="No valid soil values"):
        download_soilgrids_v2(out, **options, overwrite=True)
    assert existing.read_bytes() == b"original"
    assert list(out.iterdir()) == [existing]


def test_default_layers_and_depths_are_not_interchanged(tmp_path, monkeypatch):
    calls = remote(monkeypatch, raster(tmp_path / "source.tif", [[35, 0], [1, 100]]))
    former = download_soilgrids_2017(tmp_path / "former", dem=domain(tmp_path))
    latest = download_soilgrids_v2(tmp_path / "v2", dem=domain(tmp_path))
    assert len(former) == 15 and len(latest) == 12
    expected = {f"{code}_M_sl{i}_250m.tif" for code in ("SNDPPT", "CLYPPT") for i in range(1, 8)}
    expected.add("BDRICM_M_250m.tif")
    assert {path.name for path in former.values()} == expected
    assert "bedrock" in former and "bedrock" not in latest
    assert "sand_sl7" in former and "sand_100-200cm" in latest
    assert not any("sl" in key for key in latest if key.startswith("sand"))


def test_native_subset_does_not_resample(tmp_path, monkeypatch):
    data = np.arange(16).reshape(4, 4)
    remote(monkeypatch, raster(tmp_path / "source.tif", data, from_origin(0, 2, .5, .5)))
    result = download_soilgrids_2017(tmp_path / "out", dem=domain(tmp_path, (.6, .4, 1.4, 1.6)),
                                   properties="sand", depths="sl1", include_bedrock=False)
    with rasterio.open(result["sand_sl1"]) as src:
        np.testing.assert_array_equal(src.read(1), data[:, 1:3])
        assert src.transform == from_origin(.5, 2, .5, .5)
        assert src.res == (.5, .5)


def test_resampling_template_mask_rectangular_pixels_and_overwrite(tmp_path):
    source = raster(tmp_path / "source.tif", [[10, 20], [30, 40]])
    template = raster(tmp_path / "dem.tif", [[1, -32768, 1, 1], [1, 1, 1, 1]],
                      from_origin(0, 2, .5, 1))
    output = resample_and_subset(source, tmp_path / "aligned.tif", template)
    with rasterio.open(output) as src:
        np.testing.assert_array_equal(src.read(1), [[10, 10, 20, 20], [30, 30, 40, 40]])
        assert src.res == (.5, 1) and src.shape == (2, 4)
        assert src.dtypes == ("float32",) and src.nodata == -9999
    with pytest.raises(FileExistsError):
        resample_and_subset(source, output, template)
    resample_and_subset(source, output, template, mask_template=True, overwrite=True)
    with rasterio.open(output) as src:
        assert src.read(1)[0, 1] == -9999
    with pytest.raises(ValueError, match="must not replace"):
        resample_and_subset(source, source, template, overwrite=True)
    with pytest.raises(ValueError, match="resampling"):
        resample_and_subset(source, tmp_path / "invalid.tif", template, resampling="mode")


def test_projected_dem_defines_native_download_extent(tmp_path, monkeypatch):
    source = raster(tmp_path / "source.tif", [[35, 35], [35, 35]])
    remote(monkeypatch, source)
    dem = raster(tmp_path / "projected-dem.tif", [[1]],
                 from_origin(0, 222684.2085, 222684.2085, 222684.2085), "EPSG:3857")
    result = download_soilgrids_2017(tmp_path / "out", dem=dem,
                                   properties="sand", depths="sl1", include_bedrock=False)
    with rasterio.open(result["sand_sl1"]) as src:
        assert src.crs.to_epsg() == 4326
        assert src.res == (1, 1) and src.shape == (2, 2)
        np.testing.assert_array_equal(src.read(1), [[35, 35], [35, 35]])


def test_invalid_dem_crs_is_rejected_before_remote_read(tmp_path, monkeypatch):
    dem = raster(tmp_path / "no-crs.tif", [[1]], crs=None)
    def unexpected(url):
        pytest.fail("Invalid DEM must not access the archive")
    monkeypatch.setattr(soil, "_open_source", unexpected)
    with pytest.raises(ValueError, match="DEM"):
        download_soilgrids_v2(tmp_path / "out", dem=dem)
    assert not (tmp_path / "out").exists()

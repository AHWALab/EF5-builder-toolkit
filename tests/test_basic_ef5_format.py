"""Regression coverage for the GeoTIFF layout supported by EF5 1.3."""
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from ef5_builder import prepare_from_dem, prepare_hydrosheds


@pytest.mark.parametrize("derive", [False, True])
def test_basic_outputs_are_striped_deflate_and_preserve_dem(tmp_path, derive):
    if derive:
        pytest.importorskip("pysheds")
    transform = from_origin(-92, 40, 0.01, 0.01)
    elevation = np.tile(np.arange(9, 0, -1, dtype="float32"), (9, 1))
    inputs = {}
    for name, values in {
        "dem": elevation,
        "facc": np.tile(np.arange(1, 10, dtype="float32"), (9, 1)),
        "fdir": np.ones((9, 9), dtype="float32"),
    }.items():
        path = tmp_path / f"input_{name}.tif"
        with rasterio.open(
            path, "w", driver="GTiff", width=9, height=9, count=1,
            dtype="float32", nodata=-9999, crs="EPSG:4326",
            transform=transform, tiled=True, compress="deflate",
        ) as dst:
            dst.write(values, 1)
        inputs[name] = path
    if derive:
        outputs = prepare_from_dem(inputs["dem"], tmp_path / "out", condition=False)
    else:
        outputs = prepare_hydrosheds(**inputs, output_dir=tmp_path / "out")
    for path in outputs.values():
        with rasterio.open(path) as src:
            assert not src.profile.get("tiled", False)
            assert src.compression == rasterio.enums.Compression.deflate
            assert src.dtypes == ("float32",)
            assert src.nodata == -9999
            assert src.transform == transform
            assert src.crs.to_epsg() == 4326
            assert src.shape == elevation.shape
    with rasterio.open(outputs["dem"]) as src:
        np.testing.assert_array_equal(src.read(1), elevation)

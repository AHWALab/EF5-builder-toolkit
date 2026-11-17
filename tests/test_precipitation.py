"""Offline download and conversion checks using raster fixtures and HTTP stubs."""

import base64
import gzip
from datetime import datetime, timezone
from io import BytesIO
from urllib.error import HTTPError, URLError

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from ef5_builder import download_precipitation
from ef5_builder import precipitation as precip


@pytest.fixture
def imerg(tmp_path):
    path = tmp_path / "imerg-source.tif"
    data = np.zeros((1800, 3600), dtype="uint16")
    data[500:502, 800:802] = [[10, 29999], [0, 25]]
    with rasterio.open(
        path, "w", driver="GTiff", width=3600, height=1800, count=1,
        crs="EPSG:4326", transform=from_origin(-180, 90, 0.1, 0.1),
        dtype="uint16", compress="deflate",
    ) as dst:
        dst.write(data, 1)
    return path


@pytest.fixture
def mrms(tmp_path):
    path = tmp_path / "mrms-source.tif"
    with rasterio.open(
        path, "w", driver="GTiff", width=3, height=2, count=1,
        crs="EPSG:4326", transform=from_origin(-100, 40, 0.1, 0.1),
        dtype="float32", nodata=-999,
    ) as dst:
        dst.write(np.array([[1, -1, -3], [0, 2.5, -999]], dtype="float32"), 1)
    return path


def stub_download(monkeypatch, fixture, compressed=False):
    calls = []

    def download(url, destination, email, timeout, retries):
        calls.append((url, email))
        payload = fixture.read_bytes()
        destination.write_bytes(gzip.compress(payload) if compressed else payload)

    monkeypatch.setattr(precip, "_download", download)
    return calls


def test_imerg_midnight_scaling_nodata_and_end_timestamps(tmp_path, monkeypatch, imerg):
    calls = stub_download(monkeypatch, imerg)
    paths = download_precipitation(
        "imerg", "2020-10-08T23:30", "2020-10-09T00:30Z", tmp_path / "out",
        email="test@example.com", bounds=(-100, 39.8, -99.8, 40),
    )
    assert [p.name for p in paths] == ["imerg.202010090000.tif", "imerg.202010090030.tif"]
    assert "2020/10/08/gis/" in calls[0][0]
    assert "S233000-E235959.1410.V07B.tif" in calls[0][0]
    assert "2020/10/09/gis/" in calls[1][0]
    assert "S000000-E002959.0000.V07B.tif" in calls[1][0]
    for path in paths:
        assert path.is_absolute()
        with rasterio.open(path) as src:
            np.testing.assert_allclose(src.read(1), [[1, -9999], [0, 2.5]])
            assert src.read(1, masked=True).mask[0, 1]
            assert src.crs.to_epsg() == 4326
            assert src.nodata == -9999
            assert src.dtypes == ("float32",)
            assert not src.profile.get("tiled", False)
            assert src.compression == rasterio.enums.Compression.deflate
            assert src.tags()["units"] == "mm/h"
            assert "test@example.com" not in str(src.tags())
    assert not list((tmp_path / "out").glob(".ef5-precip-*"))


@pytest.mark.parametrize("choice,archive,step,units", [
    ("Rate", "PrecipRate", 2, "mm/h"),
    ("Pass2", "MultiSensor_QPE_01H_Pass2", 60, "mm"),
    ("PrecipRate", "PrecipRate", 2, "mm/h"),
    ("MultiSensor_QPE_01H_Pass2", "MultiSensor_QPE_01H_Pass2", 60, "mm"),
])
def test_mrms_products_gzip_units_and_missing_cells(tmp_path, monkeypatch, mrms,
                                                  choice, archive, step, units):
    # These offline fixtures contain TIFF bytes, not GRIB. Driver availability
    # is checked separately; here exercise gzip and raster conversion behavior.
    monkeypatch.setattr(rasterio.Env, "drivers", lambda self: {"GRIB": "GRIB"})
    calls = stub_download(monkeypatch, mrms, compressed=True)
    end = "2024-09-18T00:02" if step == 2 else "2024-09-18T01:00"
    paths = download_precipitation(
        "MRMS", "2024-09-18", end, tmp_path / "out", mrms_product=choice,
    )
    assert len(paths) == 1
    assert calls == [(
        f"{precip.MRMS_SERVER}/2024/09/18/mrms/ncep/{archive}/"
        f"{archive}_00.00_20240918-000000.grib2.gz", None,
    )]
    with rasterio.open(paths[0]) as src:
        np.testing.assert_allclose(src.read(1), [[1, -9999, -9999], [0, 2.5, -9999]])
        assert src.tags()["units"] == units
        assert src.tags()["timestamp_utc"] == "2024-09-18T00:00:00+00:00"
        assert src.tags()["mrms_product"] == archive


@pytest.mark.parametrize("kwargs,match", [
    ({"product": "other"}, "product must"),
    ({"email": None}, "email"),
    ({"email": "not an email"}, "email"),
    ({"mrms_product": "Rate"}, "only to MRMS"),
    ({"product": "MRMS", "email": None}, "MRMS requires"),
    ({"product": "MRMS", "mrms_product": "Rate"}, "only to IMERG"),
    ({"product": "MRMS", "email": None, "mrms_product": "bad"}, "MRMS requires"),
    ({"start": "2020-10-08T00:01"}, "30-minute"),
    ({"end": "2020-10-08T00:45"}, "30-minute"),
    ({"end": "2020-10-08"}, "later than"),
    ({"start": "bad"}, "ISO"),
    ({"start": 12}, "ISO"),
    ({"bounds": (0, 0, 0, 1)}, "bounds"),
    ({"bounds": (-181, 0, 1, 1)}, "bounds"),
    ({"bounds": (0, 0, float("nan"), 1)}, "bounds"),
    ({"retries": -1}, "retries"),
    ({"timeout": 0}, "timeout"),
    ({"imerg_version": "../../bad"}, "imerg_version"),
])
def test_validation_before_network_or_output_creation(tmp_path, monkeypatch, kwargs, match):
    def unexpected(*args, **kwargs):
        pytest.fail("Network must not be used for invalid arguments")
    monkeypatch.setattr(precip, "_download", unexpected)
    options = dict(product="IMERG", start="2020-10-08", end="2020-10-08T01:00",
                   output_dir=tmp_path / "out", email="test@example.com")
    options.update(kwargs)
    with pytest.raises(ValueError, match=match):
        download_precipitation(**options)
    assert not (tmp_path / "out").exists()


def test_timezone_conversion_and_day_minute_index():
    stamp = precip._utc("2020-10-08T06:30:00-05:00")
    assert stamp == datetime(2020, 10, 8, 11, 30, tzinfo=timezone.utc)
    url, _, output = precip._request_file("IMERG", stamp, "V07B", None)
    assert "S113000-E115959.0690.V07B.tif" in url
    assert output == "imerg.202010081200.tif"


def test_existing_outputs_preflight_and_atomic_failure(tmp_path, monkeypatch, imerg):
    calls = stub_download(monkeypatch, imerg)
    out = tmp_path / "out"
    out.mkdir()
    existing = out / "imerg.202010080100.tif"
    existing.write_bytes(b"original")
    options = dict(product="IMERG", start="2020-10-08", end="2020-10-08T01:00",
                   output_dir=out, email="test@example.com")
    with pytest.raises(FileExistsError):
        download_precipitation(**options)
    assert not calls
    assert not (out / "imerg.202010080030.tif").exists()

    def fail_conversion(*args):
        raise ValueError("Invalid input")
    monkeypatch.setattr(precip, "_convert", fail_conversion)
    options["start"] = "2020-10-08T00:30"
    with pytest.raises(ValueError, match="Invalid input"):
        download_precipitation(**options, overwrite=True)
    assert existing.read_bytes() == b"original"
    assert not list(out.glob(".ef5-precip-*"))


def test_partial_completion_remains_on_missing_download(tmp_path, monkeypatch, imerg):
    calls = stub_download(monkeypatch, imerg)
    download = precip._download

    def missing_second(url, *args):
        if "S003000" in url or url.endswith("/gis/"):
            raise FileNotFoundError(url)
        download(url, *args)
    monkeypatch.setattr(precip, "_download", missing_second)
    out = tmp_path / "out"
    with pytest.raises(FileNotFoundError):
        download_precipitation("IMERG", "2020-10-08", "2020-10-08T01:00", out,
                               email="test@example.com", bounds=(-100, 39.8, -99.8, 40))
    assert (out / "imerg.202010080030.tif").exists()
    assert not (out / "imerg.202010080100.tif").exists()
    assert len(calls) == 1
    assert not list(out.glob(".ef5-precip-*"))


class Response(BytesIO):
    def __init__(self, payload, length=None):
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload) if length is None else length)}


def test_http_auth_retry_and_streaming(tmp_path, monkeypatch):
    requests = []

    def open_url(request, timeout):
        requests.append(request)
        assert timeout == 12
        if len(requests) == 1:
            raise HTTPError(request.full_url, 503, "Unavailable", {}, None)
        return Response(b"payload")
    monkeypatch.setattr(precip, "urlopen", open_url)
    monkeypatch.setattr(precip.time, "sleep", lambda _: None)
    destination = tmp_path / "download"
    precip._download("https://example.com/file", destination, "test@example.com", 12, 1)
    assert len(requests) == 2
    auth = requests[0].get_header("Authorization").split()[1]
    assert base64.b64decode(auth).decode() == "test@example.com:test@example.com"
    assert destination.read_bytes() == b"payload"


@pytest.mark.parametrize("code,error", [(404, FileNotFoundError), (401, PermissionError),
                                        (403, PermissionError), (400, RuntimeError)])
def test_http_permanent_errors_do_not_retry(tmp_path, monkeypatch, code, error):
    calls = []

    def open_url(request, timeout):
        calls.append(request)
        raise HTTPError(request.full_url, code, "error", {}, None)
    monkeypatch.setattr(precip, "urlopen", open_url)
    with pytest.raises(error):
        precip._download("https://example.com/file", tmp_path / "file", None, 1, 2)
    assert len(calls) == 1


@pytest.mark.parametrize("incomplete", [False, True])
def test_network_failure_exhausts_retries(tmp_path, monkeypatch, incomplete):
    calls = []

    def open_url(request, timeout):
        calls.append(request)
        if incomplete:
            return Response(b"short", length=100)
        raise URLError("Disconnected")
    monkeypatch.setattr(precip, "urlopen", open_url)
    monkeypatch.setattr(precip.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="after 3 attempts"):
        precip._download("https://example.com/file", tmp_path / "file", None, 1, 2)
    assert len(calls) == 3


def test_crop_snaps_outward_and_rejects_uncovered_bounds(tmp_path, mrms):
    with rasterio.open(mrms) as src:
        window = precip._crop_window(src, (-99.99, 39.81, -99.81, 39.99))
        assert window.width == window.height == 2
        with pytest.raises(ValueError, match="not fully covered"):
            precip._crop_window(src, (-110, 39.8, -99.8, 40))


def test_missing_grib_driver_fails_before_download(tmp_path, monkeypatch):
    monkeypatch.setattr(rasterio.Env, "drivers", lambda self: {})
    with pytest.raises(RuntimeError, match="GRIB driver"):
        download_precipitation("MRMS", "2024-09-18", "2024-09-18T00:02",
                               tmp_path / "out", mrms_product="Rate")
    assert not (tmp_path / "out").exists()


def test_uncovered_bounds_leave_no_output(tmp_path, monkeypatch, mrms):
    monkeypatch.setattr(rasterio.Env, "drivers", lambda self: {"GRIB": "GRIB"})
    stub_download(monkeypatch, mrms, compressed=True)
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="not fully covered"):
        download_precipitation("MRMS", "2024-09-18", "2024-09-18T00:02", out,
                               mrms_product="Rate", bounds=(-110, 39, -99, 40))
    assert list(out.iterdir()) == []


@pytest.mark.parametrize("suffix", [".ms", ".total.rate.tif", ".zip"])
def test_imerg_404_discovers_exact_granule_and_caches_daily_index(
    tmp_path, monkeypatch, imerg, suffix,
):
    from zipfile import ZipFile
    stamps = [precip._utc("2020-10-08T00:00"), precip._utc("2020-10-08T00:30")]
    stems = [precip._request_file("IMERG", s, "V07B", None)[1][:-4] for s in stamps]
    names = [stem + suffix for stem in stems]
    links = names + [stem + ".tfw" for stem in stems]
    links += [stems[0].replace("V07B", "V06B") + ".tif"]
    calls = []

    def download(url, destination, email, timeout, retries):
        calls.append(url)
        assert email == "test@example.com"
        if url.endswith("/gis/"):
            destination.write_text("".join(f'<a href="{name}">{name}</a>' for name in links))
        elif url.rsplit("/", 1)[-1] in names:
            if suffix == ".zip":
                stem = destination.name[:-4]
                with ZipFile(destination, "w") as archive:
                    archive.writestr(stem + ".total.rate.tif", imerg.read_bytes())
                    archive.writestr(stem + ".total.accum.tif", b"wrong variable")
                    archive.writestr(stem + ".liquid.rate.tif", b"wrong variable")
            else:
                destination.write_bytes(imerg.read_bytes())
        else:
            raise FileNotFoundError(url)

    monkeypatch.setattr(precip, "_download", download)
    paths = download_precipitation(
        "IMERG", "2020-10-08", "2020-10-08T01:00", tmp_path / "out",
        email="test@example.com", bounds=(-100, 39.8, -99.8, 40),
    )
    assert len(paths) == 2
    assert sum(url.endswith("/gis/") for url in calls) == 1
    assert len(calls) == 4
    for path, name in zip(paths, names):
        with rasterio.open(path) as src:
            np.testing.assert_allclose(src.read(1), [[1, -9999], [0, 2.5]])
            assert src.tags()["source_url"].endswith(name)


def test_imerg_worldfile_only_is_not_a_rainfall_download(tmp_path, monkeypatch):
    url, filename, _ = precip._request_file("IMERG", precip._utc("2020-10-08"), "V07B", None)
    stem = filename[:-4]

    def download(url, destination, *args):
        if url.endswith("/gis/"):
            destination.write_text(
                f'<a href="{stem}.tfw">worldfile</a>'
                f'<a href="https://other.example/{stem}.ms">external</a>'
            )
        else:
            raise FileNotFoundError(url)
    monkeypatch.setattr(precip, "_download", download)
    with pytest.raises(FileNotFoundError, match=r"\.tfw world file alone"):
        precip._imerg_source(url, tmp_path / filename, "test@example.com", 60, 0, {})


def test_imerg_zip_rejects_accumulation_only(tmp_path):
    from zipfile import ZipFile
    source = tmp_path / "granule.zip"
    with ZipFile(source, "w") as archive:
        archive.writestr("granule.total.accum.tif", b"not a rate")
    with pytest.raises(ValueError, match="total precipitation-rate TIFF"):
        precip._unpack_imerg(source)


def test_early_run_url_accumulation_to_rate_and_nodata(tmp_path, monkeypatch, imerg):
    calls = stub_download(monkeypatch, imerg)
    paths = download_precipitation(
        "IMERG", "2020-10-08T23:30", "2020-10-09T00:30", tmp_path / "early",
        email="test@example.com", imerg_run="EARLY", bounds=(-100, 39.8, -99.8, 40),
    )
    assert calls[0][0] == (
        "https://jsimpsonhttps.pps.eosdis.nasa.gov/imerg/gis/early/2020/10/"
        "3B-HHR-E.MS.MRG.3IMERG.20201008-S233000-E235959.1410.V07B.30min.tif"
    )
    assert "20201009-S000000-E002959.0000.V07B.30min.tif" in calls[1][0]
    for path in paths:
        with rasterio.open(path) as src:
            np.testing.assert_allclose(src.read(1), [[2, -9999], [0, 5]])
            assert src.tags()["imerg_run"] == "early"
            assert src.tags()["units"] == "mm/h"
            assert src.tags()["source_units"] == "0.1 mm/30min"


@pytest.mark.parametrize("run", ["late", "unknown", None])
def test_reject_unsupported_imerg_run(tmp_path, run):
    with pytest.raises(ValueError, match="imerg_run must"):
        download_precipitation("IMERG", "2020-10-08", "2020-10-09", tmp_path / "out",
                               email="test@example.com", imerg_run=run)
    assert not (tmp_path / "out").exists()


def test_early_zip_selects_total_accumulation_not_ice(tmp_path):
    from zipfile import ZipFile
    source = tmp_path / "3B-HHR-E.sample.V07B.30min.zip"
    with ZipFile(source, "w") as archive:
        archive.writestr("3B-HHR-E.sample.V07B.30min.tif", b"total")
        archive.writestr("3B-HHR-E.sample.V07B.30min.ice.tif", b"ice")
    extracted = precip._unpack_imerg(source, "early")
    assert extracted.read_bytes() == b"total"


@pytest.mark.parametrize("product", ["Pass1", "pass1", "MultiSensor_QPE_01H_Pass1"])
def test_removed_pass1_rejected_before_network(tmp_path, monkeypatch, product):
    def unexpected(*args, **kwargs):
        pytest.fail("Removed products must be rejected before network access")
    monkeypatch.setattr(precip, "_download", unexpected)
    with pytest.raises(ValueError, match="Rate or Pass2"):
        download_precipitation(
            "MRMS", "2025-06-01", "2025-06-01T01:00",
            tmp_path / "out", mrms_product=product,
        )
    assert not (tmp_path / "out").exists()

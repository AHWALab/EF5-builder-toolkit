"""Download IMERG Final/Early GIS or archived MRMS as EF5 GeoTIFFs."""

import base64
import gzip
import logging
import math
import re
import shutil
import time
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from http.client import IncompleteRead
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import unquote, urljoin, urlsplit
from zipfile import ZipFile

import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window, from_bounds as bounds_window

LOGGER = logging.getLogger(__name__)
NODATA = -9999
IMERG_SERVER = "https://arthurhouhttps.pps.eosdis.nasa.gov/gpmdata"
IMERG_EARLY_SERVER = "https://jsimpsonhttps.pps.eosdis.nasa.gov/imerg/gis/early"
#IMERG_LATE_SERVER = 
MRMS_SERVER = "https://mtarchive.geol.iastate.edu"
MRMS_PRODUCTS = {
    "rate": ("PrecipRate", 2, "mm/h"),
    "pass2": ("MultiSensor_QPE_01H_Pass2", 60, "mm"),
}


def _utc(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("Dates must be ISO dates or datetimes.") from exc
    if not isinstance(value, datetime):
        raise ValueError("Dates must be ISO strings or datetime objects.")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _bounds(value):
    if value is None:
        return None
    try:
        west, south, east, north = map(float, value)
    except (TypeError, ValueError) as exc:
        raise ValueError("bounds must be (west, south, east, north).") from exc
    if not (
        np.isfinite([west, south, east, north]).all()
        and -180 <= west < east <= 180
        and -90 <= south < north <= 90
    ):
        raise ValueError("bounds must be an ordered EPSG:4326 box within the globe.")
    return west, south, east, north


def _request_file(product, stamp, version, mrms_key, imerg_run="final"):
    folder = stamp.strftime("%Y/%m/%d")
    if product == "IMERG":
        last_second = stamp + timedelta(minutes=30) - timedelta(seconds=1)
        minute_of_day = stamp.hour * 60 + stamp.minute
        filename = (
            "3B-HHR-GIS.MS.MRG.3IMERG."
            f"{stamp:%Y%m%d-S%H%M%S}-{last_second:E%H%M%S}."
            f"{minute_of_day:04d}.{version}.tif"
        )
        url = f"{IMERG_SERVER}/{folder}/gis/{filename}"
        if imerg_run == "early":
            filename = filename.replace("3B-HHR-GIS.", "3B-HHR-E.").replace(
                f".{version}.tif", f".{version}.30min.tif"
            )
            url = f"{IMERG_EARLY_SERVER}/{stamp:%Y/%m}/{filename}"
        output = f"imerg.{stamp + timedelta(minutes=30):%Y%m%d%H%M}.tif"
    else:
        archive_name = MRMS_PRODUCTS[mrms_key][0]
        filename = f"{archive_name}_00.00_{stamp:%Y%m%d-%H%M%S}.grib2.gz"
        url = f"{MRMS_SERVER}/{folder}/mrms/ncep/{archive_name}/{filename}"
        output = f"mrms.{mrms_key}.{stamp:%Y%m%d%H%M}.tif"
    return url, filename, output


def _download(url, destination, email, timeout, retries):
    headers = {"User-Agent": "ef5-builder-toolkit"}
    if email is not None:
        token = base64.b64encode(f"{email}:{email}".encode()).decode("ascii")
        headers["Authorization"] = f"Basic {token}"
    request = Request(url, headers=headers)
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                with destination.open("wb") as dst:
                    shutil.copyfileobj(response, dst)
                length = response.headers.get("Content-Length")
                if length is not None and destination.stat().st_size != int(length):
                    raise OSError("Incomplete download.")
            return
        except HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError(f"No archived precipitation file: {url}") from exc
            if exc.code in (401, 403):
                raise PermissionError(
                    "Archive access denied. For IMERG, check the PPS-registered email."
                ) from exc
            if exc.code != 429 and not 500 <= exc.code < 600:
                raise RuntimeError(f"Download failed (HTTP {exc.code}): {url}") from exc
            error = exc
        except (URLError, OSError, IncompleteRead) as exc:
            error = exc
        if attempt == retries:
            raise RuntimeError(f"Download failed after {retries + 1} attempts: {url}") from error
        time.sleep(min(2 ** attempt, 8))


def _crop_window(src, bounds):
    if bounds is None:
        return Window(0, 0, src.width, src.height)
    west, south, east, north = bounds
    tolerance = max(src.res) * 1e-6
    if (
        west < src.bounds.left - tolerance
        or south < src.bounds.bottom - tolerance
        or east > src.bounds.right + tolerance
        or north > src.bounds.top + tolerance
    ):
        raise ValueError("Requested bounds are not fully covered by the precipitation grid.")
    window = bounds_window(*bounds, transform=src.transform)
    # Snap outwards to the source pixel edges without adding an extra pixel
    # for floating-point noise at an already aligned edge.
    col = max(0, math.floor(window.col_off + 1e-7))
    row = max(0, math.floor(window.row_off + 1e-7))
    right = min(src.width, math.ceil(window.col_off + window.width - 1e-7))
    bottom = min(src.height, math.ceil(window.row_off + window.height - 1e-7))
    return Window(col, row, right - col, bottom - row)


class _ArchiveLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href" and value)


def _imerg_source(url, source, email, timeout, retries, listings):
    """On a missing TIFF, discover the same granule in the archive index."""
    directory = url.rsplit("/", 1)[0] + "/"
    stem = source.name.removesuffix(".tif")
    if directory not in listings:
        try:
            _download(url, source, email, timeout, retries)
            return source, url
        except FileNotFoundError:
            LOGGER.info("TIFF URL not found; checking the IMERG archive index")
        listing = source.parent / "index.html"
        _download(directory, listing, email, timeout, retries)
        parser = _ArchiveLinks()
        parser.feed(listing.read_text(encoding="utf-8", errors="replace"))
        files = {}
        for href in parser.links:
            linked = urljoin(directory, href)
            # Only use files in this authenticated archive directory.
            if linked.rsplit("/", 1)[0] + "/" != directory:
                continue
            name = unquote(urlsplit(linked).path.rsplit("/", 1)[-1])
            if name and "/" not in name and "\\" not in name:
                files[name] = linked
        listings[directory] = files
    files = listings[directory]
    # A world file is metadata only. Select a precipitation-rate raster or
    # NASA's GIS ZIP for this exact timestamp and requested version.
    suffixes = ((".tif", ".zip") if source.name.startswith("3B-HHR-E.")
                else (".tif", ".total.rate.tif", ".ms", ".zip"))
    for suffix in suffixes:
        name = stem + suffix
        if name in files:
            resolved = files[name]
            source = source.parent / name
            LOGGER.info("Using archived IMERG file %s", name)
            _download(resolved, source, email, timeout, retries)
            return source, resolved
    matches = sorted(name for name in files if name.startswith(stem))
    raise FileNotFoundError(
        f"No precipitation-rate raster or GIS ZIP for {stem} in {directory}. "
        f"Matching archive entries: {matches or 'none'}. "
        "A .tfw world file alone does not contain rainfall values."
    )


def _unpack_imerg(source, imerg_run="final"):
    if source.suffix.lower() != ".zip":
        return source
    stem = source.name.removesuffix(".zip")
    with ZipFile(source) as archive:
        expected = ((stem + ".tif",) if imerg_run == "early"
                    else (stem + ".total.rate.tif", stem + ".tif"))
        matches = [
            name for name in archive.namelist()
            if Path(name).name in expected
        ]
        if len(matches) != 1:
            variable = "total half-hour accumulation" if imerg_run == "early" else "total precipitation-rate"
            raise ValueError(
                f"IMERG GIS ZIP must contain exactly one matching {variable} TIFF."
            )
        destination = source.parent / "precipitation-rate.tif"
        # Stream the selected member, without extracting arbitrary archive paths.
        with archive.open(matches[0]) as src, destination.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    return destination


def _convert(source, destination, product, bounds, tags):
    with ExitStack() as stack:
        if product == "IMERG":
            # Resolve conflicting source GeoTIFF keys using the official CRS.
            stack.enter_context(rasterio.Env(GTIFF_SRS_SOURCE="EPSG"))
        raw = stack.enter_context(rasterio.open(source))
        if raw.count != 1:
            raise ValueError("Expected a single-band precipitation file.")
        if product == "IMERG":
            # IMERG GIS metadata has historically been misinterpreted by GDAL.
            # Use NASA's documented global 0.1-degree grid, as in the notebook.
            if (raw.width, raw.height) != (3600, 1800):
                raise ValueError("Expected the global 3600 x 1800 IMERG GIS grid.")
            src = stack.enter_context(WarpedVRT(
                raw, src_crs="EPSG:4326",
                src_transform=from_bounds(-180, -90, 180, 90, 3600, 1800),
                crs="EPSG:4326", src_nodata=29999, nodata=NODATA,
                dtype="float32",
            ))
        else:
            if raw.crs is None:
                raise ValueError("MRMS GRIB must have a defined CRS.")
            src = stack.enter_context(WarpedVRT(
                raw, crs="EPSG:4326", nodata=NODATA, dtype="float32",
            ))
        window = _crop_window(src, bounds)
        with rasterio.open(
            destination, "w", driver="GTiff", count=1,
            width=int(window.width), height=int(window.height),
            transform=src.window_transform(window), crs="EPSG:4326",
            dtype="float32", nodata=NODATA, compress="deflate", tiled=False, interleave="pixel",
            BIGTIFF="IF_SAFER",
        ) as dst:
            for _, local in dst.block_windows(1):
                read = Window(
                    window.col_off + local.col_off, window.row_off + local.row_off,
                    local.width, local.height,
                )
                values = src.read(1, window=read, masked=True)
                valid = (
                    ~np.ma.getmaskarray(values)
                    & np.isfinite(values.data)
                    & (values.data >= 0)
                )
                data = np.full(values.shape, NODATA, dtype="float32")
                scale = 1.0
                if product == "IMERG":
                    # Early stores tenths of mm per half-hour. Divide by
                    # 0.5 hours to keep the same mm/h output as Final.
                    scale = 0.2 if tags.get("imerg_run") == "early" else 0.1
                data[valid] = values.data[valid] * scale
                dst.write(data, 1, window=local)
            dst.update_tags(**tags)


def download_precipitation(
    product,
    start,
    end,
    output_dir,
    *,
    email=None,
    mrms_product=None,
    bounds=None,
    imerg_version="V07B",
    imerg_run="final",
    overwrite=False,
    timeout=60,
    retries=2,
):
    """Download and convert precipitation files for a UTC period [start, end).

    product: "IMERG" (Final or Early Run GIS) or "MRMS", case-insensitive.
    start, end: ISO date/datetime strings or datetime objects. Naive dates
        are UTC; timezone-aware dates are converted to UTC. Both boundaries
        must align with the product cadence (30, 2, or 60 minutes).
    output_dir: Directory for striped, Deflate-compressed Float32 EPSG:4326 GeoTIFFs.
    email: PPS-registered email required for IMERG, used as username/password.
    mrms_product: Required for MRMS: Rate or Pass2 (or the full
        corresponding archive product name). Availability varies by date;
    bounds: Optional (west, south, east, north) box in EPSG:4326. Snapped
        outwards to grid edges; must be fully covered. No temporal aggregation
        or alignment to the model DEM is performed.
    imerg_version: GIS filename version, default V07B; applies only to IMERG.
    imerg_run: "final" (default) or "early", case-insensitive. Early GIS
        half-hour accumulations are converted to mm/h by multiplying by 0.2;
        Final GIS rates are converted to mm/h by multiplying by 0.1.
    overwrite: Replace existing outputs, default False.
    timeout: Positive timeout in seconds for each network operation.
    retries: Number of additional attempts after transient download errors.

    Returns a chronological list of absolute pathlib.Path objects. IMERG
    outputs contain mm/h and use interval-end timestamps, as in the original
    notebook. MRMS Rate contains mm/h; Pass2 retains hourly totals in mm.
    MRMS filenames use the archive timestamp. Missing/negative precipitation
    is NoData=-9999. Any failure raises an exception; completed files remain.
    Temporary downloads are removed, and each output is published atomically.
    """
    if not isinstance(product, str) or product.upper() not in ("IMERG", "MRMS"):
        raise ValueError("product must be IMERG or MRMS.")
    product = product.upper()
    mrms_key = None
    if product == "IMERG":
        if not isinstance(imerg_run, str) or imerg_run.lower() not in ("final", "early"):
            raise ValueError("imerg_run must be final or early.")
        imerg_run = imerg_run.lower()
        if not isinstance(email, str) or not re.fullmatch(r"[^\s:@]+@[^\s:@]+", email):
            raise ValueError("IMERG requires a PPS-registered email address.")
        if mrms_product is not None:
            raise ValueError("mrms_product applies only to MRMS.")
        if not isinstance(imerg_version, str) or not re.fullmatch(r"V\d{2}[A-Z]", imerg_version):
            raise ValueError("imerg_version must look like V07B.")
        minutes, units = 30, "mm/h"
    else:
        if email is not None:
            raise ValueError("email applies only to IMERG; MRMS needs no account.")
        if isinstance(mrms_product, str):
            for key, (name, _, _) in MRMS_PRODUCTS.items():
                if mrms_product.lower() in (key, name.lower()):
                    mrms_key = key
                    break
        if mrms_key is None:
            raise ValueError("MRMS requires mrms_product: Rate or Pass2.")
        _, minutes, units = MRMS_PRODUCTS[mrms_key]
        with rasterio.Env() as env:
            if "GRIB" not in env.drivers():
                raise RuntimeError(
                    "MRMS conversion requires the GDAL GRIB driver. "
                    "Update the Conda environment using environment.yml "
                    "(which includes libgdal-grib)."
                )
    start, end = _utc(start), _utc(end)
    if end <= start:
        raise ValueError("end must be later than start.")
    for stamp in (start, end):
        if stamp.second or stamp.microsecond or (stamp.hour * 60 + stamp.minute) % minutes:
            raise ValueError(f"UTC start and end must align to {minutes}-minute boundaries.")
    bounds = _bounds(bounds)
    if not isinstance(retries, int) or isinstance(retries, bool) or retries < 0:
        raise ValueError("retries must be a nonnegative integer.")
    if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a positive number of seconds.")
    output_dir = Path(output_dir).resolve()
    step = timedelta(minutes=minutes)
    count = (end - start) // step
    outputs = [
        output_dir / _request_file(product, start + i * step, imerg_version, mrms_key, imerg_run)[2]
        for i in range(count)
    ]
    for path in outputs:
        if path.exists() and not overwrite:
            raise FileExistsError(f"{path} already exists; use overwrite=True.")
    output_dir.mkdir(parents=True, exist_ok=True)
    listings = {}
    for i, path in enumerate(outputs):
        stamp = start + i * step
        url, filename, _ = _request_file(product, stamp, imerg_version, mrms_key, imerg_run)
        LOGGER.info("Downloading %s (%d/%d)", filename, i + 1, count)
        with TemporaryDirectory(prefix=".ef5-precip-", dir=output_dir) as temp:
            temp = Path(temp)
            source = temp / filename
            if product == "IMERG":
                source, url = _imerg_source(url, source, email, timeout, retries, listings)
                source = _unpack_imerg(source, imerg_run)
            else:
                _download(url, source, email, timeout, retries)
                unpacked = temp / filename.removesuffix(".gz")
                with gzip.open(source, "rb") as src, unpacked.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                source = unpacked
            tags = {
                "product": product, "units": units, "source_url": url,
                "source_timestamp_utc": stamp.isoformat(),
                "cadence_minutes": str(minutes),
            }
            if product == "IMERG":
                tags["imerg_version"] = imerg_version
                tags["imerg_run"] = imerg_run
                tags["source_units"] = "0.1 mm/30min" if imerg_run == "early" else "0.1 mm/h"
                tags["timestamp_utc"] = (stamp + step).isoformat()
            else:
                tags["mrms_product"] = MRMS_PRODUCTS[mrms_key][0]
                tags["timestamp_utc"] = stamp.isoformat()
            staged = temp / "output.tif"
            _convert(source, staged, product, bounds, tags)
            staged.replace(path)
    return outputs

# Precipitation downloads: technical details

Use `download_precipitation` to download a UTC period and convert IMERG Final Run, IMERG Early Run, or archived MRMS precipitation to EF5 GeoTIFFs. Run [notebook 2](../Example/Example_notebooks/2_Get_precipitation_files_library.ipynb) or call the function directly.

```python
from ef5_builder import download_precipitation
```

#### Option A: IMERG Final or Early Run

Provide your **PPS-registered GPM email address**. NASA PPS uses that email as both the HTTPS username and password; register at [PPS registration](https://registration.pps.eosdis.nasa.gov/). An Earthdata account alone does not replace PPS registration. The function uses the registered email for authentication and does not write it to output metadata.

```python
email = "your-registered-email@example.com"

outputs = download_precipitation(
    product="IMERG",
    imerg_run="final",  # choose "final" or "early"
    start="2020-10-08 00:00:00",
    end="2020-10-11 00:00:00",
    output_dir="data/precip/imerg",
    email=email,
    bounds=(-21.4, -2.9, 30.4, 33.1),  # west, south, east, north
)
```

IMERG defaults to **Final Run v07B**, at 30-minute temporal resolution. Select `imerg_run="early"` for Early Run; Late Run is not included.

| `imerg_run` | Archive | Source variable and stored units | Conversion to output mm/h |
| --- | --- | --- | --- |
| `final` | `arthurhouhttps.pps.eosdis.nasa.gov/gpmdata/YYYY/MM/DD/gis/` | Total precipitation rate in 0.1 mm/h, including `total.rate.tif` inside a GIS ZIP | Raw value × 0.1 |
| `early` | `jsimpsonhttps.pps.eosdis.nasa.gov/imerg/gis/early/YYYY/MM/` | Half-hour accumulation in 0.1 mm, in `3B-HHR-E.…V07B.30min.tif` | Raw value × 0.1 ÷ 0.5 hours = raw value × 0.2 |

Both runs produce **mm/h** using the same EF5 settings below. Early outputs are interval-average rates derived from the half-hour totals. Use separate output directories for Final and Early because both use the `imerg.YYYYMMDDHHUU.tif` filename pattern. Output metadata records the run and source units.

For both runs, missing values (`29999`) are masked before scaling and written as `-9999`. A stored value of `10` means `1 mm/h` in Final; in Early it means `1 mm` over 30 minutes, equivalent to `2 mm/h`. Outputs use the **end of the 30-minute interval**, that is, the source interval beginning at `2020-10-08 00:00 UTC` becomes `imerg.202010080030.tif`. See NASA's [IMERG GIS documentation](https://gpm.nasa.gov/resources/documents/imerg-gis-geotiff-documentation) for format and scaling details, and its [data directory](https://gpm.nasa.gov/data/directory) for version information.

```ini
[PrecipForcing IMERG]
TYPE=TIF
UNIT=mm/h
FREQ=30u
LOC=/data/precip/imerg/
NAME=imerg.YYYYMMDDHHUU.tif
```

If the expected IMERG `.tif` URL returns 404, the downloader reads the authenticated GIS directory (daily for Final, monthly for Early) and looks for the exact timestamp and requested version as `.tif`, `.total.rate.tif`, `.ms`, or `.zip`. A listed `.ms` file must contain a readable rainfall raster; its extension alone does not establish its format. GIS ZIP files are unpacked using only the matching total precipitation-rate TIFF for Final, or total half-hour accumulation TIFF for Early. `.tfw` world files contain georeferencing metadata and are never used as rainfall data. If no supported file is found, the error reports matching directory entries. This fallback does not substitute another timestamp or version.

#### Option B: MRMS

Select `product="MRMS"` and supply `mrms_product`. No account is required. Downloads use Iowa State University's historical archive.

```python
outputs = download_precipitation(
    product="MRMS",
    mrms_product="Rate",
    start="2017-06-29 00:00:00",
    end="2017-06-29 01:00:00",
    output_dir="data/precip/mrms_rate",
    bounds=(-100.0, 35.0, -90.0, 45.0),
)
```

| `mrms_product` | Archive product name (also accepted) | Cadence | Output units | Filename |
| --- | --- | --- | --- | --- |
| `Rate` | `PrecipRate` | 2 minutes | mm/h | `mrms.rate.YYYYMMDDHHUU.tif` |
| `Pass2` | `MultiSensor_QPE_01H_Pass2` | 1 hour | mm (hourly total) | `mrms.pass2.YYYYMMDDHHUU.tif` |

MRMS outputs retain the **archive timestamp** and the precipitation values in the table; negative or missing values become NoData. Product and date availability vary. A missing archive file raises `FileNotFoundError`; the function does not substitute products or fill missing times. Example ISU catalogs: [Rate](https://mtarchive.geol.iastate.edu/thredds/mtarchive/2024/09/18/mrms/ncep/PrecipRate/catalog.html) and [Pass2](https://mtarchive.geol.iastate.edu/thredds/mtarchive/2024/09/18/mrms/ncep/MultiSensor_QPE_01H_Pass2/catalog.html).

For Rate, use:

```ini
[PrecipForcing MRMS]
TYPE=TIF
UNIT=mm/h
FREQ=2u
LOC=/data/precip/mrms_rate/
NAME=mrms.rate.YYYYMMDDHHUU.tif
```

Pass2 remains hourly accumulation in mm; configure their hourly forcing consistently with those units. The downloader does not aggregate Rate to hourly data or convert hourly totals to another interval.

#### Period, spatial extent, and outputs

- `start` is inclusive and `end` is exclusive **for source timestamps**. To include a whole day, use midnight of the next day as `end`. IMERG's last output timestamp can equal `end` because outputs label interval ends.
- Dates may be ISO strings (including date-only strings) or Python `datetime` objects. Naive dates are interpreted as UTC; timezone-aware dates are converted to UTC. Both boundaries must align with the product cadence: 30 minutes for IMERG, even 2-minute boundaries for Rate, or whole hours for Pass2. Misaligned dates are rejected.
- `bounds=(west, south, east, north)` is optional and uses EPSG:4326. Omit it to keep the full product extent. Bounds must be fully covered by the precipitation grid and are snapped outward to pixel edges. Cropping does not reduce the remote download size. MRMS is converted to EPSG:4326 with nearest-neighbor sampling; grids are not aligned to the model DEM.
- The return value is a chronological list of absolute `pathlib.Path` objects. Outputs are striped, Deflate-compressed, single-band GeoTIFFs in EPSG:4326, with float32 values and `NoData=-9999`. Metadata records product, units, source URL, version or MRMS product, and UTC timestamps.
- Existing outputs raise `FileExistsError` before downloads begin. Use `overwrite=True` to replace them. Each completed output is saved atomically; failed downloads or conversions leave no partial output. Completed files remain if a later timestamp fails. Resume from the failed source timestamp or rerun with `overwrite=True`.
- `timeout=60` sets the network timeout in seconds; `retries=2` allows two additional attempts for transient network errors or HTTP 429/5xx responses. Authentication failures and missing files fail immediately.

---

## Live example tests

The example notebook uses one-hour UTC periods beginning at 2025-06-01 00:00 for IMERG Final, IMERG Early, and both MRMS products. IMERG is cropped to the Ghana example DEM bounds; MRMS uses the U.S. box (-95, 40, -93, 42). Each product has its own folder under `Ghana_example/outputs/precip`.

The live validation report is saved as `Ghana_example/outputs/precip/download_test_report.json`. It records actual dates, output files, units, timestamps, source URLs, valid-cell counts, and value ranges, or the observed error when a download fails. It must not be interpreted as a guarantee of archive availability for other dates. The individual examples do not substitute dates or products after failure.

The offline regression tests use local raster fixtures and simulated HTTP responses. They cover units, missing values, timestamps, cadence validation, archive-index/ZIP fallback, retries, and file handling. These tests complement actual downloads; simulated success alone does not establish archive availability.

## EF5 GeoTIFF storage

Precipitation outputs use `TILED=NO` and `COMPRESS=DEFLATE` (Rasterio `tiled=False`, `compress="deflate"`) for EF5 1.3. No pixel scaling, temporal labels, or crop rules are changed by these storage settings. Source data are still downloaded in their original archive format before conversion.

## MRMS GRIB dependency

The local `FFclimo` environment initially had GDAL 3.9.3 without the optional GRIB driver. The first real MRMS attempts stopped at the driver check before downloading. To test without modifying that environment, a temporary PyPI Rasterio 1.4.2 wheel was installed under `/tmp/ef5-precip-rasterio`; its bundled GDAL 3.9.3 includes GRIB. The tests use the same precipitation module with that temporary Rasterio on PYTHONPATH. This temporary path is a test dependency, not part of the notebook setup.

For the normal Conda setup, `environment.yml` already includes `libgdal-grib`. If using an older existing environment, activate it and install the driver:

```sh
conda install -c conda-forge libgdal-grib
```

An inherited `GDAL_DRIVER_PATH` pointing to another environment can prevent plugin discovery. Check that it points to the active environment's plugin directory, or remove the incorrect override. Confirm the driver using:

```python
import rasterio

with rasterio.Env() as env:
    print("GRIB available:", "GRIB" in env.drivers())
```

## Observed results

Actual downloads and conversion for the source interval 2025-06-01 00:00–01:00 UTC produced:

| Product | Status | Output files |
| --- | --- | --- |
| IMERG Final V07B | Passed | 2 |
| IMERG Early V07B | Passed | 2 |
| MRMS Rate | Passed with GRIB-enabled temporary dependency | 30 |
| MRMS Pass2 | Passed with GRIB-enabled temporary dependency | 1 |

Every downloaded output was checked for single-band float32 EPSG:4326, NoData=-9999, striped/uncompressed storage, finite nonnegative valid data, and presence of valid cells. Units, output timestamps, source URLs, and value ranges are recorded per file in `download_test_report.json`. The 47 offline precipitation tests also passed after the storage update.


## Removed product

Pass1 is no longer supported by this downloader because the requested file and the seven checked ISU product directories returned 404 during testing. Both `Pass1` and `MultiSensor_QPE_01H_Pass1` are rejected before network access. The historical download/availability reports remain unchanged as records of those attempts; they do not describe the currently supported products.

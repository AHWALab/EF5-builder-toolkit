# Annual overland Manning roughness

`annual_manning_from_modis(input_dir, output_dir, years=None, file_pattern="*", filename_template=None, class15_n=0.025, overwrite=False)`
converts MCD12Q1 Collection 6.1 `LC_Type2` exports into annual overland roughness.
Use single-band EPSG:4326 GeoTIFFs that were exported without interpolation of
categorical classes. Native MODIS is sinusoidal; this function accepts the user's
geographic exports and preserves their grid rather than imposing a nominal 500 m pixel size.

## Verified scientific crosswalk

[Flamig et al. (2020), Table 5](https://gmd.copernicus.org/articles/13/4943/2020/gmd-13-4943-2020-t05.xlsx)
uses older UMD numbering. Matching raw numbers to `LC_Type2` would be incorrect.
The mapping below uses class meanings from the [official MODIS C6.1 user guide,
Table 4](https://lpdaac.usgs.gov/documents/1409/MCD12_User_Guide_V61.pdf).
Woodland and wooded grassland correspond to woody savanna and savanna terminology;
this correspondence also appears in the [NASA MODIS vegetation ATBD legend](https://lpdaac.usgs.gov/documents/117/MOD15_ATBD_0HgficO.pdf).

| LC_Type2 | Class | Table 5 code | n (s m^-1/3) |
| --- | --- | --- | --- |
| 0 | Water | 0 | 0.001 |
| 1 | Evergreen needleleaf forest | 1 | 0.1 |
| 2 | Evergreen broadleaf forest | 2 | 0.1 |
| 3 | Deciduous needleleaf forest | 3 | 0.1 |
| 4 | Deciduous broadleaf forest | 4 | 0.1 |
| 5 | Mixed forest | 5 | 0.1 |
| 6 | Closed shrubland | 8 | 0.3 |
| 7 | Open shrubland | 9 | 0.2 |
| 8 | Woody savanna / woodland | 6 | 0.1 |
| 9 | Savanna / wooded grassland | 7 | 0.3 |
| 10 | Grassland | 10 | 0.17 |
| 12 | Cropland | 11 | 0.035 |
| 13 | Urban and built-up | 13 | 0.015 |
| 15 | Barren, including snow/ice | No direct combined-class match | 0.025 (provisional user choice) |
| 255 | Unclassified/fill | — | Output NoData=-9999 |

Classes 11 (wetlands) and 14 (cropland/vegetation mosaics) were removed from UMD
in Collection 6.1. Their occurrence raises an error, as do other unexpected
or fractional codes. They are not borrowed from IGBP or another scheme.

Class 15 combines barren land with permanent snow/ice. Table 5 covers bare
ground at 0.01 but does not provide a snow/ice coefficient. At the user's
request, the combined class uses **0.025 provisionally**, pending further
research. This value is not attributed to Flamig Table 5. The user's reference
is [HEC-RAS 6.6: Creating Land Cover, Manning’s n values, and % Impervious Layers](
https://www.hec.usace.army.mil/confluence/rasdocs/r2dum/6.6/developing-a-terrain-model-and-geospatial-layers/creating-land-cover-mannings-n-values-and-impervious-layers).
That page describes assigning land-cover roughness; it is not a verified lookup
for MODIS UMD class 15. The assumption and reference are recorded in every
output's metadata. Set `class15_n` to revise the provisional coefficient:

```python
annual_n = annual_manning_from_modis(
    "data/modis_lc_type2", "data/manning/native", class15_n=0.025,
)
```

The function applies an a priori overland coefficient, not a calibrated
channel roughness. In EF5's KW workflow n contributes to alpha0 via
alpha0 = (n / sqrt(slope)) ** (3/5), following the selected
[EF5 Global Parameters formulation](https://github.com/HyDROSLab/EF5-Global-Parameters). Derive routing inputs for the intended
year; generating these files does not automatically switch EF5 parameters.
The MODIS guide cautions that annual class transitions may reflect classification
uncertainty, so these rasters should not be treated as definitive observed land-cover changes.

## Files and mosaics

Names may contain an isolated year (`LC_Type2_2001_tile01.tif`), a date
(`LC_Type2_20010101.tif`), or a MODIS acquisition token (`MCD12Q1.A2001001...tif`).
Acquisition year takes precedence over the production timestamp. Ambiguous or
missing years raise an error. The function detects available four-digit years without a dataset-date restriction;
`years=range(2001, 2026)` explicitly requires every requested year to be present.
No missing year is synthesized or carried forward. For custom names, set
`filename_template="MCD12Q1_UMD_YYYY_Global_*.tif"` to specify the year position.
`YYYY` captures four digits, and `*`/`?` are filename wildcards. Only matching
files are processed. The template can disambiguate acquisition and export years. Use
`file_pattern="MCD12Q1_UMD_*.tif"` when the input directory also contains
DEM or other GeoTIFF files.

Tiles within each year must share resolution, CRS and pixel alignment. Their
union extent becomes the output domain. Gaps are NoData. Identical class overlap
is accepted; conflicting valid classes raise an error, even when their coefficients
are equal. Fill or masked pixels never replace valid neighboring tiles. NoData=0
is rejected because class 0 is valid water. Metadata-free exports must actually
contain LC_Type2: overlapping code ranges cannot establish band identity alone.

Outputs are `manning_n_YYYY.tif`, float32, NoData=-9999, with Deflate compression,
striped storage and BigTIFF when needed. Each year is written atomically; earlier
completed years remain if a later year fails. Source names, year, DOI, crosswalk,
units and source product/band are stored as tags. Spatial metadata is preserved;
separate years can have different export extents.

```python
from ef5_builder import annual_manning_from_modis, resample_and_subset

annual_n = annual_manning_from_modis(
    input_dir="data/modis_lc_type2",
    output_dir="data/manning/native",
)

# Align coefficients separately to the final model DEM.
aligned_n = {
    year: resample_and_subset(
        path, f"data/manning/aligned/manning_n_{year}.tif",
        template="data/basic/dem.tif", mask_template=True,
    )
    for year, path in annual_n.items()
}
```

Nearest-neighbor alignment retains lookup values. Averaging coefficients is a
separate modeling assumption, not an established effective roughness rule.

Coefficients are assigned directly in SI units (`s m^-1/3`); the function
performs no additional unit scaling and records these units in raster tags.

## Export MODIS GeoTIFFs from Google Earth Engine

If you want to download the MODIS MCD12Q1 Collection 6.1 `LC_Type2` (UMD) product, paste the following code into the [Earth Engine Code Editor](https://code.earthengine.google.com/).

The code exports the files for available years at nominal 500 m in EPSG:4326. 
Start them in the **Tasks** tab, then download all exported tiles from the
**MODIS_LandCover** folder in Google Drive into your input directory.
The code is also available as [export_modis_umd.js](../Example/Example_notebooks/earth_engine/export_modis_umd.js).
[Earth Engine GeoTIFF export options](https://developers.google.com/earth-engine/apidocs/export-image-todrive).

<details>
<summary>Earth Engine export code</summary>

```javascript
// Paste into https://code.earthengine.google.com/.
var dataset = ee.ImageCollection('MODIS/061/MCD12Q1');
var region = ee.Geometry.Rectangle([-180, -90, 180, 90], 'EPSG:4326', false);

// LC_Type2 codes. Classes 11 and 14 were removed in Collection 6.1.
// This palette affects display only; the export retains integer class codes.
var palette = [
  '1c0dff', // 0 Water
  '05450a', // 1 Evergreen needleleaf forest
  '086a10', // 2 Evergreen broadleaf forest
  '54a708', // 3 Deciduous needleleaf forest
  '78d203', // 4 Deciduous broadleaf forest
  '009900', // 5 Mixed forest
  'c6b044', // 6 Closed shrubland
  'dcd159', // 7 Open shrubland
  'dade48', // 8 Woody savanna
  'fbff13', // 9 Savanna
  'b6ff05', // 10 Grassland
  '808080', // 11 Unused in C6.1 UMD
  'c24f44', // 12 Cropland
  'a5a5a5', // 13 Urban and built-up
  '808080', // 14 Unused in C6.1 UMD
  'f9ffa4'  // 15 Barren, including snow/ice
];

// Discover available years, including future releases; no missing-year exports.
var years = dataset.aggregate_array('system:time_start').map(function(time) {
  return ee.Date(time).get('year');
}).distinct().sort().getInfo();
var latestYear = years[years.length - 1];

// To export selected years only, filter the years array here.
years.forEach(function(year) {
  var landcover = dataset
    .filterDate(year + '-01-01', (year + 1) + '-01-01')
    .first();
  var lc = landcover.select('LC_Type2');

  if (year === latestYear) {
    Map.setCenter(-60, -10, 4);
    Map.addLayer(lc, {min: 0, max: 15, palette: palette},
                 'MODIS UMD Land Cover ' + year);
  }

  // Keep default nearest-neighbor sampling for categorical land cover.
  // Fill missing pixels with 255 rather than zero (which is valid water).
  Export.image.toDrive({
    image: lc.unmask({value: 255, sameFootprint: false}).toUint8(),
    description: 'MCD12Q1_UMD_' + year + '_Global_EPSG4326',
    folder: 'MODIS_LandCover',
    fileNamePrefix: 'MCD12Q1_UMD_' + year + '_Global_EPSG4326',
    region: region,
    crs: 'EPSG:4326',
    scale: 500,
    maxPixels: 1e10,
    fileFormat: 'GeoTIFF',
    formatOptions: {cloudOptimized: true, noData: 255}
  });
});

// Start exports in the Tasks tab, then download all tiles from Google Drive.
```

</details>

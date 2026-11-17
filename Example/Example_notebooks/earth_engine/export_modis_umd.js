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

# Impervious surface: GMIS 2010 technical details

For the basic workflow, see [Step 7 in the README](../README_library.md#step-7-create-the-crest-parameters) and [the Ghana notebook](../Example/Example_notebooks/7b_Impervious_layer_processing.ipynb).

## Source checks and access

On 2026-10-29, NASA CMR returned GMIS collection `C3550185860-ESDIS`, short name `CIESIN_SEDAC_ULANDSAT_GMIS_V1`, version 1.0. The collection contains geographic and UTM products at 30 m, 250 m, and 1 km, including separate uncertainty layers. The notebook selects only geographic **impervious surface percentage** ZIP files at 250 m.

- [Current NASA Earthdata collection](https://search.earthdata.nasa.gov/search/granules?p=C3550185860-ESDIS).
- CMR discovery API: `https://cmr.earthdata.nasa.gov/search/granules.json`.
- Tile-index query: `https://gis.earthdata.nasa.gov/portal/rest/services/Hosted/UTM_Tiles/FeatureServer/0/query`.
- Current file URLs are returned by CMR under `https://data.earthdata.nasa.gov/nasa-earth/human-dimensions/sedac-root/downloads/data/ulandsat/ulandsat-gmis-v1/`.
- [Earthdata token instructions](https://urs.earthdata.nasa.gov/documentation/for_users/user_token) and [NASA's token download example](https://urs.earthdata.nasa.gov/documentation/for_users/data_access/python_user_token_script).

The example DEM bounds intersect tiles 30N, 30P, 31N, and 31P in the official tile index. A country-only Ghana download would not cover the upstream domain extending beyond Ghana. CMR may also return country clips or dateline-related bounding-box matches; the tile-index IDs and exact filename pattern exclude them. Missing tiles raise an error rather than silently creating partial coverage. The manifest records selected public URLs and bounds, never the token.

The old `https://gis.earthdata.nasa.gov/image/rest/services/ulandsat/ulandsat_gmis_v1/ImageServer` returned 404. The [NASA portal item](https://gis.earthdata.nasa.gov/portal/home/item.html?id=921b3fc59ef2439087cd77ca61f32117) now references `https://gis.earthdata.nasa.gov/portal/rest/services/ulandsat/ulandsat_gmis_v1/ImageServer`, which returned metadata and a small quantitative TIFF export successfully. That service reports a roughly 30 m source grid; an export requested at 250 m is not automatically equivalent to the published 250 m tile product, so the notebook does not silently substitute it.

An anonymous request for the official 30N geographic 250 m ZIP returned HTTP 401. Its catalogue record remains discoverable; this response indicates an authentication requirement, not evidence that the data were deleted. A subsequent authenticated run successfully downloaded all four official ZIP files and processed the Ghana example. The token was not saved in the notebook, manifest, or output files. The notebook supports a hidden token prompt or manually downloaded ZIP files. It checks ZIP integrity and does not save credentials. Requests handles redirects and keeps session cookies in memory. The token is sent only to the expected HTTPS data host.

## Processing decisions

The source is the 2010 GMIS dataset used by the old example, not an annual impervious time series. The public coarser product is used as delivered; its provider-side production must not be confused with averaging performed by this notebook.

The notebook follows the legacy interpretation of the documented GMIS codes: 0–100 are percent imperviousness, 200 denotes non-HBASE and is converted to 0%, and 255 denotes missing/cloud/shadow data. Band 1 of the percentage product is used. Unexpected codes raise an error instead of being clipped into the valid range. The original ZIPs are preserved.

Each source tile is cropped to the DEM bounding rectangle at its own grid and cleaned in 512 × 512 windows. Tiles are mosaicked at their shared source pixel size; nearest-neighbor is allowed for tile-origin alignment only. The output is not averaged, bilinearly interpolated, or resized to the DEM resolution. Source pixel-size inconsistencies raise an error. The DEM's finite valid-cell mask is sampled by nearest-neighbor onto the impervious grid; only the mask is sampled, not the impervious values.

Remaining missing cells inside that domain can be filled from the nearest original valid impervious cell inside the domain, following the legacy nearest-neighbor approach. Zero is a valid donor. Donor selection uses Euclidean distance in geographic raster coordinates, not geodesic distance in metres. No maximum filling distance is applied. Set `fill_missing=False` to keep these gaps. Filling estimates are not observations, and may extend values over large cloud gaps; inspect the fill mask. Lakes are not independently masked by this notebook; the supplied DEM defines its domain.

## Outputs and resource use

The output is `Example/data_model/crest_parameters/crest_IM.tif`, still at the source 250 m geographic pixel size and in percent, not a 0–1 fraction. The exact degree pixel size is read from the downloaded source rather than invented from the nominal metre label. `Example/posproc_outputs/crest_diagnostics/crest_IM_filled_mask.tif` records unchanged cells (0), filled cells (1), and NoData outside the domain (-9999). Both files are float32, striped, and Deflate-compressed, with NoData=-9999 for EF5. They are staged before replacement; each replacement is atomic, not the pair as a transaction. Existing processed files require `overwrite=True`.

Tile cleaning is windowed. The final Ghana-size mosaic and domain masks are held in memory; the distance-transform index uses two int32 grids when filling is needed. This is intended for the example domain, not an unrestricted global in-memory calculation. Larger regions need a different filling strategy. Plot downsampling affects display only.

## References

Brown de Colstoun et al. (2017), Global Man-made Impervious Surface (GMIS) Dataset From Landsat, v1 (2010), [doi:10.7927/H4P55KKF](https://doi.org/10.7927/H4P55KKF). Technical documentation: [doi:10.7927/H4JD4TVQ](https://doi.org/10.7927/H4JD4TVQ). The provider requests attribution when using the data. The notebook preserves the source reference year and does not imply that 2010 imperviousness represents later urban change.

## Validation performed

The notebook's actual discovery cell was run against the current NASA services using the Ghana example DEM bounds and selected the four expected official geographic 250 m percentage tiles. Their public URLs are saved in `Example/resources/impervious/gmis_2010_250m/download_manifest.json`.

The regression test `tests/test_impervious_notebook.py` executes the notebook's raster-processing cells with small ZIP/GeoTIFF fixtures. It passed checks for source pixel-size retention, a finer output grid than the DEM, no averaging, 200-to-zero conversion, nearest-neighbor filling of 255, unchanged valid values and source ZIP files, domain masking, striped/uncompressed float32 output, the optional no-fill path, and failure when no valid donor exists. This regression test uses synthetic data. A subsequent real authenticated run completed the source notebook cells and generated the Ghana outputs described below.

## Completed Ghana run

All four official geographic 250 m ZIPs were downloaded and processed on 2026-10-29. The output has 4,865 rows × 3,666 columns, EPSG:4326, and source pixel size 0.002083330000000031 degrees in both axes. The DEM pixel size remains 0.00833333333333333 degrees; the impervious layer was not averaged to it.

The final layer contains 9,593,456 valid domain cells, with values ranging from 0 to 100 percent. Nearest-neighbor filling estimated 16,105 originally missing domain cells, leaving zero missing cells inside the sampled DEM mask. This is a completeness/format result, not a scientific validation of those estimates. Both GeoTIFFs were verified as float32, NoData=-9999, striped, and uncompressed, with matching grids and domain masks.

Only the parameter raster `crest_IM.tif` is stored in `Example/data_model/crest_parameters/`. Diagnostic masks and existing reports are stored in the sibling `Example/posproc_outputs/crest_diagnostics/` folder. The preview is displayed only in the notebook; no PNG is saved. The token was supplied through a hidden prompt and was not included in source files, manifests, reports, or notebook outputs. Existing downloads can be reused without authentication; processed outputs require `overwrite=True` to regenerate.

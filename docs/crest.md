# CREST calculation: technical details

For the basic workflow, see [Step 7 in the README](../README_library.md#step-7-create-the-crest-parameters).

## Inputs and method

`get_crest_parameters(input_dir, output_dir, *, dem=None, lakes=None, all_touched=False, diagnostics_dir=None, overwrite=False)` requires the aligned SoilGrids 2017 sand and clay rasters for sl1–sl7 and BDRICM_M_250m.tif. All rasters, including the optional DEM, must be single-band, north-up, and have exactly the same CRS, transform, and dimensions. No resampling is performed. Texture is in percent; bedrock is in centimetres.

The calculation preserves the equal average across seven point depths, texture classification, and lookup table used in EF5 Builder toolkit version 1.0. This is not thickness-weighted integration. Wm = effective porosity × 10 × bedrock_cm, in mm. Fc_Ksat retains the original conductivity-table multiplier of 10; the source notebook does not document the table units. b retains the original lookup value. No independent scientific validation of the legacy table is implied.

Invalid texture (masked, nonfinite, or outside 0–100%) masks all parameters unless repaired by the filling rules. Invalid bedrock (masked, nonfinite, or negative) masks Wm only unless filled. There is no 200 cm bedrock cutoff. Valid mean sand + clay above 100% raises an error. No imperviousness grid is calculated.

## Optional lake polygons

`lakes` accepts a vector path or GeoDataFrame containing polygons with a defined CRS and requires `dem`. Vectors are transformed to the raster CRS. Invalid polygons are repaired on a copy using `make_valid`; polygon components are retained and discarded non-polygon components are logged. Missing/empty geometries, non-polygon source layers, or unsuccessful repairs raise errors. Original vector files and the caller's GeoDataFrame remain unchanged.

Rasterization uses pixel centers by default. `all_touched=True` includes all touched cells. A spatial index limits each window to intersecting polygons. SoilGrids entries in selected lake cells are set to NaN in memory before filling. Those cells are excluded from candidates, donors, and parameter calculation. Parameter outputs and the filling mask use -9999 in lakes and outside the DEM. No aligned soil input files are rewritten.

Lake cells are not treated as DEM-invalid ocean cells for the coastal exception. Geometry alone cannot prove that a missing cell outside the supplied polygons is land. HydroLAKES targets lakes and reservoirs at least 10 hectares and is not a complete map of all water bodies. Source, license and reference: [HydroLAKES](https://www.hydrosheds.org/products/hydrolakes), CC-BY 4.0; Messager et al. (2016), [doi:10.1038/ncomms13603](https://doi.org/10.1038/ncomms13603).

## Filling outside lakes

Without lakes, the existing nearest-neighbor rules are preserved. With a DEM, finite valid non-lake cells containing incomplete SoilGrids data are candidates. A cell is filled if no other candidate occurs among its eight neighbors and an original complete neighbor exists. The coastal exception also permits connected candidates when a complete donor faces an actual DEM-invalid cell on the opposite side, including diagonals. The raster edge alone is not DEM NoData.

Only invalid entries are copied, using one original donor with all 15 valid inputs. Neighbor selection uses distance in raster CRS coordinates, with deterministic row/column tie-breaking. There is one pass; newly repaired cells never donate. Other gaps remain missing when lakes are omitted. Omitting the DEM disables filling.

With lakes supplied, every incomplete non-lake cell in the valid DEM is filled from the nearest original non-lake donor with all 15 valid inputs. Only invalid entries are replaced; valid source entries are preserved. Distances use Euclidean raster CRS coordinates (angular distances on geographic grids), not geodesic metres, with no distance cutoff. Equal-distance ties may select any nearest donor. Large holes can therefore receive distant extrapolated soil values. A missing land cell with no complete original donor anywhere in the domain raises an error rather than inventing values.

A preliminary windowed pass builds a SciPy cKDTree containing only boundary cells of complete valid land coverage. A nearest complete cell to an incomplete cell must occur on that boundary, so this reduces storage without changing the distance criterion. Memory scales with boundary count and tree size, not with 15 full-domain arrays; fragmented coverage can still require a large index. Donor values are sampled from the original rasters. Filled cells never become donors.

## Outputs and processing

Returns absolute paths keyed by `wm`, `fc`, and `b`: crest_Wm.tif, crest_Fc_Ksat.tif, crest_b.tif. With a DEM, the sibling `crest_diagnostics/crest_filled_mask.tif` records unchanged land (0), isolated fills (1), coastal fills (2), unrestricted nearest-land fills with lakes supplied (3), and NoData in lakes or outside the DEM. Raster metadata records lake-cell and filling counts.

Outputs are striped, Deflate-compressed float32 GeoTIFFs with NoData=-9999 for EF5 compatibility. Processing uses 512 × 512 windows with a one-cell halo for neighbor rules. Files are staged before replacement; each file replacement is atomic, not the entire output set. Existing outputs require `overwrite=True`.

Diagnostic masks are separate from model parameter rasters. `diagnostics_dir` defaults to `output_dir.parent / "crest_diagnostics"`; supply another diagnostics directory if different parameter sets share one parent. The parameter directory contains only model parameter outputs.

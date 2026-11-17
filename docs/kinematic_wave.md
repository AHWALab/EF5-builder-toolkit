# Kinematic wave parameters

The library uses the supplied Python RobustScaler/SVR models bundled in
`ef5_builder/models/kw`, not GAMLSS. The toolkit finds these package resources
automatically, regardless of the working directory. No model path is required.
The root `environment.yml` installs the KW dependency with the rest of the toolkit.
For a pip-only installation, run `python -m pip install '.[kw]'` from the toolkit root.
The model pickles record
scikit-learn 1.5.2; compatibility with another version is not established.
Load only trusted pickle files. No retraining or model-file conversion is performed.

## Alpha and beta

```python
from ef5_builder import get_kw_parameters

# Paths relative to the toolkit root; generate these with BASIN_AVG first.
inputs = "Example/posproc_outputs/basin_integration"
fac = "Example/data_model/basic/fam.tif"
result = get_kw_parameters(
    f"{inputs}/basin.area.tif", f"{inputs}/mean_temp.avg.tif",
    f"{inputs}/mean_precip.avg.tif", f"{inputs}/relief.ratio.tif",
    fac, "outputs/kw",
    precipitation_units="mm/year",  # Ghana example; select the actual input units.
    self_fam=True,  # Set to match SELFFAM for your FAC raster.
    layer_th=7,  # Example threshold; choose for your model grid.
)
print(result["alpha"], result["beta"])
print(f'Control-file TH must exceed {result["layer_th"]}')
```

Area must be basin area in km², temperature basin-averaged °C, precipitation
basin-averaged mean annual precipitation, and relief ratio dimensionless.
The exact predictor order is `log10(area), temperature, precipitation, relief_ratio`.
Alpha is `10**predicted_log_alpha`. Negative beta becomes `exp(10*beta)`.
Alpha above 1000 is NoData, as in the inference notebook. Invalid inputs and
nonpositive/nonfinite output coefficients become NoData independently per output.

Training precipitation units are inches/month, confirmed by the user.
Conversions below target those units.

Specify `precipitation_units` explicitly:

| Input units | Conversion to inches/month |
| --- | --- |
| `in/year` or `in` | Divide by 12 |
| `in/month` | No conversion |
| `mm/year` or `mm` | Divide by 25.4 and 12 |
| `mm/month` | Divide by 25.4 |

Bare `in` and `mm` are interpreted as annual totals by API convention;
length units alone do not specify a temporal basis. Prefer explicit units.
The legacy `precipitation_factor` argument remains supported, but cannot be
combined with `precipitation_units`. Input units and the applied factor are
recorded in output tags. No temporal aggregation is performed.


`layer_th` defines the prediction domain through `FAC > layer_th`.
The threshold defaults to 2. A warning reports the selected value; the control-file
TH must be strictly greater than this value. `result['th']` reports the layer threshold;
`control_th` is not an input argument. The threshold is a number of contributing
grid cells, not km². No
universal increment or calibrated TH is inferred. The threshold does not
change predictor values; it selects where predictions are written.
The models were trained on USGS station data from CONUS, so application
outside that region involves extrapolation.

## Alpha0 for one or several years

```python
from ef5_builder import get_kw_alpha0

outputs = get_kw_alpha0(
    ["manning_n_2001.tif", "manning_n_2002.tif"],
    slope="slope_m_m.tif", flow_accumulation="fac.tif",
    output_dir="outputs/kw", self_fam=True,
)
# One input is also supported: get_kw_alpha0("manning_n.tif", ...)
```

Returns `{input_path: output_path}`. Each output is named
`kw_alpha0_2001.tif` when the Manning filename contains one distinct year
(1900–2099), or `kw_alpha0.tif` when it has no year. Multiple inputs must
produce distinct output names, including when `overwrite=True`.
Manning n must be in s m^-1/3 and slope in m/m. Supply an existing slope
layer; this function does not derive slope from a DEM.

At the user's direction, this implements the inference notebook equation
`alpha0 = (n / sqrt(slope)) ** (3/5)` using the now-confirmed formulation. This legacy function retains its old clipping behavior;
prefer the DEM-derived function below for new work.
The notebook's global clipping rule is retained separately for each layer:
values >=1000 (including infinite values at zero slope) become the maximum
valid alpha0 strictly below 1000. If no such value exists, processing fails.
Valid FAC defines the domain; masks, nonfinite inputs, nonpositive Manning n,
and negative slopes become NoData. No slope floor is introduced.

All inputs must already have matching CRS, transform and dimensions and one
band. No resampling is performed. Computation is in 512×512 windows; alpha0
uses a second disk pass to apply its global clipping rule. Outputs are
float32, NoData=-9999, striped and Deflate-compressed for EF5. Files are staged
before replacement. Existing outputs require `overwrite=True`.

## FAC counting convention (required)

Both functions require `self_fam=True` or `self_fam=False` explicitly,
matching EF5's `SELFFAM` setting. True means FAC includes the current cell
(minimum possible count 1); False excludes it (minimum possible count 0).
A spatial subset need not contain a cell with that minimum. The library
does not infer this setting from the observed minimum and does not add or
subtract one from FAC or the thresholds. Valid counts below the specified
minimum raise an error; declared NoData cells remain excluded.

`get_kw_parameters` returns `result['self_fam']` along with `result['th']`.
Use the returned Boolean for `SELFFAM` in the appropriate EF5 configuration
section. Choose a strictly greater TH for the KW parameter block. Both functions record the
convention in output raster tags.

## ALPHA0 derived from the DEM (recommended)

```python
from ef5_builder import get_kw_alpha0_from_dem
alpha0 = get_kw_alpha0_from_dem(
    "manning_n_2001.tif", "dem.tif", "outputs/kw", min_slope=None,
)
```

Manning n is in s m^-1/3; DEM elevations must be in metres. The function
requires identical grids (CRS, transform, resolution and dimensions); align
Manning explicitly with `resample_and_subset` using the DEM as template.
Nearest-neighbor alignment retains the original lookup coefficients.

The method uses Horn 3x3 terrain slope in m/m and computes
`alpha0 = (n / sqrt(slope)) ** (3/5)`, following
[EF5 Global Parameters](https://github.com/HyDROSLab/EF5-Global-Parameters).
Projected horizontal units are converted to metres. Geographic grids use
ellipsoidal geodesic distances between neighboring pixel centres, varying by
latitude; degrees are never used as distances. Grids must be north-up and
unrotated. Projected-grid distances retain the projection's scale distortion.
The DEM vertical datum/units cannot be inferred from its horizontal CRS.

`min_slope=None` is the default: zero slopes become NoData. A finite positive
value explicitly floors slopes in m/m, including zero. This changes ALPHA0 in
flat areas and should be selected for the intended modeling application.
Negative/invalid slopes, invalid or nonpositive Manning n, and neighborhoods
with missing elevations become NoData. The one-cell outer border is NoData.
There is no clipping at 1000. Outputs outside positive Float32 range become
NoData. Windows include a one-cell halo to avoid processing seams.

Returns the output Path, named `kw_alpha0_2001.tif` for a Manning filename
containing the year 2001, or `kw_alpha0.tif` when there is no year. Year
detection recognizes 1900–2099 outside longer digit sequences. Filenames
containing multiple distinct years are rejected as ambiguous. The directory
is created automatically. Output is single-band Float32, NoData=-9999,
Deflate-compressed, striped, and on the DEM grid. Existing output requires
`overwrite=True`. The older `get_kw_alpha0` API remains available with its
legacy supplied-slope/FAC behavior and clipping rule.

## Terrain slope versus downstream D8 slope

The builder uses Horn 3x3 terrain slope for the DEM-derived ALPHA0 workflow.
This differs from the supplied `alpha0.ipynb`, whose slope is the absolute
DEM elevation difference between a cell and its FDIR-selected downstream
neighbor, divided by the horizontal distance between their centres.

| Property | Builder: Horn 3x3 | Supplied notebook: downstream D8 |
| --- | --- | --- |
| Quantity | Magnitude of estimated local X/Y terrain gradient | Elevation difference along one flow-direction link |
| Inputs | DEM | DEM, FDIR, FAC and link distance |
| Horizontal distances | Projected linear units converted to metres; geographic CRS ellipsoid for geodesic distances | WGS84 geodesic distances, assuming input coordinates are longitude/latitude |
| Required elevations | All nine cells in the neighborhood | Current cell and selected neighbor |
| Domain | Valid DEM neighborhood and positive Manning n | Slope requires FAC > 0 and valid D8 direction |
| Processing | Vectorized windows with a one-cell halo | Full rasters and Python pixel loops |

**Pros.** Horn does not require consistent FDIR and FAC layers. D8 explicitly
represents the selected flow link.

**Cons.** Horn averages local directional differences and does not directly
represent the selected routing link. D8 is sensitive to the chosen direction.
Neither method universally produces larger slopes.

**Assumptions.** Elevations must be in metres, with correct horizontal
georeferencing. Both methods exclude the outer raster border in these
implementations. Their missing-data requirements differ.

**Risks.** The notebook takes an absolute elevation difference, so an uphill
FDIR link becomes a positive slope rather than being flagged. It does not
check grid alignment or confirm that coordinates are geographic before
calling WGS84 geodesic calculations. Its slope masking also compares FDIR
against the HorLen dataset's NoData value. These are implementation caveats,
not reasons to treat every downstream-slope method as invalid.
The notebook additionally clips ALPHA0 >=1000 and fills missing ALPHA0 by
nearest neighbor; the new DEM-derived builder function does neither.

**Recommendation.** Retain Horn for the agreed terrain-slope formulation.
Reproducing the supplied notebook would require an explicit D8 alternative
and comparison of the complete workflows. For fixed Manning n,
`alpha0` is proportional to `slope**(-0.3)`, so changing the slope method
changes ALPHA0. This comparison describes inspected code, not a numerical
validation on Ghana or evidence that one method is universally superior.

## Bundled model files

The wheel and source distribution include the original `scaler.p`,
`alpha_model.p`, and `beta_model.p` byte for byte. These are the three files
needed for inference; legacy notebooks, training data and `scaler_fixed.p`
are not loaded. Removing the legacy builder folder does not affect model
lookup. No model retraining or conversion is performed.

For existing callers, `model_dir` remains an optional override accepting a
directory containing the same three filenames. Only load trusted pickles.
The optional `kw` dependency supplies the recorded scikit-learn version.

## Basin averaging checks

The example expects `basin.area.tif`, `relief.ratio.tif`,
`mean_temp.tif.avg.tif`, and `mean_precip.tif.avg.tif`. EF5 versions can
use different average-file names; set the notebook paths to the files produced
by your run. Use basin averages for the model predictors.

When a basin includes several independent outlets, provide parameter sets
for each outlet or set `defaultparamsgauge=0` in the task block, with
parameters defined for gauge 0 in both CREST and KW parameter sets.
The Ghana example uses this default. The same setting is used in the
CLIP_GAUGE task. See the [EF5 task examples](https://ef5docs.readthedocs.io/en/latest/style.html).

The error `Independent basin "1" lacks a water balance parameter set!`
interrupts basin initialization. In the inspected EF5 1.3 build, later output
writing can still occur with incomplete accumulation. Symptoms include
all-zero relief and relief ratio, basin area close to one cell, and river
length close to one link. Correct the task and regenerate the grids.
The `Unimplemented simulation run style "7"` message seen in some builds
should be assessed separately from earlier initialization errors.

Inspect the input and output masks as well as their ranges. In the inspected
EF5 build, missing climate inputs are treated as zero during averaging.
Review zero temperature or precipitation averages against the source NoData
mask before using them as model predictors.

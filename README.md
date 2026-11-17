# EF5 Builder Toolkit

A guide and Python library for constructing EF5 model layers, with Jupyter notebooks to run and inspect each step.

## Overview
This repository provides a step-by-step guide for setting up an EF5 model configuration. The included code and resources are designed to help users build a functional model for their own watershed. The methodology outlined here has been successfully used to create EF5 models at various resolutions for different regions.

The core of the EF5 model is the **control file**, which defines all the input data and parameters. This guide is structured around filling out the necessary blocks within this control file.

For a comprehensive understanding of EF5, please refer to the official documentation: [EF5 User Manual](https://ef5docs.readthedocs.io/).

For any questions, contact Vanessa Robledo (vanessa-robledodelgado@uiowa.edu) or the [AHWA Laboratory](https://ahwa.lab.uiowa.edu) Development team at [engr-ahwa-lab@uiowa.edu](mailto:engr-ahwa-lab@uiowa.edu).


## Set up your Conda environment

Choose either a new environment or your current environment. Run the setup commands from the **EF5-builder-toolkit repository root**, where `environment.yml` and `pyproject.toml` are located. The repository must be available on the machine running Python or the notebook kernel.

The root [environment.yml](environment.yml) installs the required libraries through conda-forge and installs this local toolkit through its pip subsection. This is a regular package installation performed automatically by Conda. No separate editable-install command is needed, and imports work from any directory after setup.

### Option A: Create an ef5-builder environment

```sh
conda env create --file environment.yml
conda activate ef5-builder
```

### Option B: Add the toolkit to an existing Conda environment

Replace `YOUR_ENV` with the name of your environment:

```sh
conda activate YOUR_ENV
conda env update --name YOUR_ENV --file environment.yml
```

This installs the same dependencies and toolkit in the selected environment. It may update dependency versions to satisfy the environment file. The command does not prune other packages.

### Use the environment in JupyterHub or VS Code

In the activated environment, register a notebook kernel:

```sh
python -m ipykernel install --user --name ef5-builder --display-name "EF5 Builder"
```

Select **EF5 Builder** as the notebook kernel. To launch Jupyter from this environment:

```sh
jupyter lab
```

Check the installation:

```sh
python -c "from ef5_builder import prepare_hydrosheds, prepare_from_dem, download_precipitation, download_soilgrids_2017, download_soilgrids_v2; print('EF5 Builder ready')"
```

## Project structure

```text
EF5-builder-toolkit/
├── environment.yml          # Conda environment for all example notebooks
├── pyproject.toml           # Python package configuration
├── README_library.md        # Step-by-step learning guide
├── ef5_builder/             # Functions imported by the notebooks
├── Example/
│   ├── Example_notebooks/   # Guided examples, in step order
│   ├── useful_datasets/    # Source datasets for the Ghana example
│   ├── data_model/         # Prepared EF5 inputs and parameter grids
│   └── posproc_outputs/    # Intermediate grids and inspection results
├── Resources/              # EF5 control examples and TIFF conversion scripts
└── docs/                   # Methods, input requirements, and troubleshooting
```

## Step-by-step instructions

### Step 1: Create DEM, flow direction, and flow accumulation grids

EF5 uses the DEM, flow direction (FDIR/DDM), and flow accumulation (FACC/FAM) to define its computational mesh. Run [Codes/1_Basic_grids_library.ipynb](Example/Example_notebooks/1_Basic_grids_library.ipynb), set your input and output paths, and choose a workflow. The notebook imports the installed functions directly:

```python
from ef5_builder import prepare_hydrosheds, prepare_from_dem
```

#### Option A: Prepare HydroSHEDS layers

Supply aligned HydroSHEDS DEM, ACC, and DIR rasters. Include a polygon region to clip and mask the outputs:

```python
outputs = prepare_hydrosheds(
    dem="data/hyd_dem.tif",
    facc="data/hyd_acc.tif",
    fdir="data/hyd_dir.tif",
    region="data/region.gpkg",  #Optional. A shapefile is also accepted 
    output_dir="data/basic",
)
```

Omit `region` (or set `region=None`) to convert the full raster extent:

```python
outputs = prepare_hydrosheds(
    dem="data/hyd_dem.tif",
    facc="data/hyd_acc.tif",
    fdir="data/hyd_dir.tif",
    output_dir="data/basic",
)
```

All three rasters are required and must be single-band, already in **EPSG:4326**, with identical CRS, transform, and dimensions. Use ACC upstream-cell counts rather than ACA upstream area. Accumulation must be nonnegative, and flow direction must use ESRI D8 codes (`1, 2, 4, 8, 16, 32, 64, 128`); `0` is also accepted for cells without a downstream direction. 

The function preserves the native grid without resampling or reprojection; vector coordinates are transformed to the raster CRS. Processing uses 512 × 512 pixel windows to support large source rasters. Global mosaicking is not included.

#### Option B: Derive drainage from a DEM

Supply a single-band, north-up DEM without rotation, already in **EPSG:4326**, and optionally a polygon region:

```python
outputs = prepare_from_dem(
    dem="data/my_dem.tif",
    region="data/region.gpkg",
    output_dir="data/basic",
)
```

By default (`condition=True`), the function fills pits and depressions, resolves flats, and calculates ESRI D8 direction and accumulation over the full supplied DEM before optionally clipping and masking to the region. Use `condition=False` to skip pit filling, depression filling, and flat resolution when deriving drainage from an already conditioned DEM:

```python
outputs = prepare_from_dem(
    dem="data/conditioned_dem.tif",
    output_dir="data/basic",
    condition=False,
)
```

This example omits `region`, so outputs cover the full DEM extent. Supply the complete upstream catchment even when clipping to a smaller region. If you need a different resolution or need to convert a projected DEM to EPSG:4326, prepare the DEM first, then derive drainage. Geographic routing uses angular pixel distances. The output DEM retains original elevations; conditioning is used only for routing.

#### Optional arguments

| Argument | Default | Behavior |
| --- | --- | --- |
| `region` | `None` | Process the full raster extent; supply a vector file path or GeoDataFrame to clip and mask. |
| `all_touched` | `False` | Use the default pixel-center polygon mask; set `True` to include all pixels touched by the region. Applies only when a region is supplied. |
| `overwrite` | `False` | Refuse existing output files; set `True` to replace them. Output paths must never replace input rasters. |
| `condition` | `True` | Fill pits and depressions and resolve flats before routing. Available only in `prepare_from_dem`. |

`all_touched`, `overwrite`, and `condition` are keyword-only arguments.

#### Outputs and EF5 settings

When a region is supplied, both functions accept a vector file path or a filtered GeoDataFrame with a defined CRS. All features are included; geometries must be nonempty, valid Polygons or MultiPolygons, and the region must be fully covered by the raster extent. Both functions return `dem`, `fdir`, and `facc`:

| Layer | Output | Data type | NoData |
| --- | --- | --- | --- |
| DEM | `dem.tif` | float32 | -9999 |
| FDIR / DDM | `ddm.tif` | float32 | -9999 |
| FACC / FAM | `fam.tif` | float32 | -9999 |

Accumulation derived by `prepare_from_dem` includes the current cell, so use `SelfFAM=true`; for supplied HydroSHEDS ACC, use the same setting for counts that include the current cell.

```ini
[Basic]
DEM=data/basic/dem.tif
DDM=data/basic/ddm.tif
FAM=data/basic/fam.tif
PROJ=geographic
ESRIDDM=true
SelfFAM=true
```

Use `PROJ=geographic` for these EPSG:4326 outputs. Neither function accepts projected raster inputs or reprojects drainage rasters.

---

### Step 2: Prepare precipitation forcing data

Run [Codes/2_Get_precipitation_files_library.ipynb](Example/Example_notebooks/2_Get_precipitation_files_library.ipynb). It provides a short example for each supported product and saves them in separate folders under `Example/posproc_outputs/precip`.

| Product | Time step | Output units |
| --- | --- | --- |
| IMERG Final | 30 minutes | mm/h |
| IMERG Early | 30 minutes | mm/h |
| MRMS Rate | 2 minutes | mm/h |
| MRMS Pass2 | 1 hour | mm |

IMERG requires a [PPS-registered email](https://registration.pps.eosdis.nasa.gov/). MRMS needs no account; choose bounds within its coverage rather than the Ghana example bounds.

```python
from ef5_builder import download_precipitation

outputs = download_precipitation(
    product="IMERG",
    imerg_run="early",  # "final" is also available.
    start="2025-06-01 00:00:00",
    end="2025-06-01 01:00:00",
    output_dir="data/precip/imerg_early",
    email="your-registered-email@example.com",
)
```

Use UTC dates aligned to the product's time step. `start` is included and `end` is excluded for source times. IMERG filenames label interval ends; MRMS keeps source timestamps. Existing files require `overwrite=True`.

Outputs are GeoTIFFs in the format required by EF5. Missing archive files raise an error rather than being replaced with another date or product.

See [precipitation technical details](docs/precipitation.md) for more information.

---

### Step 3: Prepare Potential Evapotranspiration (PET) Data

The final forcing dataset required is Potential Evapotranspiration.

**EF5 Control File Block:**
```
[PETForcing CLIMO]
TYPE=TIF
UNIT=mm/d
FREQ=1m
LOC=/data/pet/
NAME=PET.MM.tif
```

You can obtain PET data from several sources:

* **Global Dataset:** The University of Oklahoma hosts global PET datasets compatible with EF5. You can find them in the [EF5-Global-Parameters](https://github.com/HyDROSLab/EF5-Global-Parameters/tree/main/FAO_PET) repository or if you are interested in U.S. [US-Parameters](https://github.com/HyDROSLab/EF5-US-Parameters)
* **Regional Dataset (West Africa):** If you are building the West Africa or Ghana 1km model, pre-clipped PET files are available [here](https://github.com/RobledoVD/WAEF5-dockerized/tree/main/data/pet).

**Result:** Place the monthly PET `.tif` files (e.g., `PET.01.tif`, `PET.02.tif`, etc.) into the `/data/pet/` directory.

In this repository, FAO_PET files are provided to be used in the example for the Ghana model.

---

### Step 4: Preparing Grids for a Distributed Model

To create a distributed model using EF5 tasks like `CLIP_GAUGE` and `BASIN_AVG`, all input grids must be **perfectly aligned**. This means they must share the exact same spatial domain (extent), pixel resolution, and coordinate system. 

#### Inputs needed

* **For Water Balance (CREST)**

1. Soil texture rasters: Percent Sand, Percent Clay, and Percent Silt.

2. Depth to bedrock raster in centimetres for the CREST calculation (`BDRICM_M_250m.tif`).
> Download these layers using one of the SoilGrids functions below. 

* **Flow Routing (KinematicWave)**

1. DEM and their flow grid derivatives: DEM (dem) file, Flow Accumulation (facc) file, and Flow Direction (fdir) file.

2. Hydroclimatological grids: Mean Temperature (Celsius) and Mean Annual Total Precipitation (mm).

3. Manning's roughness coefficient.

#### Preparing domain grids

The **Digital Elevation Model (DEM)** serves as the master template for the entire model domain. All other grids must conform to it.

> **:warning: Critical Note on Basic Grids**
>
> It is incorrect to directly resample or reproject existing Flow Accumulation (`facc`) or Flow Direction (`fdir`) grids. If your DEM needs modification (e.g., re-projecting or resampling), you must use the **final, correct DEM** to regenerate the `facc` and `fdir` grids from scratch (Step 1 of this tutorial).

The **hydroclimatological grids** do not have to have the same domain grid, but do need to have the same coordinate system as dem and its derivatives. Use **Resources/prepare_ef5_inputs.sh** to preprocess the files so ef5 can use them. 

```bash
bash Resources/prepare_ef5_inputs.sh input.tif [output.tif]
```

#### 1. Water Balance (CREST): Download SoilGrids layers

Run [Codes/4_distributed_model_grids.ipynb](Codes/4_distributed_model_grids.ipynb) or call the two functions below to download regional soil texture data directly from ISRIC at their native resolution and CRS. Downloading and DEM alignment are separate steps. Use the **2017 release for the current CREST parameter calculation**: it supplies the seven depth levels and bedrock layer expected by that workflow.

```python
from ef5_builder import download_soilgrids_2017, resample_and_subset
```

##### Option A: SoilGrids 2017

```python
outputs = download_soilgrids_2017(
    output_dir="data/soilgrids_2017",
    dem="data/basic/dem.tif",
)
```

Outputs use names such as `SNDPPT_M_sl1_250m.tif`, `CLYPPT_M_sl1_250m.tif`, `SLTPPT_M_sl1_250m.tif`, and `BDRICM_M_250m.tif`. The `250m` suffix identifies the source product; the output grid retains the native source resolution. The return dictionary uses keys such as `sand_sl1`, `clay_sl1`, and `bedrock`.

The complete required CREST input set is:

```text
BDRICM_M_250m.tif
CLYPPT_M_sl1_250m.tif
CLYPPT_M_sl2_250m.tif
CLYPPT_M_sl3_250m.tif
CLYPPT_M_sl4_250m.tif
CLYPPT_M_sl5_250m.tif
CLYPPT_M_sl6_250m.tif
CLYPPT_M_sl7_250m.tif
SNDPPT_M_sl1_250m.tif
SNDPPT_M_sl2_250m.tif
SNDPPT_M_sl3_250m.tif
SNDPPT_M_sl4_250m.tif
SNDPPT_M_sl5_250m.tif
SNDPPT_M_sl6_250m.tif
SNDPPT_M_sl7_250m.tif
```

Select fewer layers when needed:

```python
outputs = download_soilgrids_2017(
    output_dir="data/soilgrids_2017_subset",
    dem="data/basic/dem.tif",
    properties=("sand", "clay"),
    depths=("sl1", "sl2"),
    include_bedrock=False,
)
```

Sources: [2017 archive](https://files.isric.org/soilgrids/former/2017-03-10/data/) and [ISRIC 2017 property units and depths](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_2017.html).

##### Option B: SoilGrids v2 (Not recommended for CREST)
We have included the optio to download SoilGrids v2. However it is the user's job to adapt the layers to the Crest computation.

```python
from ef5_builder import  download_soilgrids_v2

outputs = download_soilgrids_v2(
    output_dir="data/soilgrids_v2",
    dem="data/basic/dem.tif",
)
```

The default downloads **12 mean layers**: sand and clay for six depth intervals (`0-5cm`, `5-15cm`, `15-30cm`, `30-60cm`, `60-100cm`, `100-200cm`). ISRIC stores these texture values in **g/kg**; the function divides by **10** to obtain percent. For example, `350 g/kg` becomes `35%`. NoData is masked before conversion.

Converting units does **not** make the releases interchangeable. The v2 function does not invent a bedrock layer or rename its intervals as `sl1`–`sl7`. **Adapting CREST to v2 requires a separate choice of depth integration and bedrock data.**

Sources: [v2 archive](https://files.isric.org/soilgrids/latest/data/) and [ISRIC v2 units and depth intervals](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html).



##### Resample and subset downloaded layers

After downloading, align each soil raster to your model DEM with `resample_and_subset`. The DEM supplies the output extent, pixel size, and coordinate system. This loop processes each TIFF in the download folder and saves an EF5-ready copy in `data/soilgrids_aligned`.

```python
from pathlib import Path
from ef5_builder import resample_and_subset

input_dir = Path("data/soilgrids_2017")
output_dir = Path("data/soilgrids_aligned")

for path in sorted(input_dir.glob("*.tif")):
    resample_and_subset(
        input_file=path,
        output_file=output_dir / path.name,
        template="data/basic/dem.tif",
        mask_template=True,
    )
```

`mask_template=True` keeps cells inside the DEM's valid area. Set `overwrite=True` when rerunning this step to replace existing outputs. More resampling options and file-format details are in [the alignment reference](docs/soilgrids.md#align-downloaded-rasters).

#### 2. Flow Routing (KW)

Prepare the inputs that describe how water moves through your model area. In this step you will create a Manning roughness grid from land cover and prepare mean temperature and precipitation grids. Step 6 calculates basin averages, and Step 8 uses these inputs to estimate the KW parameters.

1. Download MODIS annual land-cover GeoTIFFs using the Earth Engine script linked below. Choose the `LC_Type2` product and the year you want to model.
2. Run `annual_manning_from_modis` to assign a roughness value to each land-cover class.
3. Align the resulting Manning grid to your DEM using `resample_and_subset`, as shown in notebook 4.
4. Prepare `mean_temp.tif` and `mean_precip.tif` for `BASIN_AVG`. The Ghana example uses temperature in °C and annual precipitation in mm/year.

```python
from ef5_builder import annual_manning_from_modis

annual_n = annual_manning_from_modis(
    input_dir="data/modis_lc_type2",
    output_dir="data/manning/native",
    file_pattern="MCD12Q1_UMD_*.tif",
)
```

The function saves one `manning_n_YYYY.tif` for each detected year. Use single-band EPSG:4326 MODIS files with the year in their names and NoData coded as 255. [Open notebook 4](Example/Example_notebooks/4_Get_Distributed_Model_Grids.ipynb).

The ready-to-use Earth Engine script is in [export_modis_umd.js](Example/Example_notebooks/earth_engine/export_modis_umd.js). Export instructions, roughness values, and assumptions are in [Manning documentation](docs/manning.md).

### Step 5: Automatically defining all outlets locations with `CLIP_GAUGE`

Forcing EF5 to model every pixel within a domain can be a tedious process if done manually. Instead of creating hundreds of `[Gauge]` blocks by hand, you can use a specific EF5 run mode to automatically identify all outlets and generate the necessary configuration.

This process uses the `CLIP_GAUGE` style. Here is the step-by-step guide:

1. Configure the CLIP_GAUGE Control File
You will need to run EF5 with a temporary control file specifically for this task.

- A sample file is provided in this folder:  [`Resources/ef5_clip_gauge_sample.txt`](Resources/ef5_clip_gauge_sample.txt). Use it as your starting point.
- In the [Task] block, ensure the run style is set to CLIP_GAUGE.

```
[Task GAUGECLIP]
STYLE=CLIP_GAUGE
MODEL=crest
ROUTING=KW
BASIN=0
PRECIP=IMERG
PET=CLIMO
OUTPUT=/outputs/ 
PARAM_SET=myCREST
ROUTING_PARAM_Set=myKinematicWave
defaultparamsgauge=0
TIMESTEP=30u
TIME_BEGIN=202406210000
TIME_END=202406210400
```

> **❗Important:** The other blocks in this sample file (e.g., paths to forcing data) must still contain valid entries. EF5 may check for the existence of these files even though they are not used in the CLIP_GAUGE operation.

2. Run EF5 and Check the Outputs:

Run EF5 using the control file configured in the previous step. When the process is complete, two new files will be generated:

- `maskgrid.tif`: This is a raster file you can open in QGIS or another GIS software. Use it to visually verify that the drainage basins within your domain have been correctly identified.
- `basin_new.txt`: This text file contains the auto-generated [Gauge] and [Basin] blocks for your model.

The contents of basin_new.txt will look something like this:

```
[Gauge 0] cellx=28 celly=6 outputts=false #Num Cells = 360.000000
[Gauge 1] cellx=28 celly=4 outputts=false #Num Cells = 148.000000
[Gauge 2] cellx=10 celly=1 outputts=false #Num Cells = 44.000000
...
...
[Gauge 45] cellx=5 celly=0 outputts=false #Num Cells = 0.000000
[Basin 0]
gauge=0 gauge=1 gauge=2 gauge=3 gauge=4 gauge=5 gauge=6 gauge=7 gauge=8 gauge=9 gauge=10 gauge=11 gauge=12 gauge=13 gauge=14 gauge=15 gauge=16 gauge=17 gauge=18 gauge=19 gauge=20 gauge=21 gauge=22 gauge=23 gauge=24 gauge=25 gauge=26 gauge=27 gauge=28 gauge=29 gauge=30 gauge=31 gauge=32 gauge=33 gauge=34 gauge=35 gauge=36 gauge=37 gauge=38 gauge=39 gauge=40 gauge=41 gauge=42 gauge=43 gauge=44 gauge=45

```
3. Update Your Control File:

Now, you will transfer this configuration into the main control file that you will use to run actual simulations.

- Open `basin_new.txt` and copy its entire contents.
- Open your final simulation control file.
- Paste the copied text into the file. The correct location is between the last forcing block (e.g., [PETForcing CLIMO]) and the first parameter block (e.g., [CrestParamSet]).
- This process defines a single, comprehensive basin named [Basin 0] that includes all the generated gauges. If any other blocks in your control file need to reference a basin, ensure they are set to use 0.

---

### Step 6: Calculate Basin-Integrated Variables with `BASIN_AVG`

To generate certain parameters, like those for the kinematic wave routing model, you first need to calculate basin-wide average values from your gridded data (e.g., mean precipitation). The `BASIN_AVG` task in EF5 is designed for this purpose.

Follow these steps to perform the basin integration:

1. Create a new folder for this operation (e.g., basin_integration/).

2. Copy the grid files that need to be integrated (`mean_temp.tif` and `mean_precip.tif`) into this new `basin_integration/` folder.

3. Modify your main simulation control file to perform this specific task.

> ❗**Important:** In the `[Task]` block, set the `STYLE` to `BASIN_AVG`.
> Point the `OUTPUT` variable to the directory you just created.
> Ensure the other settings match your project's configuration.

The new task block in your control file using basin average function of EF5 should looks like this:

```
[Task BASINAVGING] 
STYLE=BASIN_AVG 
MODEL=crest 
ROUTING=KW 
BASIN=0 
PRECIP=IMERG 
PET=CLIM 
OUTPUT=/basin_integration/ 
defaultparamsgauge=0 
PARAM_SET=myCREST 
ROUTING_PARAM_Set=myKinematicWave 
TIMESTEP=30u 
TIME_BEGIN=202010100830 
TIME_END=202010110400 
```

> **Note:** Ensure that the names for BASIN, PET, PARAM_SET, etc., are consistent with the rest of your control file.

4. Save the modified control file and run EF5 using this control file. The model will print status updates to the screen. The process should only take a few seconds, but may be longer for very high-resolution domains.

The process will finish by printing an error message to the screen. **This is normal for this specific task.**

> **:warning: Expected Error**
> `ERROR:src/ExecutionController.cpp(94): Unimplemented simulation run style "7"`
> You can safely ignore this error. It indicates that the BASIN_AVG operation completed successfully.

5. Verify the Output:  Navigate to the output folder you created (e.g., basin_integration/). You will now find new geotiff files containing the results of the calculation, such as `mean_temp_basin_avg.tif` and `mean_precip_basin_avg.tif`. These files contain the basin-integrated values needed for subsequent steps.

---

### Step 7: Create the CREST parameters

At this point, you should have the soil texture rasters clipped and regridded for your area domain (See Step 4 in this guide). The input folder must contain these 15 files:

- Sand: `SNDPPT_M_sl1_250m.tif` through `SNDPPT_M_sl7_250m.tif`.
- Clay: `CLYPPT_M_sl1_250m.tif` through `CLYPPT_M_sl7_250m.tif`.
- Bedrock depth: `BDRICM_M_250m.tif`.

Run [Example/Example_notebooks/7_Crest_parameters_library.ipynb](Example/Example_notebooks/7_Crest_parameters_library.ipynb) for the Ghana example, or call:

```python
from ef5_builder import get_crest_parameters

outputs = get_crest_parameters(
    input_dir="data/soilgrids_aligned",
    output_dir="data/parameters/crest",
    dem="data/basic/dem.tif",
    overwrite=False,
)
```

The function creates `crest_Wm.tif`, `crest_Fc_Ksat.tif`, and `crest_b.tif`. With `dem` supplied, it also fills small isolated and coastal gaps and saves `crest_diagnostics/crest_filled_mask.tif` beside the parameter folder to show where filling occurred. Larger gaps may remain. Existing files require `overwrite=True`.

#### Impervious surface layer

Run [Example/Example_notebooks/7b_Impervious_layer_processing.ipynb](Example/Example_notebooks/7b_Impervious_layer_processing.ipynb) to prepare `crest_IM.tif` for Ghana using **GMIS 2010**. The notebook finds the official **250 m** tiles intersecting the DEM bounds through [NASA Earthdata](https://search.earthdata.nasa.gov/search/granules?p=C3550185860-ESDIS).

Earthdata file downloads require a login token. Enter it in the notebook's hidden prompt, or download the listed ZIP files manually after signing in. Your PPS email for IMERG is not an Earthdata token.

The output stays at the source's **250 m pixel size**, in percent (0–100), without averaging to the DEM grid. The DEM defines the area and mask. Values outside the built-up mask become 0%; missing cells can be filled with nearest-neighbor estimates. A separate mask in `Example/posproc_outputs/crest_diagnostics/` shows those estimates. Source files remain unchanged. See [impervious-layer technical details](docs/impervious.md) for codes, source access, and limitations.

Once you get IM layer, the outputs will help you to fill out the next block in the control file:

**EF5 Control File Block:**
```
[CrestParamSet MyCREST]
wm_grid=/data/Parameters/crest_Wm.tif
im_grid=/data/Parameters/crest_IM.tif
fc_grid=/data/Parameters/crest_Fc_Ksat.tif
b_grid=/data/Parameters/crest_b.tif
gauge=0
wm=1.0
b=1.0
im=0.01
ke=1.0
fc=1.0
iwu=0
```
---

### Optional: Keep lake cells as NoData

Pass your region's lake **polygon** layer when creating the parameters:

```python
outputs = get_crest_parameters(
    input_dir="data/soilgrids_aligned",
    output_dir="data/parameters/crest",
    dem="data/basic/dem.tif",
    lakes="data/lakes.gpkg",
)
```

The function masks lake cells first, then fills all remaining missing SoilGrids cells inside the DEM using their nearest valid land neighbor. Lakes remain NoData and cannot supply values to nearby cells. Large gaps may use distant neighbors; inspect the results. Invalid lake polygons are repaired on a copy; your source files are preserved. A shapefile or GeoDataFrame is also accepted. Do not use lake pour points.

Omit `lakes` or set `lakes=None` to process as before. When providing lakes, also provide `dem`. The Ghana example uses `Example/useful_datasets/hydrolakes/ghana_hydrosheds.shp`. See [technical details](docs/crest.md) for masking and filling rules.

---

### Step 8: Create the Kinematic Wave (KW) Parameters

The final step is to compute the routing parameters required for the Kinematic Wave model. Use `get_kw_parameters` for alpha and beta and `get_kw_alpha0_from_dem` for ALPHA0 from aligned Manning and DEM rasters.

```python
from ef5_builder import get_kw_parameters, get_kw_alpha0_from_dem

kw_alpha_beta = get_kw_parameters(
    basin_area="basin.area.tif",
    temperature="mean_temp.avg.tif",
    precipitation="mean_precip.avg.tif",
    relief_ratio="relief.ratio.tif", 
    flow_accumulation="fac.tif", 
    output_dir="outputs/kw",
    precipitation_units="mm/year",  # Ghana example; select the actual input units.
    self_fam=True,  # Set to match SELFFAM for your FAC raster.
    layer_th=2,  # Default prediction threshold.
    overwrite=True,
)

alpha0 = get_kw_alpha0_from_dem(
    manning="manning_n_2001.tif", 
    dem="dem.tif", 
    output_dir="outputs/kw", 
    min_slope=None,
    overwrite=True,
)

print(f'Control-file TH must exceed {kw_alpha_beta["layer_th"]}')
```

Inputs must already be aligned. Temperature units must be °C and Precipitation must be in mm/month, specify your precipitation units with precipitation_units so the library can automatically convert to the needed units by the kinematic wave model. 
With min_slope=None, flat terrain and incomplete slope neighborhoods become NoData. See [KW details](docs/kinematic_wave.md) for input requirements, clipping, model compatibility and returned paths.
ALPHA0 uses **Horn 3×3 terrain slope**, estimated from the DEM's local X and Y
gradients.

For Ghana example, follow the notebook
[8_Get_KinematicWave_parameters.ipynb](Example/Example_notebooks/8_Get_KinematicWave_parameters.ipynb).


The outputs will help you to fill out the next block in the control file:

**EF5 Control File Block:**
```
[kwparamset MyKW]
alpha_grid=parameters/kw_alpha.tif
beta_grid=parameters/kw_beta.tif
alpha0_grid=parameters/kw_alpha0.tif
gauge=0
alpha=1.0
alpha0=1.0
beta=0.6
under=0.001
leaki=0.03
th=12.0
isu=0.0
```
### Final Step: Run your Simulations.

Set `STYLE=SIMU` in your final control file to run a hydrologic simulation. The task selects the water balance model (`CREST`), routing method (`KW`), basin, forcing blocks, and parameter sets prepared in the previous steps. `OUTPUT` sets the results directory. `TIMESTEP=30u` means a 30-minute model step, and `TIME_BEGIN` / `TIME_END` define the simulation period using 12-digit timestamps (year, month, day, hour, minute). `OUTPUT_GRIDS` selects raster results, with multiple variables separated by `|`. See the [official EF5 task-block documentation](https://ef5docs.readthedocs.io/en/latest/tasks.html).

Add the following blocks after your model parameter blocks. The example assumes `[Basin 0]`, `[PrecipForcing IMERG]`, `[PETForcing FAO_PET]`, `[CrestParamSet MyCREST]`, and `[kwparamset MyKW]` are already defined. Adjust these names, dates, and output path to match your configuration.

```ini
[Task RunSimulation]
STYLE=SIMU
MODEL=CREST
ROUTING=KW
BASIN=0
PRECIP=IMERG
PET=FAO_PET
PARAM_SET=MyCREST
ROUTING_PARAM_SET=MyKW
OUTPUT=Example/posproc_outputs/simulations/
OUTPUT_GRIDS=STREAMFLOW|MAXUNITSTREAMFLOW|MAXSTREAMFLOW|PRECIPACCUM
TIMESTEP=30u
TIME_BEGIN=202506010030
TIME_END=202506080100

[Execute]
TASK=RunSimulation
```

The `[Execute]` block selects `RunSimulation` for execution. Save the complete control file as `control.txt`, create the output directory, and run the following command from the repository root with the EF5 executable on your PATH. See [Running EF5](https://ef5docs.readthedocs.io/en/latest/running.html#run-ef5-in-the-terminal).

```bash
ef5 control.txt
```

# Cite this package as
Robledo, V., & Vergara, H. (2026). EF5 Builder Toolkit: A Complete Guide to Constructing and Implementing an EF5 Model from Scratch. (Version 2.0.0) [Computer software]. Zenodo. [https://doi.org/10.5281/zenodo.24293720]
(https://zenodo.org/records/24293720)

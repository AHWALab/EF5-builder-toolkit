# Building an EF5 Model: A Step-by-Step Guide

A complete guide to constructing and implementing an EF5 model from scratch using Python and Jupyter Notebooks.

## Overview
This repository provides a step-by-step guide for setting up an EF5 model configuration. The included code and resources are designed to help users build a functional model for their own watershed. The methodology outlined here has been successfully used to create EF5 models at various resolutions for regions like Ghana, West Africa, and Iowa, USA.

The core of the EF5 model is the **control file**, which defines all the input data and parameters. This guide is structured around filling out the necessary blocks within this control file.

For a comprehensive understanding of EF5, please refer to the official documentation: [EF5 User Manual](https://ef5docs.readthedocs.io/).

For any questions, contact Vanessa Robledo (vanessa-robledodelgado@uiowa.edu) or the [AHWA Laboratory](https://ahwa.lab.uiowa.edu) Development team at [engr-ahwa-lab@uiowa.edu](mailto:engr-ahwa-lab@uiowa.edu).

---

## Prerequisites

You have two options for running the code in this guide:

#### 1. Google Colaboratory (Recommended)
The easiest way to get started is with Google Colab, as all notebooks are adapted to run in that environment.
- **Link:** [https://colab.research.google.com/](https://colab.research.google.com/)

#### 2. Local Conda Environment
If you prefer to work on your local machine, we recommend creating a new Conda environment to avoid package conflicts.

1.  **Create the environment from the provided file:**
    The `environment.yml` file is located in the `/prerequisites` folder. Run the following command in your terminal:
    ```sh
    conda env create -f prerequisites/environment.yml
    ```
    *(This process may take several minutes.)*

2.  **Activate the new environment:**
    ```sh
    conda activate ef5_env
    ```

---

## Project Structure

All necessary files are organized into the following folders:

-   **/Codes:** Contains all Jupyter Notebooks for each step.
-   **/Prerequisites:** Includes the Conda environment file.

---

## Step-by-Step Instructions

The following steps will walk you through generating the required input files for the EF5 model, using the control file blocks as our guide.


### Step 1: Getting the basic files

This first step creates the basic grid files that EF5 employs to define the computational mesh: the Digital Elevation Model (DEM), Flow Direction Model (DDM), and Flow Accumulation Model (FAM).

**EF5 Control File Block:**
```
[Basic]
DEM=data/basic/dem.tif
DDM=data/basic/ddm.tif
FAM=data/basic/fam.tif
PROJ=geographic
ESRIDDM=true
SelfFAM=false
```
Users have several options such as QGIS or ArcGIS based methodologies. However, in this tutorial you have two options depending on your available data:

* **Option A: Use HydroSHEDS Data**
    If you want to create a model based on the readily available HydroSHEDS dataset, use the following notebook:
    - **Notebook:** [`/Codes/1_GettingBasicFiles.ipynb`](/Codes/1_GettingBasicFiles.ipynb)

* **Option B: Use a Custom DEM**
    If you have your own high-resolution DEM, use this notebook to derive the DDM and FAM grids:
    - **Notebook:** [`/Codes/1b_CreateBasicGrids.ipynb`](/Codes/1b_CreateBasicGrids.ipynb)


**Result:** After running the appropriate notebook, ensure your three output files (`dem.tif`, `ddm.tif`, `fam.tif`) are saved in the `/data/basic/` directory.

---

### Step 2: Prepare Precipitation Forcing Data

Next, you will download and format the precipitation data. This guide uses IMERG v07 for its excellent spatial and temporal resolution.

**EF5 Control File Block:**
```
[PrecipForcing IMERG]
TYPE=TIF
UNIT=mm/h
FREQ=30u
LOC=/data/precip/
NAME=imerg.YYYYMMDDHHUU.tif
```
Follow the instructions in the notebook below to process the precipitation files.
- **Notebook:** [`/Codes/2_Get_precipitation_files.ipynb`](/Codes/2_Get_precipitation_files.ipynb)

**Result:** Place all generated precipitation `.tif` files into the `/data/precip/` directory.

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

---

### Step 4: Preparing Grids for a Distributed Model

To create a distributed model using EF5 tasks like `CLIP_GAUGE` and `BASIN_AVG`, all input grids must be perfectly aligned. This means they must share the exact same spatial domain (extent), pixel resolution, and coordinate system. 

#### Inputs needed

* **For Water Balance (CREST)**

1. Soil texture rasters: Percent Sand, Percent Clay, and Percent Silt.
> You can access to these files in [soilgrids.org](https://files.isric.org/soilgrids/former/2017-03-10/data/) 

2. Depth to bedrock raster in meters

* **Flow Routing (KinematicWave)**

1. DEM and their flow grid derivatives: DEM (dem) file, Flow Accumulation (facc) file, and Flow Direction (fdir) file.

2. Hydroclimatological grids: Mean Temperature (Celsius) and Mean Annual Total Precipitation (mm).

3. Manning's roughness coefficient.

#### Preparing domain grids

The **Digital Elevation Model (DEM)** serves as the master template for the entire model domain. All other grids must conform to it.

> **:warning: Critical Note on Basic Grids**
>
> It is incorrect to directly resample or reproject existing Flow Accumulation (`facc`) or Flow Direction (`fdir`) grids. If your DEM needs modification (e.g., re-projecting or resampling), you must use the **final, correct DEM** to regenerate the `facc` and `fdir` grids from scratch (Step 1 of this tutorial).

The hydroclimatological grids do not have to have the same domain grid, but do need to have the same coordinate system as dem and its derivatives. If this is not the case, use a GIS-based tool to re-project grids to match the same coordinate system as dem. An example of this kind of tool is GDAL's program gdalwarp. If all grids have the same coordinate system, all is needed is to resample and subset to match dem's pixel resolution and domain box. 

To help with this, a C-Shell script is included in this folder "resample_and_subset.csh". The following illustrates the usage:

```sh
./resample_and_subset.csh <input_file.tif> <output_file.tif> <template.tif>
```

**input_file.tif:** The grid file that needs to be processed (e.g., climatological_temperature.tif).
**output_file.tif:** The desired name for the processed, aligned file (e.g., mean_temp.tif).
**template.tif:** The master grid to use as a template for pixel resolution and domain coordinates (this should be your final dem.tif).

Example:

```sh
./resample_and_subset.csh climatological_temperature.tif mean_temp.tif dem.tif
```

Use the C-Shell script for all the inputs listed above.

---

### Step 5: Automatically defining all outlets locations with `CLIP_GAUGE`

Forcing EF5 to model every pixel within a domain can be a tedious process if done manually. Instead of creating hundreds of `[Gauge]` blocks by hand, you can use a specific EF5 run mode to automatically identify all outlets and generate the necessary configuration.

This process uses the `CLIP_GAUGE` style. Here is the step-by-step guide:

1. Configure the CLIP_GAUGE Control File
You will need to run EF5 with a temporary control file specifically for this task.

- A sample file is provided in this folder:  [`/Resources/ef5_clip_gauge_sample.txt`]. Use it as your starting point.
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

At this point, you should have the soil texture rasters clipped and regridded for your area domain (see Step 4 in this guide). Place them into a folder `CREST_input`. The expected files in this folder are:

`BDRICM_M.tif      
CLYPPT_M_sl3.tif  
CLYPPT_M_sl6.tif  
SNDPPT_M_sl2.tif  
SNDPPT_M_sl5.tif
CLYPPT_M_sl1.tif  
CLYPPT_M_sl4.tif  
CLYPPT_M_sl7.tif  
SNDPPT_M_sl3.tif  
SNDPPT_M_sl6.tif
CLYPPT_M_sl2.tif  
CLYPPT_M_sl5.tif  
SNDPPT_M_sl1.tif  
SNDPPT_M_sl4.tif  
SNDPPT_M_sl7.tif`

Use the following notebook and follow its instructions:
- **Notebook:** [`/Codes/4_Crest_parameters_estimation.ipynb`](/Codes/4_Crest_parameters_estimation.ipynb)

The outputs will help you to fill out the next block in the control file:

**EF5 Control File Block:**
```
[CrestParamSet MyCREST]
wm_grid=/data/Parameters/crest_Wm.tif
im_grid=/data/Parameters/crest_IM.tif
fc_grid=/data/Parameters/crest_Fc_Ksat.tif
b_grid=/data/Parameters/crest_b.tif

gauge=6607500
wm=1.0
b=1.0
im=0.01
ke=1.0
fc=1.0
iwu=0
```

❗**Impervious Layer**

You should have noticed that there is not `crest_IM.tif` file in the outputs folder. It is not necessary to calculate the impervious layer because there are  multiple satellite products available for this, just make sure the units are in percentage. In this case we use the [Global Man-made Impervious Surface (GMIS) Dataset From Landsat](https://search.earthdata.nasa.gov/search/granules?p=C3550185860-ESDIS&pg[0][v]=f&pg[0][gsk]=-start_date&q=GMIS&tl=1278028800!3!!). Please read the documentation of this product and process it according to that. We include a notebook to help with this process: 
- **Notebook:** [`/Codes/4b_IM_layer_processing.ipynb`](/Codes/4b_IM_layer_processing.ipynb)

---

### Step 8: Create the Kinematic Wave (KW) Parameters

The final step is to compute the routing parameters required for the Kinematic Wave model. To do this, you must prepare a set of input grids. Place the following files into the folder: `/codes/KW_parameters/inputs_grids/`

Required files:

`basin.area.tif
dem.tif
fam.tif
manning_n.tif
mean_precip.avg.tif
mean_temp.avg.tif
relief.ratio.tif`

>❗**Important:**
> Ensure the filenames match exactly. EF5 may generate average grid files with names like mean_precip.tif.avg.tif. If this happens, rename the files accordingly so they match the expected input format.

Open and follow the instructions in the following Jupyter notebook to compute the KW parameters:

- **Notebook:** [`/Codes/5_KM_parameters/5_Kinematic_Wave_Parameter_Estimation.ipynb`](/Codes/5_KM_parameters/5_Kinematic_Wave_Parameter_Estimation.ipynb)

The outputs will help you to fill out the next block in the control file:

**EF5 Control File Block:**
```
[kwparamset MyKW]
alpha_grid=parameters/alpha_kw.tif
beta_grid=parameters/beta_kw.tif
alpha0_grid=parameters/alpha0_kw.tif
under_grid=parameters/crest_Fc_Ksat.tif
gauge=0
alpha=1.0
alpha0=1.0
beta=0.6
under=0.001
leaki=0.03
th=12.0
isu=0.0
```
# Cite this package as
Robledo, V., Henao, S., Vergara, H. (2025). A Complete Guide to Constructing and Implementing an EF5 Model from Scratch. (v1.0). https://doi.org/10.5281/zenodo.15644400




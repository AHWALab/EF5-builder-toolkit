# SoilGrids downloads

Run [notebook 4](../Example/Example_notebooks/4_Get_Distributed_Model_Grids.ipynb) or call the two functions below to download regional soil texture data directly from ISRIC at their native resolution and CRS. Downloading and DEM alignment are separate steps. Use the **2017 release for the current CREST parameter calculation**: it supplies the seven depth levels and bedrock layer expected by that workflow.

```python
from ef5_builder import download_soilgrids_2017, resample_and_subset
```

## Option A: SoilGrids 2017

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

## Option B: SoilGrids v2 (Not recommended for CREST)
The toolkit supports SoilGrids v2 downloads. Using these layers for CREST requires adapting the parameter calculation to their depths and supplying bedrock data.

```python
from ef5_builder import  download_soilgrids_v2

outputs = download_soilgrids_v2(
    output_dir="data/soilgrids_v2",
    dem="data/basic/dem.tif",
)
```

The default downloads **12 mean layers**: sand and clay for six depth intervals (`0-5cm`, `5-15cm`, `15-30cm`, `30-60cm`, `60-100cm`, `100-200cm`). ISRIC stores these texture values in **g/kg**; the function divides by **10** to obtain percent. For example, `350 g/kg` becomes `35%`. NoData is masked before conversion.

The releases use different depth definitions and require different processing. The v2 outputs retain their interval names and exclude bedrock. **Adapting CREST to v2 requires a separate choice of depth integration and bedrock data.**

Sources: [v2 archive](https://files.isric.org/soilgrids/latest/data/) and [ISRIC v2 units and depth intervals](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html).



## Align downloaded rasters

`resample_and_subset` matches the template's CRS, transform, dimensions, and pixel size.
It supports `nearest` (default), `average`, and `bilinear` sampling.
`mask_template=True` excludes invalid template cells; the default uses its rectangular extent.
Existing outputs require `overwrite=True`. Use this function for continuous layers such as soil,
Manning roughness, and climate grids. Derive drainage direction and accumulation from the final DEM.

Outputs use single-band Float32 GeoTIFF, NoData=-9999, DEFLATE compression,
striped storage (`TILED=NO`), and `INTERLEAVE=PIXEL`. GDAL can report band
interleaving for a single-band file. `BIGTIFF=IF_SAFER` allows large files.

To convert a TIFF while preserving its existing grid, use the scripts in `Resources`.
Run `bash Resources/prepare_ef5_inputs.sh input.tif [output.tif]` on Linux/macOS,
or `Resources\prepare_ef5_inputs.cmd input.tif [output.tif]` in Windows CMD.
GDAL must be on PATH. The default output ends in `_ef5.tif`; existing outputs are protected.

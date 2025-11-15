# Creación de un modelo de EF5: guía paso a paso

Una guía completa para construir e implementar un modelo de EF5 desde cero utilizando Python y Jupyter Notebooks.

## Resumen
Este repositorio proporciona una guía paso a paso para configurar un modelo de EF5. El código y los recursos incluidos están diseñados para ayudar a los usuarios a crear un modelo funcional para su propia cuenca hidrográfica. La metodología aquí descrita se ha utilizado con éxito para crear modelos de EF5 con diferentes resoluciones para regiones como Ghana, África Occidental e Iowa, EEUU.

El corazón de EF5 es el **archivo de control**, que define todos los datos y parámetros de entrada. Esta guía se estructura en torno al llenado de los bloques necesarios dentro de este archivo de control.

Para una mayor comprensión de EF5, consulte la documentación: [EF5 User Manual](https://ef5docs.readthedocs.io/) (documentación aún en vía de desarrollo).

Si tiene alguna pregunta, póngase en contacto con Vanessa Robledo (vanessa-robledodelgado@uiowa.edu) o con [AHWA Laboratory](https://ahwa.lab.uiowa.edu) Equipo de desarrollo en [engr-ahwa-lab@uiowa.edu](mailto:engr-ahwa-lab@uiowa.edu).

---

## Prerrequisitos

Tiene dos opciones para ejecutar el código de esta guía:

#### 1. Google Colaboratory (recomendado)
La forma más fácil de empezar es con Google Colab, ya que todos los Notebooks están adaptados para ejecutarse en ese entorno.
- **Link:** [https://colab.research.google.com/](https://colab.research.google.com/)

#### 2. Entorno de Conda local
Si prefiere trabajar en su máquina local, le recomendamos crear un nuevo entorno Conda para evitar conflictos entre paquetes.

1.  **Cree el entorno a partir del archivo proporcionado:**
    El archivo `environment.yml` se encuentra en la carpeta `/prerequisites`.
    Ejecute el siguiente comando en su terminal:
    ```sh
    conda env create -f prerequisites/environment.yml
    ```
    *(Esto puede tomar varios minutos.)*

2.  **Activar el nuevo entorno:**
    ```sh
    conda activate ef5_env
    ```

---

## Estructura del proyecto

Todos los archivos necesarios están organizados en las siguientes carpetas:

-   **/Codes:** contiene todos los Notebooks de Jupyter para cada paso.
-   **/Prerequisites:** incluye el archivo de entorno de Conda.

---

## Instrucciones paso a paso

Los siguientes pasos le guiarán a través del proceso de generación de los archivos de entrada necesarios para el modelo a ejecutar en EF5, utilizando los bloques del archivo de control como guía.


### Paso 1: obtener los archivos básicos

Este primer paso crea los archivos de cuadrícula básicos que EF5 emplea para definir la malla computacional: el modelo digital de elevación (DEM), el modelo de direcciones de flujo (DDM) y el modelo de acumulación de flujo (FAM).

**Bloque de archivo de control de EF5:**
```
[Basic]
DEM=data/basic/dem.tif
DDM=data/basic/ddm.tif
FAM=data/basic/fam.tif
PROJ=geographic
ESRIDDM=true
SelfFAM=false
```
Los usuarios tienen varias opciones, como metodologías basadas en QGis o ArcGIS. Sin embargo, en este tutorial se presentan dos opciones en función de los datos que disponga:

* **Opción A: usar información de HydroSHEDS**
    Si desea crear un modelo basado en el repositorio de HydroSHEDS, con datos ya listos para usar, utilice el siguiente notebook:
    - **Notebook:** [`/Codes/1_GettingBasicFiles.ipynb`](/Codes/1_GettingBasicFiles.ipynb)

* **Opción B: usar un DEM específico**
    Si dispone de su propio DEM, utilice este Notebook para obtener las cuadrículas DDM y FAM.
    - **Notebook:** [`/Codes/1b_CreateBasicGrids.ipynb`](/Codes/1b_CreateBasicGrids.ipynb)


**Resultado:** después de ejecutar el notebook adecuado, asegúrese de tener sus tres archivos de salida (`dem.tif`, `ddm.tif`, `fam.tif`) y que estén guardados en la carpeta `/data/basic/`.

---

### Paso 2: preparar los datos de forzamiento de la precipitación

A continuación, descargará y dará formato a los datos de precipitación. Esta guía utiliza IMERG v07 por su oportuna resolución espacial y temporal.

**Bloque de archivo de control de EF5:**
```
[PrecipForcing IMERG]
TYPE=TIF
UNIT=mm/h
FREQ=30u
LOC=/data/precip/
NAME=imerg.YYYYMMDDHHUU.tif
```

Siga las instrucciones del notebook que aparece a continuación para procesar los archivos de precipitación.
- **Notebook:** [`/Codes/2_Get_precipitation_files.ipynb`](/Codes/2_Get_precipitation_files.ipynb)

**Result:** Sitúe todos los archivos de precipitación `.tif` en la carpeta `/data/precip/`.

---

### Step 3: preparar datos de evapotranspiración potencial (PET)

El último conjunto de datos forzantes necesario es la evapotranspiración potencial.

**Bloque de archivo de control de EF5:**
```
[PETForcing CLIMO]
TYPE=TIF
UNIT=mm/d
FREQ=1m
LOC=/data/pet/
NAME=PET.MM.tif
```

Puede obtener datos de PET de varias fuentes:

* **Repositorio global:** la Universidad de Oklahoma aloja conjuntos de datos globales de PET compatibles con EF5. Puede encontrarlos en el repositorio [EF5-Global-Parameters](https://github.com/HyDROSLab/EF5-Global-Parameters/tree/main/FAO_PET) o, si su área de interés es EEUU, [US-Parameters](https://github.com/HyDROSLab/EF5-US-Parameters)
* **Datos regionales (África Occidental):** si está construyendo un modelo de África Occidental o Ghana de 1 km, hay disponibles archivos PET ya recortados. [aquí](https://github.com/RobledoVD/WAEF5-dockerized/tree/main/data/pet).

**Resultado:** Sitúe los archivos de PET `.tif` (e.g., `PET.01.tif`, `PET.02.tif`, etc.) en la carpeta `/data/pet/`.

---

### Paso 4: preparación de cuadrículas para un modelo distribuido

Para crear un modelo distribuido utilizando tareas de EF5 como `CLIP_GAUGE` y `BASIN_AVG`, todas las cuadrículas de entrada deben estar perfectamente alineadas. Esto significa que deben compartir exactamente el mismo dominio espacial (extensión), resolución de píxeles y sistema de coordenadas. 

#### Insumos necesarios

* **Para el balance hídrico (CREST)**

1. Rásters de texturas del suelo: porcentaje de arena, arcilla, y limo.
> Puede acceder a estos archivos en [soilgrids.org](https://soilgrids.org/) 

2. Ráster de profundidad a la roca madre, en metros

* **Tránsito hidráulico (onda cinemática o kinematic wave)**

1. DEM y sus cuadrículas derivadas: Modelo digital del terreno (dem), Flujo de acumulación (facc), y direcciones de flujo (fdir).

2. Cuadrículas hidroclimatológicas: Temperatura media (Celsius) Precipitación media anual (mm).

3. Coeficiente de rugosidad de Manning.

#### Preparación de cuadrículas del dominio

El modelo digital de elevación **(DEM)** sirve como plantilla principal para todas las cuadrículas generadas para el dominio. Todas las demás cuadrículas deben ajustarse a este.

> **:warning: Nota crítica sobre las cuadrículas básicas**
>
> No es correcto remuestrear o reproyectar directamente las cuadrículas existentes de acumulación de flujo (`facc`) o dirección de flujo (`fdir`). Si su DEM necesita modificaciones (por ejemplo, reproyección o remuestreo), debe utilizar el **DEM final y correcto** para regenerar las cuadrículas `facc` y `fdir` desde cero (paso 1 de este tutorial).

Las cuadrículas hidroclimatológicas no necesitan tener la misma cuadrícula del dominio, pero sí deben tener el mismo sistema de coordenadas que el DEM. Si no es así, utilice una herramienta basada en SIG para reproyectar las cuadrículas y que coincidan con el mismo sistema de coordenadas que el del DEM. Un ejemplo de este tipo de herramienta es el programa gdalwarp de GDAL.

Para ayudar con esto, se incluye un script C-Shell en esta carpeta "resample_and_subset.csh". A continuación se ilustra su uso:

```sh
./resample_and_subset.csh <input_file.tif> <output_file.tif> <template.tif>
```

**input_file.tif:** El archivo de cuadrícula que se necesita procesar (por ejemplo, climatological_temperature.tif).
**output_file.tif:** El nombre deseado para el archivo procesado y alineado (por ejemplo, mean_temp.tif).
**template.tif:** La cuadrícula maestra que se utilizará como plantilla para la resolución de píxeles y las coordenadas del dominio (debería ser su dem.tif final).

Ejemplo:

```sh
./resample_and_subset.csh climatological_temperature.tif mean_temp.tif dem.tif
```

Utilice el script C-Shell para todas las entradas enumeradas anteriormente.

---

### Paso 5: definición automática de todas las ubicaciones de los puntos (estaciones) envolventes del dominio con `CLIP_GAUGE`

Hacer que EF5 modele cada píxel dentro de un dominio puede ser un proceso tedioso si se hace manualmente. En lugar de crear cientos de bloques `[Gauge]` a mano, puede utilizar un modo de ejecución específico de EF5 para identificar automáticamente todos los sumideros de las cuencas envolventes de su dominio y generar la configuración necesaria.

Este proceso utiliza el estilo `CLIP_GAUGE`. A continuación se ofrece una guía paso a paso:

1. Configure el archivo de control CLIP_GAUGE
Deberá ejecutar EF5 con un archivo de control temporal específico para esta tarea.

- En esta carpeta se proporciona un archivo de ejemplo:  [`/Resources/ef5_clip_gauge_sample.txt`]. Utilícelo como punto de partida.
- En el bloque [Task], asegúrese de que el estilo de ejecución esté configurado en CLIP_GAUGE.

**Bloque de archivo de control de EF5:**
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

> **❗Importante:** los demás bloques de este archivo de ejemplo (por ejemplo, las rutas a los datos de forzamiento) deben seguir conteniendo entradas válidas. EF5 intentará comprobar la existencia de estos archivos aunque no se utilicen en la operación CLIP_GAUGE.

2. Ejecute EF5 y compruebe los resultados:

Ejecute EF5 utilizando el archivo de control configurado en el paso anterior. Cuando el proceso haya finalizado, se generarán dos nuevos archivos:

- `maskgrid.tif`: se trata de un archivo ráster que puede abrir en QGIS u otro software SIG. Utilícelo para verificar visualmente que las cuencas hidrográficas dentro de su dominio se han identificado correctamente.
- `basin_new.txt`: este archivo de texto contiene los bloques [Gauge] y [Basin] generados automáticamente para su modelo.

El contenido de basin_new.txt tendrá un formato similar al siguiente:

**Archivo de texto generado:**
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

3. Actualice su archivo de control:

Ahora, transferirá esta configuración al archivo de control principal que utilizará para ejecutar simulaciones reales.

- Abra `basin_new.txt` y copie todo su contenido.
- Abra su archivo de control de simulación final.
- Pegue el texto copiado en el archivo. La ubicación correcta es entre el último bloque de forzamiento (por ejemplo, [PETForcing CLIMO]) y el primer bloque de parámetros (por ejemplo, [CrestParamSet]).
- Este proceso define una única cuenca completa denominada [Basin 0] que incluye todos las estaciones generadas. Si cualquier otro bloque de su archivo de control necesita hacer referencia a una cuenca, asegúrese de que estén configurados para utilizar la cuenca 0.

---

### Paso 6: calcular variables integradas en la cuenca con `BASIN_AVG`

Para generar determinados parámetros, como los del modelo de propagación de la onda cinemática, primero es necesario calcular los valores medios de cada variable, para el area aferente a cada pixel del dominio, a partir de los datos de la cuadrícula (por ejemplo, la precipitación media). El estilo `BASIN_AVG` de EF5 está diseñado para este fin.

Siga estos pasos para realizar la operación de agregación sobre el dominio:

1. Cree una nueva carpeta para esta operación (por ejemplo, basin_integration/).

2. Copie los archivos de cuadrícula que deben integrarse (`mean_temp.tif` y `mean_precip.tif`) en esta nueva carpeta `basin_integration/`.

3. Modifique el archivo de control de simulación principal para realizar esta tarea específica.

> ❗**Importante:** En el bloque `[Task]`, establezca `STYLE` en `BASIN_AVG`.
> Indique en la variable `OUTPUT` el directorio que acaba de crear.
> Asegúrese de que los demás ajustes coincidan con la configuración de su proyecto.

El nuevo bloque de tareas de su archivo de control que utiliza la función de operación de agregación de EF5 debería tener este aspecto:

**Bloque de archivo de control de EF5:**
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

> **Note:** Asegúrese de que los nombres de BASIN, PET, PARAM_SET, etc., sean coherentes con el resto del archivo de control.

4. Guarde el archivo de control modificado y ejecute EF5 utilizando este archivo de control. El modelo imprimirá las actualizaciones de estado en la pantalla. El proceso solo debería tardar unos segundos, pero puede ser más largo para dominios de muy alta resolución.

El proceso finalizará mostrando un mensaje de error en la pantalla. **Esto es normal para esta tarea específica.**

> **:warning: Error esperado**
> `ERROR:src/ExecutionController.cpp(94): Unimplemented simulation run style "7"`
> Puede ignorar este error sin problema. Indica que la operación BASIN_AVG ha finalizado.

5. Verifique la salida:  Navegue hasta la carpeta de salida que ha creado (por ejemplo, basin_integration/). Ahora encontrará nuevos archivos geotiff que contienen los resultados del cálculo, como `mean_temp_basin_avg.tif` y `mean_precip_basin_avg.tif`. Estos archivos contienen los valores agregados a nivel de cuenca necesarios para los pasos siguientes.

---

### Paso 7: cree los parámetros CREST

En este punto, ya debería tener los rásteres de textura del suelo recortados y reajustados para su dominio (consulte el paso 4 de esta guía). Colóquelos en una carpeta llamada `CREST_input`. Los archivos que deben encontrarse en esta carpeta son:

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

Utilice el siguiente notebook y siga las instrucciones:
- **Notebook:** [`/Codes/4_Crest_parameters_estimation.ipynb`](/Codes/4_Crest_parameters_estimation.ipynb)

Los resultados le servirán para llenar el siguiente bloque del archivo de control:

**Bloque de archivo de control de EF5:**
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

❗**Capa impermeable**

Notará que no hay un archivo `crest_IM.tif` en la carpeta de resultados. No es necesario calcular la capa impermeable porque hay  múltiples productos satelitales disponibles para ello, solo asegúrese de que las unidades estén en porcentaje. En este caso, utilizamos el [Conjunto de datos de superficies impermeables artificiales globales (GMIS) de Landsat](https://search.earthdata.nasa.gov/search/granules?p=C3550185860-ESDIS&pg[0][v]=f&pg[0][gsk]=-start_date&q=GMIS&tl=1278028800!3!!). Por favor lea la documentación de este producto y proceda según lo indicado. Incluimos un Notebook para ayudarle en este proceso:
- **Notebook:** [`/Codes/4b_IM_layer_processing.ipynb`](/Codes/4b_IM_layer_processing.ipynb)

---

### Paso 8: crear los parámetros de la onda cinemática (KW)

El último paso consiste en calcular los parámetros de tránsito necesarios para el modelo de onda cinemática. Para ello, debe preparar un conjunto de cuadrículas de entrada. Coloque los siguientes archivos en la carpeta: `/codes/KW_parameters/inputs_grids/`

Archivos necesarios:

`basin.area.tif
dem.tif
fam.tif
manning_n.tif
mean_precip.avg.tif
mean_temp.avg.tif
relief.ratio.tif`

>❗**Important:**
> Asegúrese de que los nombres de los archivos coincidan exactamente. EF5 puede generar archivos de cuadrícula promedio con nombres como mean_precip.tif.avg.tif. Si esto ocurre, cambie el nombre de los archivos para que coincidan con el formato de entrada esperado.

Abra y siga las instrucciones del siguiente Notebook Jupyter para calcular los parámetros KW:

- **Notebook:** [`/Codes/5_KM_parameters/5_Kinematic_Wave_Parameter_Estimation.ipynb`](/Codes/5_KM_parameters/5_Kinematic_Wave_Parameter_Estimation.ipynb)

Los resultados le ayudarán a llenar el siguiente bloque del archivo de control:

**Bloque de archivo de control de EF5:**
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
# Para citar este paquete como
Robledo, V., Henao, S., Vergara, H. (2025). A Complete Guide to Constructing and Implementing an EF5 Model from Scratch. (v1.0). https://doi.org/10.5281/zenodo.15644400

# Construire un modèle EF5 : guide pas à pas

Un guide complet pour construire et mettre en œuvre un modèle EF5 depuis le début, avec Python et des notebooks Jupyter.

> **Version française.** Ce dépôt est la traduction française de la branche `main` (EF5-builder-toolkit). Le code, les noms de variables, les chemins de fichiers et les noms de blocs du fichier de contrôle EF5 restent inchangés : seuls les textes explicatifs, les commentaires et les messages affichés ont été traduits.

## Vue d'ensemble

Ce dépôt fournit un guide pas à pas pour configurer un modèle EF5. Le code et les ressources qu'il contient sont conçus pour aider les utilisateurs à construire un modèle opérationnel sur leur propre bassin versant. La méthodologie présentée ici a déjà servi à créer des modèles EF5 à différentes résolutions pour des régions telles que le Ghana, l'Afrique de l'Ouest et l'Iowa (États-Unis).

Le cœur du modèle EF5 est le **fichier de contrôle** (control file), qui définit l'ensemble des données d'entrée et des paramètres. Ce guide est organisé autour du remplissage des blocs successifs de ce fichier de contrôle.

Pour une compréhension approfondie d'EF5, veuillez consulter la documentation officielle : [Manuel de l'utilisateur EF5](https://ef5docs.readthedocs.io/).

Pour toute question, contactez Vanessa Robledo (vanessa-robledodelgado@uiowa.edu) ou l'équipe de développement du [laboratoire AHWA](https://ahwa.lab.uiowa.edu) à l'adresse [engr-ahwa-lab@uiowa.edu](mailto:engr-ahwa-lab@uiowa.edu).

---

## Prérequis

Vous avez deux possibilités pour exécuter le code de ce guide :

#### 1. Google Colaboratory (recommandé)

La façon la plus simple de démarrer est d'utiliser Google Colab, car tous les notebooks sont adaptés à cet environnement.
- **Lien :** [https://colab.research.google.com/](https://colab.research.google.com/)

#### 2. Environnement Conda local

Si vous préférez travailler sur votre propre machine, nous recommandons de créer un nouvel environnement Conda afin d'éviter les conflits entre paquets.

1.  **Créez l'environnement à partir du fichier fourni :**
    Le fichier `environment.yml` se trouve dans le dossier `/prerequisites`. Exécutez la commande suivante dans votre terminal :
    ```sh
    conda env create -f prerequisites/environment.yml
    ```
    *(Cette opération peut prendre plusieurs minutes.)*

2.  **Activez le nouvel environnement :**
    ```sh
    conda activate ef5_env
    ```

---

## Structure du projet

Tous les fichiers nécessaires sont organisés dans les dossiers suivants :

-   **/Codes :** contient tous les notebooks Jupyter, un par étape.
-   **/Prerequisites :** contient le fichier d'environnement Conda.

---

## Instructions pas à pas

Les étapes suivantes vous guident dans la production des fichiers d'entrée requis par le modèle EF5, en prenant les blocs du fichier de contrôle comme fil conducteur.


### Étape 1 : obtenir les fichiers de base

Cette première étape crée les grilles de base qu'EF5 utilise pour définir le maillage de calcul : le modèle numérique de terrain (DEM), la grille de direction d'écoulement (DDM) et la grille d'accumulation d'écoulement (FAM).

**Bloc du fichier de contrôle EF5 :**
```
[Basic]
DEM=data/basic/dem.tif
DDM=data/basic/ddm.tif
FAM=data/basic/fam.tif
PROJ=geographic
ESRIDDM=true
SelfFAM=false
```
Plusieurs approches sont possibles, notamment à partir de QGIS ou d'ArcGIS. Dans ce tutoriel, vous avez deux options selon les données dont vous disposez :

* **Option A : utiliser les données HydroSHEDS**
    Si vous souhaitez construire un modèle à partir du jeu de données HydroSHEDS, directement disponible, utilisez le notebook suivant :
    - **Notebook :** [`/Codes/1_GettingBasicFiles.ipynb`](/Codes/1_GettingBasicFiles.ipynb)

* **Option B : utiliser votre propre MNT**
    Si vous disposez de votre propre MNT haute résolution, utilisez ce notebook pour en dériver les grilles DDM et FAM :
    - **Notebook :** [`/Codes/1b_CreateBasicGrids.ipynb`](/Codes/1b_CreateBasicGrids.ipynb)


**Résultat :** après avoir exécuté le notebook approprié, vérifiez que vos trois fichiers de sortie (`dem.tif`, `ddm.tif`, `fam.tif`) sont enregistrés dans le répertoire `/data/basic/`.

---

### Étape 2 : préparer les données de forçage en précipitation

Vous allez ensuite télécharger et mettre en forme les données de précipitation. Ce guide utilise IMERG v07 pour son excellente résolution spatiale et temporelle.

**Bloc du fichier de contrôle EF5 :**
```
[PrecipForcing IMERG]
TYPE=TIF
UNIT=mm/h
FREQ=30u
LOC=/data/precip/
NAME=imerg.YYYYMMDDHHUU.tif
```
Suivez les instructions du notebook ci-dessous pour traiter les fichiers de précipitation.
- **Notebook :** [`/Codes/2_Get_precipitation_files.ipynb`](/Codes/2_Get_precipitation_files.ipynb)

**Résultat :** placez tous les fichiers `.tif` de précipitation produits dans le répertoire `/data/precip/`.

---

### Étape 3 : préparer les données d'évapotranspiration potentielle (ETP)

Le dernier jeu de forçage requis est l'évapotranspiration potentielle.

**Bloc du fichier de contrôle EF5 :**
```
[PETForcing CLIMO]
TYPE=TIF
UNIT=mm/d
FREQ=1m
LOC=/data/pet/
NAME=PET.MM.tif
```

Vous pouvez obtenir des données d'ETP auprès de plusieurs sources :

* **Jeu de données mondial :** l'Université de l'Oklahoma héberge des jeux de données d'ETP mondiaux compatibles avec EF5. Vous les trouverez dans le dépôt [EF5-Global-Parameters](https://github.com/HyDROSLab/EF5-Global-Parameters/tree/main/FAO_PET) ou, pour les États-Unis, dans [US-Parameters](https://github.com/HyDROSLab/EF5-US-Parameters).
* **Jeu de données régional (Afrique de l'Ouest) :** si vous construisez le modèle Afrique de l'Ouest ou Ghana 1 km, des fichiers d'ETP déjà découpés sont disponibles [ici](https://github.com/RobledoVD/WAEF5-dockerized/tree/main/data/pet).

**Résultat :** placez les fichiers `.tif` d'ETP mensuelle (par exemple `PET.01.tif`, `PET.02.tif`, etc.) dans le répertoire `/data/pet/`.

---

### Étape 4 : préparer les grilles d'un modèle distribué

Pour créer un modèle distribué à l'aide des tâches EF5 telles que `CLIP_GAUGE` et `BASIN_AVG`, toutes les grilles d'entrée doivent être parfaitement alignées. Elles doivent donc partager exactement la même emprise spatiale, la même résolution de pixel et le même système de coordonnées.

#### Entrées nécessaires

* **Pour le bilan hydrique (CREST)**

1. Rasters de texture du sol : pourcentage de sable, pourcentage d'argile et pourcentage de limon.
> Vous pouvez accéder à ces fichiers sur [soilgrids.org](https://files.isric.org/soilgrids/former/2017-03-10/data/).

2. Raster de profondeur jusqu'au substratum rocheux, en mètres.

* **Pour le routage de l'écoulement (KinematicWave)**

1. Le MNT et ses dérivés hydrologiques : le fichier MNT (dem), le fichier d'accumulation d'écoulement (facc) et le fichier de direction d'écoulement (fdir).

2. Grilles hydroclimatologiques : température moyenne (degrés Celsius) et précipitation annuelle totale moyenne (mm).

3. Coefficient de rugosité de Manning.

#### Préparation des grilles du domaine

Le **modèle numérique de terrain (MNT)** sert de gabarit de référence pour l'ensemble du domaine de modélisation. Toutes les autres grilles doivent s'y conformer.

> **:warning: Point critique concernant les grilles de base**
>
> Il est incorrect de rééchantillonner ou de reprojeter directement des grilles d'accumulation (`facc`) ou de direction (`fdir`) existantes. Si votre MNT doit être modifié (reprojection ou rééchantillonnage, par exemple), vous devez utiliser le **MNT final et correct** pour régénérer les grilles `facc` et `fdir` depuis le début (étape 1 de ce tutoriel).

Les grilles hydroclimatologiques ne sont pas tenues d'avoir la même grille de domaine, mais elles doivent avoir le même système de coordonnées que le MNT et ses dérivés. Si ce n'est pas le cas, utilisez un outil SIG pour les reprojeter dans le même système de coordonnées que le MNT. Le programme gdalwarp de GDAL en est un exemple. Si toutes les grilles partagent le même système de coordonnées, il suffit de les rééchantillonner et de les découper pour qu'elles correspondent à la résolution de pixel et à l'emprise du MNT.

Pour vous y aider, un script C-Shell est fourni dans ce dossier : « resample_and_subset.csh ». Voici comment l'utiliser :

```sh
./resample_and_subset.csh <fichier_entree.tif> <fichier_sortie.tif> <gabarit.tif>
```

**fichier_entree.tif :** la grille à traiter (par exemple climatological_temperature.tif).
**fichier_sortie.tif :** le nom souhaité pour le fichier traité et aligné (par exemple mean_temp.tif).
**gabarit.tif :** la grille de référence servant de gabarit pour la résolution de pixel et les coordonnées du domaine (il doit s'agir de votre fichier dem.tif final).

Exemple :

```sh
./resample_and_subset.csh climatological_temperature.tif mean_temp.tif dem.tif
```

Utilisez ce script C-Shell pour toutes les entrées listées ci-dessus.

---

### Étape 5 : définir automatiquement tous les exutoires avec `CLIP_GAUGE`

Forcer EF5 à modéliser chaque pixel d'un domaine peut devenir fastidieux si l'opération est faite à la main. Plutôt que de créer des centaines de blocs `[Gauge]` manuellement, vous pouvez utiliser un mode d'exécution EF5 spécifique qui identifie automatiquement tous les exutoires et génère la configuration correspondante.

Ce traitement utilise le style `CLIP_GAUGE`. Voici la marche à suivre :

1. Configurer le fichier de contrôle CLIP_GAUGE

Vous devrez exécuter EF5 avec un fichier de contrôle temporaire dédié à cette tâche.

- Un fichier d'exemple est fourni dans ce dossier : [`/Resources/ef5_clip_gauge_sample.txt`]. Utilisez-le comme point de départ.
- Dans le bloc [Task], vérifiez que le style d'exécution est bien réglé sur CLIP_GAUGE.

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

> **❗Important :** les autres blocs de ce fichier d'exemple (les chemins vers les données de forçage, par exemple) doivent tout de même contenir des valeurs valides. EF5 peut vérifier l'existence de ces fichiers même s'ils ne sont pas utilisés par l'opération CLIP_GAUGE.

2. Exécuter EF5 et vérifier les sorties

Exécutez EF5 avec le fichier de contrôle configuré à l'étape précédente. À la fin du traitement, deux nouveaux fichiers sont produits :

- `maskgrid.tif` : un fichier raster que vous pouvez ouvrir dans QGIS ou un autre logiciel SIG. Il vous permet de vérifier visuellement que les bassins versants de votre domaine ont été correctement identifiés.
- `basin_new.txt` : un fichier texte qui contient les blocs [Gauge] et [Basin] générés automatiquement pour votre modèle.

Le contenu de basin_new.txt ressemblera à ceci :

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
3. Mettre à jour votre fichier de contrôle

Vous allez maintenant reporter cette configuration dans le fichier de contrôle principal, celui qui servira aux simulations réelles.

- Ouvrez `basin_new.txt` et copiez-en tout le contenu.
- Ouvrez votre fichier de contrôle de simulation final.
- Collez le texte copié dans ce fichier. Le bon emplacement se situe entre le dernier bloc de forçage (par exemple [PETForcing CLIMO]) et le premier bloc de paramètres (par exemple [CrestParamSet]).
- Cette opération définit un bassin unique et complet, nommé [Basin 0], qui regroupe toutes les stations générées. Si d'autres blocs de votre fichier de contrôle doivent référencer un bassin, veillez à ce qu'ils utilisent la valeur 0.

---

### Étape 6 : calculer les variables intégrées par bassin avec `BASIN_AVG`

Pour produire certains paramètres, comme ceux du modèle de routage par onde cinématique, vous devez d'abord calculer des valeurs moyennes par bassin à partir de vos données maillées (la précipitation moyenne, par exemple). La tâche `BASIN_AVG` d'EF5 est prévue à cet effet.

Suivez ces étapes pour réaliser l'intégration par bassin :

1. Créez un nouveau dossier pour cette opération (par exemple basin_integration/).

2. Copiez dans ce nouveau dossier `basin_integration/` les grilles à intégrer (`mean_temp.tif` et `mean_precip.tif`).

3. Modifiez votre fichier de contrôle principal pour réaliser cette tâche spécifique.

> ❗**Important :** dans le bloc `[Task]`, réglez `STYLE` sur `BASIN_AVG`.
> Faites pointer la variable `OUTPUT` vers le répertoire que vous venez de créer.
> Vérifiez que les autres réglages correspondent bien à la configuration de votre projet.

Le nouveau bloc de tâche de votre fichier de contrôle, utilisant la fonction de moyenne par bassin d'EF5, doit ressembler à ceci :

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

> **Remarque :** vérifiez que les noms utilisés pour BASIN, PET, PARAM_SET, etc. sont cohérents avec le reste de votre fichier de contrôle.

4. Enregistrez le fichier de contrôle modifié et lancez EF5 avec celui-ci. Le modèle affiche l'avancement à l'écran. Le traitement ne devrait prendre que quelques secondes, un peu plus pour des domaines à très haute résolution.

Le traitement se termine par l'affichage d'un message d'erreur. **C'est normal pour cette tâche particulière.**

> **:warning: Erreur attendue**
> `ERROR:src/ExecutionController.cpp(94): Unimplemented simulation run style "7"`
> Vous pouvez ignorer cette erreur sans risque. Elle indique que l'opération BASIN_AVG s'est terminée correctement.

5. Vérifiez les sorties : ouvrez le dossier de sortie que vous avez créé (par exemple basin_integration/). Vous y trouverez de nouveaux fichiers GeoTIFF contenant les résultats du calcul, tels que `mean_temp_basin_avg.tif` et `mean_precip_basin_avg.tif`. Ces fichiers contiennent les valeurs intégrées par bassin nécessaires aux étapes suivantes.

---

### Étape 7 : créer les paramètres CREST

À ce stade, vous devez disposer des rasters de texture du sol découpés et rééchantillonnés sur votre domaine (voir l'étape 4 de ce guide). Placez-les dans un dossier `CREST_input`. Les fichiers attendus dans ce dossier sont :

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

Utilisez le notebook suivant et suivez ses instructions :
- **Notebook :** [`/Codes/4_Crest_parameters_estimation.ipynb`](/Codes/4_Crest_parameters_estimation.ipynb)

Les sorties vous permettront de remplir le bloc suivant du fichier de contrôle :

**Bloc du fichier de contrôle EF5 :**
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

❗**Couche des surfaces imperméables**

Vous aurez remarqué qu'aucun fichier `crest_IM.tif` ne figure dans le dossier de sortie. Il n'est pas nécessaire de calculer la couche des surfaces imperméables, car plusieurs produits satellitaires existent pour cela : assurez-vous simplement que les unités sont exprimées en pourcentage. Nous utilisons ici le jeu de données [Global Man-made Impervious Surface (GMIS) Dataset From Landsat](https://search.earthdata.nasa.gov/search/granules?p=C3550185860-ESDIS&pg[0][v]=f&pg[0][gsk]=-start_date&q=GMIS&tl=1278028800!3!!). Lisez la documentation de ce produit et traitez-le en conséquence. Un notebook est fourni pour vous aider dans cette opération :
- **Notebook :** [`/Codes/4b_IM_layer_processing.ipynb`](/Codes/4b_IM_layer_processing.ipynb)

---

### Étape 8 : créer les paramètres de l'onde cinématique (KW)

La dernière étape consiste à calculer les paramètres de routage requis par le modèle d'onde cinématique. Pour cela, vous devez préparer un jeu de grilles d'entrée. Placez les fichiers suivants dans le dossier : `/codes/KW_parameters/inputs_grids/`

Fichiers requis :

`basin.area.tif
dem.tif
fam.tif
manning_n.tif
mean_precip.avg.tif
mean_temp.avg.tif
relief.ratio.tif`

>❗**Important :**
> Vérifiez que les noms de fichiers correspondent exactement. EF5 peut produire des grilles moyennées portant des noms du type mean_precip.tif.avg.tif. Si c'est le cas, renommez les fichiers pour qu'ils respectent le format d'entrée attendu.

Ouvrez le notebook Jupyter suivant et suivez ses instructions pour calculer les paramètres KW :

- **Notebook :** [`/Codes/5_KM_parameters/5_Kinematic_Wave_Parameter_Estimation.ipynb`](/Codes/5_KM_parameters/5_Kinematic_Wave_Parameter_Estimation.ipynb)

Les sorties vous permettront de remplir le bloc suivant du fichier de contrôle :

**Bloc du fichier de contrôle EF5 :**
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
# Citer ce paquet
Robledo, V., Henao, S., Vergara, H. (2025). A Complete Guide to Constructing and Implementing an EF5 Model from Scratch. (v1.0). https://doi.org/10.5281/zenodo.15644400

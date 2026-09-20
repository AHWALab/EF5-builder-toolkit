#!/bin/csh

#Fichier à traiter :
set inputFile=$1
#Nom du fichier de sortie après traitement : 
set outputFile=$2
#Fichier de référence servant de gabarit pour les coordonnées des coins du domaine et la résolution de pixel
set SampleFile=$3

#Obtenir les coordonnées des coins du domaine à partir du fichier de référence
set xmin=`gdalinfo "$SampleFile" | grep "Lower Left" | cut -d "," -f1 | cut -d "(" -f2 | tr -d "[ ]"`
set ymin=`gdalinfo "$SampleFile" | grep "Lower Left" | cut -d "," -f2 | cut -d ")" -f1 | tr -d "[ ]"`
set xmax=`gdalinfo "$SampleFile" | grep "Upper Right" | cut -d "," -f1 | cut -d "(" -f2 | tr -d "[ ]"`
set ymax=`gdalinfo "$SampleFile" | grep "Upper Right" | cut -d "," -f2 | cut -d ")" -f1 | tr -d "[ ]"`

#Obtenir la taille de pixel à partir du fichier de référence
set pixelsz=`gdalinfo "$SampleFile" | grep "Pixel Size" | cut -d "," -f1 | cut -d "(" -f2 | tr -d "[ ]"`

#Utiliser gdalwarp pour traiter le fichier d'entrée avec la résolution et les coordonnées de coins spécifiées
gdalwarp -co COMPRESS=Deflate -ot Float32 -dstnodata -9999 -te "$xmin" "$ymin" "$xmax" "$ymax" -tr "$pixelsz" -"$pixelsz" "$inputFile" "$outputFile"

#!/bin/csh

#File that needs to be processed:
set inputFile=$1
#Name of the output file after processing: 
set outputFile=$2
#Sample file to use as template for domain corner coordinates and pixel resolution
set SampleFile=$3

#Obtain coordinates of domain corners from sample file
set xmin=`gdalinfo "$SampleFile" | grep "Lower Left" | cut -d "," -f1 | cut -d "(" -f2 | tr -d "[ ]"`
set ymin=`gdalinfo "$SampleFile" | grep "Lower Left" | cut -d "," -f2 | cut -d ")" -f1 | tr -d "[ ]"`
set xmax=`gdalinfo "$SampleFile" | grep "Upper Right" | cut -d "," -f1 | cut -d "(" -f2 | tr -d "[ ]"`
set ymax=`gdalinfo "$SampleFile" | grep "Upper Right" | cut -d "," -f2 | cut -d ")" -f1 | tr -d "[ ]"`

#Obtain pixel size from sample file
set pixelsz=`gdalinfo "$SampleFile" | grep "Pixel Size" | cut -d "," -f1 | cut -d "(" -f2 | tr -d "[ ]"`

#Use gdalwarp to process input file with specfied resolution and domain corner coordinates
gdalwarp -co COMPRESS=Deflate -ot Float32 -dstnodata -9999 -te "$xmin" "$ymin" "$xmax" "$ymax" -tr "$pixelsz" -"$pixelsz" "$inputFile" "$outputFile"

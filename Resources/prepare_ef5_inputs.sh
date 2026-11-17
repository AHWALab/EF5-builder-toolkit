#!/usr/bin/env bash
# Convert a TIFF for EF5 while preserving its CRS, extent, and pixel size.
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "Usage: $0 input.tif [output.tif]" >&2
    exit 1
fi

input=$1
output=${2:-${input%.*}_ef5.tif}

if ! command -v gdal_translate >/dev/null 2>&1; then
    echo "Error: gdal_translate must be installed and available on PATH." >&2
    exit 1
fi
if [[ ! -f "$input" ]]; then
    echo "Error: input file does not exist: $input" >&2
    exit 1
fi
if [[ -e "$output" ]]; then
    echo "Error: output already exists: $output" >&2
    exit 1
fi

gdal_translate -of GTiff -ot Float32 -a_nodata -9999 \
    -co COMPRESS=DEFLATE \
    -co TILED=NO \
    -co BIGTIFF=IF_SAFER \
    -co INTERLEAVE=PIXEL \
    "$input" "$output"

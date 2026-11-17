@echo off
setlocal DisableDelayedExpansion
rem Convert a TIFF for EF5 while preserving its CRS, extent, and pixel size.

if "%~1"=="" goto usage
if not "%~3"=="" goto usage

set "input=%~1"
set "output=%~2"
if not defined output set "output=%~dpn1_ef5.tif"

where gdal_translate >nul 2>&1
if errorlevel 1 (
    echo Error: gdal_translate must be installed and available on PATH. >&2
    exit /b 1
)
if not exist "%input%" (
    echo Error: input file does not exist: "%input%" >&2
    exit /b 1
)
if exist "%output%" (
    echo Error: output already exists: "%output%" >&2
    exit /b 1
)

gdal_translate -of GTiff -ot Float32 -a_nodata -9999 ^
    -co COMPRESS=DEFLATE ^
    -co TILED=NO ^
    -co BIGTIFF=IF_SAFER ^
    -co INTERLEAVE=PIXEL ^
    "%input%" "%output%"
exit /b %errorlevel%

:usage
echo Usage: %~nx0 input.tif [output.tif] >&2
exit /b 1

"""Exercise the notebook's real raster-processing cells with small fixtures."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import numpy as np
import rasterio
from rasterio.transform import from_origin


def test_impervious_notebook_native_grid():
    root = Path(__file__).resolve().parents[1]
    notebook = json.loads((root/'Example/Example_notebooks/7b_Impervious_layer_processing.ipynb').read_text())
    codes = [''.join(c['source']) for c in notebook['cells'] if c['cell_type']=='code']
    imports = codes[0]
    clean = next(s for s in codes if s.startswith('normalized_dir ='))
    mosaic = next(s for s in codes if s.startswith('with ExitStack() as stack:'))
    fill = next(s for s in codes if s.startswith('valid = np.isfinite(image)'))
    write = next(s for s in codes if s.startswith('for path in (output_file, fill_mask_file):'))
    
    with TemporaryDirectory(prefix='ef5-im-notebook-') as temp:
        base=Path(temp)
        download_dir=base/'downloads'
        download_dir.mkdir()
        output_dir=base/'outputs'
        output_dir.mkdir()
        diagnostics_dir=base/'crest_diagnostics'
        diagnostics_dir.mkdir()
        dem_file=base/'dem.tif'
        dem_profile=dict(driver='GTiff', width=6,height=4,count=1,dtype='float32',
                         crs='EPSG:4326',transform=from_origin(0,.016,.004,.004),nodata=-9999,
                         tiled=False,compress='none')
        with rasterio.open(dem_file,'w',**dem_profile) as dst:
            data=np.ones((4,6),dtype='float32')
            data[-1,-1]=-9999
            dst.write(data,1)
        zip_files=[]
        for col in (0,1):
            tile=base/f'tile_{col}.tif'
            data=np.full((8,6),10+col*40,dtype='uint8')
            if col==0:
                data[0,0]=200
                data[2,2]=255
            with rasterio.open(tile,'w',driver='GTiff',width=6,height=8,count=1,dtype='uint8',
                               crs='EPSG:4326',transform=from_origin(col*.012,.016,.002,.002),
                               nodata=255,tiled=False,compress='none') as dst:
                dst.write(data,1)
            archive=download_dir/f'tile_{col}.zip'
            with ZipFile(archive,'w') as zipped:
                zipped.write(tile,arcname=tile.name)
            zip_files.append(archive)
        original={path:hashlib.sha256(path.read_bytes()).hexdigest() for path in zip_files}
        ns={}
        exec(compile(imports,'notebook_imports','exec'),ns)
        ns.update(dem_file=dem_file,dem_bounds=(0,0,.024,.016),download_dir=download_dir,
                  output_dir=output_dir,output_file=output_dir/'crest_IM.tif',
                  fill_mask_file=diagnostics_dir/'crest_IM_filled_mask.tif',
                  overwrite=False,fill_missing=True,zip_files=zip_files)
        for label,source in [('clean',clean),('mosaic',mosaic),('fill',fill),('write',write)]:
            exec(compile(source,f'notebook_{label}','exec'),ns)
        with rasterio.open(ns['output_file']) as src:
            values=src.read(1)
            assert src.shape==(8,12),src.shape
            assert src.res==(.002,.002),src.res
            assert src.shape!=(4,6)  # The impervious layer was not resized to the DEM.
            assert values[0,0]==0  # Non-HBASE is zero, not 200%.
            assert values[2,2]==10  # One missing cell filled from the original nearby soil-free percentage data.
            assert values[2,8]==50  # Source values preserved without averaging to the DEM.
            assert (values[-2:,-2:]==-9999).all()
            assert not src.profile.get('tiled',False) and src.compression == rasterio.enums.Compression.deflate
            assert src.dtypes==('float32',) and src.nodata==-9999
        with rasterio.open(ns['fill_mask_file']) as src:
            values=src.read(1)
            assert values[2,2]==1
            assert (values==1).sum()==1
            assert (values[-2:,-2:]==-9999).all()
        assert all(hashlib.sha256(path.read_bytes()).hexdigest()==content for path,content in original.items())
        # The optional no-fill path must retain missing cells rather than fabricate data.
        exec(compile(mosaic,'notebook_mosaic_no_fill','exec'),ns)
        ns['fill_missing']=False
        exec(compile(fill,'notebook_no_fill','exec'),ns)
        assert ns['image'][2,2]==-9999
        assert ns['remaining'].sum()==1
        # No valid source data must raise instead of selecting a fictitious donor.
        ns['image']=np.full((8,12),-9999,dtype='float32')
        ns['domain']=np.ones((8,12),dtype=bool)
        ns['fill_missing']=True
        try:
            exec(compile(fill,'notebook_no_donor','exec'),ns)
        except ValueError as exc:
            assert 'No valid impervious' in str(exc)
        else:
            raise AssertionError('Missing donor validation did not run')
    print('PASSED: native resolution, no averaging, source codes, filling, DEM mask, EF5 storage, source preservation, optional no-fill, and no-donor handling.',flush=True)

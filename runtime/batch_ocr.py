"""One Windows OCR process, in-memory small regions, no capture or input APIs."""
import hashlib,json,subprocess,time
from pathlib import Path
from runtime.minimal_state import REGIONS

ROOT=Path(__file__).resolve().parents[1]


def read_regions(frame,output,*,names=('round','energy'),regions=None,cache=None):
    output=Path(output);output.mkdir(exist_ok=False)
    source=Path(frame['image']);data=source.read_bytes()
    if len(data)>16*1024*1024 or hashlib.sha256(data).hexdigest()!=frame['sha256']:
        raise ValueError('batch_ocr_capture_changed_or_too_large')
    selected=dict(regions)if regions is not None else {name:REGIONS[name]for name in names}
    if not 1<=len(selected)<=32:raise ValueError('bounded_nonempty_ocr_regions_required')
    rows=[]
    for name,rect in selected.items():
        if (not isinstance(name,str)or not name or len(rect)!=4 or any(type(n)is not int for n in rect)
                or not 0<=rect[0]<rect[0]+rect[2]<=1450 or not 0<=rect[1]<rect[1]+rect[3]<=869):
            raise ValueError('invalid_ocr_region')
        rows.append({'name':name,'bounds':list(rect),'scale':3})
    profile={'schema_version':'strategy-ocr-layout/1','width':1450,'height':869,'regions':rows}
    profile_path=output/'profile.json';profile_path.write_text(json.dumps(profile),encoding='utf-8')
    result_path=output/'ocr-batch.json'
    command=['powershell.exe','-NoProfile','-NonInteractive','-File',str(ROOT/'runtime/ocr_regions.ps1'),
             '-Image',str(source.resolve()),'-Profile',str(profile_path.resolve()),'-Output',str(result_path.resolve())]
    if cache is not None:command+=['-Cache',str(Path(cache).resolve())]
    started=time.perf_counter()
    process=subprocess.run(command,capture_output=True,encoding='utf-8',errors='replace',timeout=20,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    wall=time.perf_counter()-started
    if process.returncode:raise RuntimeError('batch_ocr_failed:'+process.stderr[-1500:])
    result=json.loads(result_path.read_text(encoding='utf-8'))
    if (result.get('schema_version')!='strategy-region-ocr/1'or result.get('image_sha256')!=frame['sha256']
            or result.get('profile_sha256')!=hashlib.sha256(profile_path.read_bytes()).hexdigest()
            or hashlib.sha256(source.read_bytes()).hexdigest()!=frame['sha256']
            or (result.get('width'),result.get('height'))!=(1450,869)):
        raise ValueError('batch_ocr_result_source_or_profile_mismatch')
    rows=result['regions']
    if len(rows)!=len(selected)or len({row['name']for row in rows})!=len(rows)or {row['name']for row in rows}!=set(selected):
        raise ValueError('batch_ocr_result_region_mismatch')
    bundles={}
    for row in rows:
        if tuple(row['bounds'])!=tuple(selected[row['name']])or row['scale']!=3:
            raise ValueError('batch_ocr_result_transform_mismatch')
        digest=row['pixel_sha256']
        if not isinstance(digest,str)or len(digest)!=64 or any(c not in '0123456789abcdef'for c in digest):
            raise ValueError('batch_ocr_pixel_hash_invalid')
        bundles[row['name']]={'roi':{'kind':'in_memory_bgra8','source_sha256':frame['sha256'],
             'source_rect':row['bounds'],'pixel_sha256':digest,'scale':3},
             'ocr':{'status':'recognized','frame_sha256':frame['sha256'],'pixel_sha256':digest,
                    'text':row['text'],'cache_hit':row['cache_hit']}}
    result['process_wall_seconds']=wall
    return bundles,result

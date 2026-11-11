"""Build the optional native additions pack, preserving every asset byte."""
import argparse,hashlib,json,tomllib,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ADDON=ROOT/'src/addons/no_mans_sky_base_builder'
def main(argv=None):
 parser=argparse.ArgumentParser()
 parser.add_argument('--release-tag')
 args=parser.parse_args(argv)
 version=tomllib.loads((ADDON/'blender_manifest.toml').read_text())['version']
 tag=args.release_tag or 'v'+version
 source=ADDON/'resources/hd_additions'
 manifest=ADDON/'resources/hd_additions.json'
 # Compatibility is explicitly reviewed, never inferred from a new pack ID.
 previous=json.loads(manifest.read_text()).get('compatible_previous',[]) if manifest.exists() else []
 files={}
 target=ROOT/'dist/bbe-hd-additions-1.zip'
 with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
  for p in sorted(source.rglob('*')):
   if not p.is_file() or p.suffix not in ('.blend','.png','.webp','.npz','.zlib'):continue
   name=p.relative_to(source).as_posix()
   # Characters have their own optional download and manifest.
   if name.split('/',1)[0] in ('pilot_references','character_references'):continue
   files[name]={'bytes':p.stat().st_size,'sha256':hashlib.file_digest(p.open('rb'),'sha256').hexdigest()}
   z.write(p,name)
 content=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
 digest=hashlib.file_digest(target.open('rb'),'sha256').hexdigest()
 spec=dict(id='hd-additions-1-'+content[:12],content_sha256=content,files=files,
           download_bytes=target.stat().st_size,archives={digest:{'prefix':''}},
           url='https://github.com/slipperystickers/nms-base-builder/releases/download/'+tag+'/'+target.name)
 if previous:spec['compatible_previous']=[p for p in previous if p['id']!=spec['id']]
 (ADDON/'resources/hd_additions.json').write_text(json.dumps(spec,indent=2)+'\n')
 print(target,len(files),target.stat().st_size,digest,flush=True)
if __name__=='__main__':main()

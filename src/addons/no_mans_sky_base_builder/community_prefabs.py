"""Public prefab catalogue. Network and file work stays outside Blender's UI thread."""
import base64
import hashlib
import json
from pathlib import Path
from queue import Empty, Queue
import re
import tempfile
import threading
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import bpy
import bpy.utils.previews
from bpy.app.handlers import persistent
from bpy.props import StringProperty, IntProperty
from . import interchange

HOST = 'https://furiousfurby.com'
BASE = HOST + '/prefabs'
PAGE = 8
MAX_FILE = 16 * 1024 * 1024
MAX_IMAGE = 4 * 1024 * 1024
_queue = Queue()
_generation = 0
_busy = False
_open = False
_status = ''
_sources = []
_source = 'main'
_items = []
_offset = _total = 0
_icons = None
_preview_dir = None
_local_names = {}

def request(url, limit, data=None):
    req = Request(url, data=data, headers={'User-Agent':'BBE-Prefab-Catalogue/1', 'Content-Type':'application/json'})
    try:
        with urlopen(req, timeout=20) as response:
            blob = response.read(limit + 1)
    except HTTPError as err:
        try:
            reason = json.loads(err.read(4096))['error']
        except (ValueError, KeyError):
            reason = f'HTTP {err.code}'
        raise ValueError(reason) from err
    if len(blob) > limit:
        raise ValueError('Catalogue response exceeds the size limit.')
    return blob

def checked_path(value, prefix):
    if not isinstance(value, str) or not re.fullmatch(re.escape(prefix) + r'[a-zA-Z0-9/-]+', value):
        raise ValueError('Unexpected catalogue file link.')
    return HOST + value

def search(slug, query, offset, emit):
    sources = json.loads(request(BASE + '/api/sources', 65536))['sources']
    params = urlencode(dict(source=slug, q=query, offset=offset, limit=PAGE))
    result = json.loads(request(BASE + '/api/items?' + params, 512 * 1024))
    items = result['items'][:PAGE]
    emit('page', (sources, slug, items, result['total'], offset))
    for e in items:
        if not e.get('thumbnail'):
            continue
        try:
            data = request(checked_path(e['thumbnail'], '/prefabs/media/'), MAX_IMAGE)
            if hashlib.sha256(data).hexdigest() == e['thumbnail'].rsplit('/', 1)[-1]:
                emit('thumb', (e['id'], data))
        except (OSError, ValueError):
            continue

def library_name(entry):
    # Include the full digest in the filename to preserve distinct revisions.
    title = re.sub(r'[^\w -]+', ' ', entry['title']).strip()[:48] or 'Prefab'
    return 'BBE ' + title + ' ' + entry['sha256'][:16]

def download(entry, directory, emit):
    raw = request(checked_path(entry['download'], '/prefabs/download/'), MAX_FILE)
    if hashlib.sha256(raw).hexdigest() != entry['sha256']:
        raise ValueError('The prefab changed. Refresh the catalogue and download again.')
    build = interchange.BuildFile.from_bytes(raw, Path(entry['filename']).suffix)
    doc = build.document
    if not isinstance(doc, dict) or not ('Objects' in doc or 'Prefab' in doc):
        doc = dict(doc) if isinstance(doc, dict) else {}
        doc.pop('objects', None)
        doc['Objects'] = build.objects
    data = json.dumps(doc,ensure_ascii=True,allow_nan=False).encode('utf-8')
    directory.mkdir(parents=True, exist_ok=True)
    name = library_name(entry)
    path = directory/(name+'.nmsprefab')
    if path.exists() and path.read_bytes()!=data:
        raise ValueError('A locally edited copy already exists. Rename it before downloading again.')
    if not path.exists():
        with tempfile.NamedTemporaryFile(dir=directory,delete=False) as out:
            tmp = Path(out.name)
            out.write(data)
        try:
            # On Windows rename refuses to overwrite a newly created destination.
            try: tmp.rename(path)
            except FileExistsError:
                if path.read_bytes()!=data: raise
        finally:
            tmp.unlink(missing_ok=True)
    emit('saved', (entry['id'], name))

def upload(slug, title, author, desc, file, image, emit):
    if not file.is_file() or file.stat().st_size>MAX_FILE:
        raise ValueError('Choose a prefab file up to 16 MiB.')
    raw=file.read_bytes()
    interchange.BuildFile.from_bytes(raw,file.suffix)
    thumbnail=None
    if image:
        if not image.is_file() or image.stat().st_size>MAX_IMAGE:
            raise ValueError('Choose a JPG, PNG or WebP thumbnail up to 4 MiB.')
        thumbnail=base64.b64encode(image.read_bytes()).decode('ascii')
    data=dict(source=slug,title=title,author=author,description=desc,filename=file.name,
              data=base64.b64encode(raw).decode('ascii'),thumbnail=thumbnail)
    result=json.loads(request(BASE+'/api/upload',65536,json.dumps(data).encode('utf-8')))
    emit('message', 'Prefab published. Refresh to see it.' if result['status']=='published' else 'Prefab submitted for review.')

def _start(context, work, *args):
    global _busy, _generation, _status, _open
    _open=True
    if _busy: return {'CANCELLED'}
    if not bpy.app.online_access:
        _status='Enable Blender Online Access to use the online catalogue.'
        return {'CANCELLED'}
    _generation+=1
    generation=_generation
    _busy=True
    _status={search:'Searching…',download:'Downloading prefab…',upload:'Submitting prefab…'}[work]
    def emit(event, data):
        if generation==_generation: _queue.put((generation,event,data))
    def run():
        try: work(*args,emit)
        except Exception as e: emit('message',str(e)[:230])
        finally: emit('done',None)
    threading.Thread(target=run,daemon=True,name='BBE prefab catalogue').start()
    if not bpy.app.timers.is_registered(_poll):bpy.app.timers.register(_poll,first_interval=.08)
    return {'FINISHED'}

def _poll():
    global _sources,_source,_items,_total,_offset,_status,_busy,_icons,_preview_dir
    changed=False
    while True:
        try: gen,event,data=_queue.get_nowait()
        except Empty: break
        if gen!=_generation:continue
        changed=True
        if event=='page':
            clear_previews()
            _sources,_source,_items,_total,_offset=data
            _status=f'{_offset+1}–{_offset+len(_items)} of {_total} prefabs' if _items else 'No matching prefabs.'
        elif event=='thumb' and not bpy.app.background:
            if _icons is None:
                _icons=bpy.utils.previews.new()
                _preview_dir=tempfile.TemporaryDirectory(prefix='bbe-prefabs-')
            key,blob=data
            if key not in _icons:
                file=Path(_preview_dir.name)/(hashlib.sha256(blob).hexdigest()+'.img')
                file.write_bytes(blob)
                try:_icons.load(key,str(file),'IMAGE')
                except RuntimeError:pass
        elif event=='saved':
            from . import refresh_prefab_catalogue
            key,name=data;_local_names[key]=name;refresh_prefab_catalogue()
            _status='Downloaded to your local prefab library.'
        elif event=='message':_status=data
        elif event=='done':_busy=False
    if changed:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type=='VIEW_3D':area.tag_redraw()
    return .12 if _busy else None

def clear_previews():
    global _icons,_preview_dir
    if _icons is not None:bpy.utils.previews.remove(_icons);_icons=None
    if _preview_dir is not None:_preview_dir.cleanup();_preview_dir=None

@persistent
def reset(*_):
    global _generation,_busy,_open,_status,_sources,_source,_items,_offset,_total
    _generation+=1;_busy=_open=False;_status='';_sources=[];_source='main';_items=[];_offset=_total=0
    _local_names.clear();clear_previews()
    if bpy.app.timers.is_registered(_poll):bpy.app.timers.unregister(_poll)

class BBE_OT_catalogue_search(bpy.types.Operator):
    bl_idname='bbe.prefab_catalogue_search'
    bl_label='Search Prefabs'
    bl_description='Browse public community prefabs by title, creator, description or tag'
    source: StringProperty(options={'SKIP_SAVE'})
    offset: IntProperty(default=0,min=0,options={'SKIP_SAVE'})
    def execute(self,context):
        return _start(context,search,self.source or _source,context.window_manager.bbe_catalogue_query,self.offset)

class BBE_OT_catalogue_download(bpy.types.Operator):
    bl_idname='bbe.prefab_catalogue_download'
    bl_label='Download Prefab'
    bl_description='Save this build in your local prefab library'
    entry: StringProperty(options={'SKIP_SAVE'})
    def execute(self,context):
        from .preset import Preset
        item=next((e for e in _items if e['id']==self.entry),None)
        return _start(context,download,dict(item),Path(Preset.PRESET_PATH)/'Community') if item else {'CANCELLED'}

class BBE_OT_catalogue_upload(bpy.types.Operator):
    bl_idname='bbe.prefab_catalogue_upload'
    bl_label='Upload Prefab'
    bl_description='Share a prefab file and optional thumbnail in the public catalogue'
    filepath:StringProperty(name='Prefab file',subtype='FILE_PATH',options={'SKIP_SAVE'})
    thumbnail:StringProperty(name='Thumbnail (optional)',subtype='FILE_PATH',options={'SKIP_SAVE'})
    title:StringProperty(name='Title',maxlen=140)
    creator:StringProperty(name='Creator',maxlen=100)
    description_text:StringProperty(name='Description',maxlen=1500)
    def invoke(self,context,event):
        return context.window_manager.invoke_props_dialog(self,width=410)
    def draw(self,context):
        for prop in ('filepath','title','creator','description_text','thumbnail'):self.layout.prop(self,prop)
        self.layout.label(text='The creator name and build file will be public.')
    def execute(self,context):
        if not self.title.strip() or not self.creator.strip() or not self.filepath:
            self.report({'ERROR'},'Choose a file and enter its title and creator.');return {'CANCELLED'}
        return _start(context,upload,_source,self.title,self.creator,self.description_text,
                      Path(bpy.path.abspath(self.filepath)),Path(bpy.path.abspath(self.thumbnail)) if self.thumbnail else None)

def draw(layout,context):
    box=layout.box();row=box.row(align=True);row.label(text='Online Prefab Catalogue')
    row.operator('wm.url_open',text='',icon='URL').url=BASE+'/'
    row=box.row(align=True);row.prop(context.window_manager,'bbe_catalogue_query',text='',icon='VIEWZOOM')
    row.enabled=not _busy;row.operator('bbe.prefab_catalogue_search',text='Search' if _open else 'Browse')
    box.operator('bbe.prefab_catalogue_upload',text='Upload Prefab',icon='EXPORT')
    if len(_sources)>1:
        row=box.row(align=True)
        for s in _sources:row.operator('bbe.prefab_catalogue_search',text=s['name'],depress=s['id']==_source).source=s['id']
    if _status:box.label(text=_status)
    for entry in _items:
        row=box.row(align=True)
        if _icons and entry['id'] in _icons:row.template_icon(icon_value=_icons[entry['id']].icon_id,scale=2.4)
        label=row.column(align=True);label.label(text=entry['title']);label.label(text=f"{entry['author']} · {entry['count']} parts")
        name=_local_names.get(entry['id'])
        if name:
            op=row.operator('object.list_build_operator',text='Place',icon='ADD');op.part_id=name;op.prefab_only=True;op.tooltip='Place the downloaded prefab'
        else:
            row.operator('bbe.prefab_catalogue_download',text='',icon='IMPORT').entry=entry['id']
    if _offset or _offset+len(_items)<_total:
        row=box.row(align=True);row.enabled=not _busy
        if _offset:row.operator('bbe.prefab_catalogue_search',text='Previous').offset=max(0,_offset-PAGE)
        if _offset+len(_items)<_total:row.operator('bbe.prefab_catalogue_search',text='Next').offset=_offset+PAGE

classes=(BBE_OT_catalogue_search,BBE_OT_catalogue_download,BBE_OT_catalogue_upload)
def register():
    bpy.types.WindowManager.bbe_catalogue_query=StringProperty(name='Search prefabs',maxlen=180,options={'SKIP_SAVE'})
    bpy.app.handlers.load_pre.append(reset)
def unregister():
    reset()
    if reset in bpy.app.handlers.load_pre:bpy.app.handlers.load_pre.remove(reset)
    del bpy.types.WindowManager.bbe_catalogue_query

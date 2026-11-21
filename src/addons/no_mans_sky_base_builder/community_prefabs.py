"""Public prefab catalogue. Network and file work stays outside Blender's UI thread."""
from . import i18n
import base64
import hashlib
import json
from pathlib import Path
from queue import Empty, Queue
import re
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
_expanded = False
_pages = {}
_source_cache = (0, [])
_cache_dir = None
_enum_refs = {}
_draw_regions = {}
_thumb_hashes = {}

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

def server_icon_key(source):
    url = source.get('iconUrl') or ''
    if re.fullmatch(r'https://cdn\.discordapp\.com/icons/\d{17,20}/(?:a_)?[a-f0-9]{32}\.png\?size=64', url):
        return 'guild-' + hashlib.sha256(url.encode()).hexdigest()
    return ''


def invite_link(source):
    url = source.get('inviteUrl') or ''
    return url if re.fullmatch(r'https://discord\.gg/[a-zA-Z0-9_-]{1,100}', url) else ''


def load_server_icon(source, emit):
    key = server_icon_key(source)
    path = _cache_dir / (key + '.img') if _cache_dir else None
    blob = path.read_bytes() if path and path.is_file() else None
    if not blob or not blob.startswith(b'\x89PNG\r\n\x1a\n'):
        blob = request(source['iconUrl'], 512 * 1024)
        if not blob.startswith(b'\x89PNG\r\n\x1a\n'):
            return
        if path:
            path.write_bytes(blob)
    emit('thumb', (key, blob))


def search(slug, query, offset, emit):
    global _source_cache
    now=time.monotonic()
    if now-_source_cache[0]>600 or not _source_cache[1]:
        _source_cache=(now,json.loads(request(BASE+'/api/sources',65536))['sources'])
    sources = _source_cache[1]
    if sources and not any(source['id']==slug for source in sources):
        slug,offset=sources[0]['id'],0
    key=(slug,query,offset)
    cached=_pages.get(key)
    if cached and now-cached[0]<90:
        result=cached[1]
    else:
        params=urlencode(dict(source=slug,q=query,offset=offset,limit=PAGE))
        result=json.loads(request(BASE+'/api/items?'+params,512*1024))
        if len(_pages)>32:_pages.clear()
        _pages[key]=(now,result)
    items=result['items'][:PAGE]
    emit('page',(_source_cache[1],slug,items,result['total'],offset))
    def thumbnail(entry):
        link=entry.get('thumbnail')
        if not link:return
        url=checked_path(link,'/prefabs/media/')
        digest=link.rsplit('/',1)[-1]
        if not re.fullmatch('[a-f0-9]{64}',digest):return
        path=_cache_dir/(digest+'.img') if _cache_dir else None
        blob=path.read_bytes() if path and path.exists() else None
        if blob is None or hashlib.sha256(blob).hexdigest()!=digest:
            blob=request(url,MAX_IMAGE)
            if hashlib.sha256(blob).hexdigest()!=digest:return
            if path:
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(blob)
        emit('thumb',(entry['id'],blob))
    with ThreadPoolExecutor(max_workers=4,thread_name_prefix='Prefab images') as pool:
        avatars = {server_icon_key(source): source for source in sources if server_icon_key(source)}
        futures = [pool.submit(load_server_icon, source, emit) for source in avatars.values()]
        futures.extend(pool.submit(thumbnail, entry) for entry in items)
        for future in as_completed(futures):
            try:future.result()
            except (OSError,ValueError):pass


def trim_cache():
    if not _cache_dir or not _cache_dir.exists():return
    try:
        total=0
        for path in sorted(_cache_dir.glob('*.img'),key=lambda p:p.stat().st_mtime,reverse=True):
            total+=path.stat().st_size
            if total>128*1024*1024:path.unlink(missing_ok=True)
    except OSError:pass

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
    _pages.clear()
    emit('message', 'Prefab published. Refresh to see it.' if result['status']=='published' else 'Prefab submitted for review.')

def _start(context, work, *args):
    global _busy, _generation, _status, _open, _cache_dir
    _open=True
    _cache_dir=Path(bpy.utils.user_resource('DATAFILES',path='community-prefab-thumbnails',create=True))
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
        finally:
            trim_cache()
            emit('done',None)
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
            _sources,_source,_items,_total,_offset=data
            sync_rows()
            _status=f'{_offset+1}–{_offset+len(_items)} of {_total} prefabs' if _items else 'No matching prefabs.'
        elif event=='thumb' and not bpy.app.background:
            if _icons is None:
                _icons=bpy.utils.previews.new()
                _preview_dir=tempfile.TemporaryDirectory(prefix='bbe-prefabs-')
            key,blob=data
            digest=hashlib.sha256(blob).hexdigest()
            if key in _icons and _thumb_hashes.get(key)!=digest:del _icons[key]
            if len(_icons)>32:
                current={e['id'] for e in _items} | {server_icon_key(source) for source in _sources}
                for old in list(_icons.keys()):
                    if old not in current:del _icons[old];_thumb_hashes.pop(old,None)
            _thumb_hashes[key]=digest
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
        for key,region in list(_draw_regions.items()):
            try:region.tag_redraw();region.tag_refresh_ui()
            except ReferenceError:_draw_regions.pop(key,None)
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type=='VIEW_3D':area.tag_redraw()
    return .12 if _busy else None

def clear_previews():
    global _icons,_preview_dir
    if _icons is not None:bpy.utils.previews.remove(_icons);_icons=None
    if _preview_dir is not None:_preview_dir.cleanup();_preview_dir=None
    _thumb_hashes.clear()

@persistent
def reset(*_):
    global _generation,_busy,_open,_status,_sources,_source,_items,_offset,_total,_expanded
    _expanded=False;_draw_regions.clear()
    _generation+=1;_busy=_open=False;_status='';_sources=[];_source='main';_items=[];_offset=_total=0
    _local_names.clear();clear_previews();_enum_refs.clear()
    if bpy.app.timers.is_registered(_poll):bpy.app.timers.unregister(_poll)

class BBE_OT_catalogue_search(bpy.types.Operator):
    bl_idname='bbe.prefab_catalogue_search'
    bl_translation_context = "BBEExtendedInterface"
    bl_label='Search Prefabs'
    bl_description='Browse public community prefabs by title, creator, description or tag'
    source: StringProperty(options={'SKIP_SAVE'})
    offset: IntProperty(default=0,min=0,options={'SKIP_SAVE'})
    def execute(self,context):
        return _start(context,search,self.source or _source,context.window_manager.bbe_catalogue_query,self.offset)

class BBE_OT_catalogue_download(bpy.types.Operator):
    bl_idname='bbe.prefab_catalogue_download'
    bl_translation_context = "BBEExtendedInterface"
    bl_label='Download Prefab'
    bl_description='Save this build in your local prefab library'
    entry: StringProperty(options={'SKIP_SAVE'})
    def execute(self,context):
        from .preset import Preset
        item=next((e for e in _items if e['id']==self.entry),None)
        return _start(context,download,dict(item),Path(Preset.PRESET_PATH)/'Community') if item else {'CANCELLED'}

class BBE_OT_catalogue_upload(bpy.types.Operator):
    bl_idname='bbe.prefab_catalogue_upload'
    bl_translation_context = "BBEExtendedInterface"
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
        for prop in ('filepath','title','creator','description_text','thumbnail'):i18n.localized_layout(self.layout).prop(self,prop)
        i18n.localized_layout(self.layout).label(text='The creator name and build file will be public.')
    def execute(self,context):
        if not self.title.strip() or not self.creator.strip() or not self.filepath:
            self.report({'ERROR'},'Choose a file and enter its title and creator.');return {'CANCELLED'}
        return _start(context,upload,_source,self.title,self.creator,self.description_text,
                      Path(bpy.path.abspath(self.filepath)),Path(bpy.path.abspath(self.thumbnail)) if self.thumbnail else None)

def thumb_items(self,context):
    key=self.name
    entry=next((e for e in _items if e['id']==key),{})
    icon=_icons[key].icon_id if _icons and key in _icons else 0
    value=[('IMAGE',entry.get('title','Loading thumbnail'), 'Click to enlarge; close to return to the same catalogue position',icon,0)]
    # Blender keeps pointers to enum strings. Retain every active tuple.
    cache=(key,icon,entry.get('title',''))
    if cache not in _enum_refs:_enum_refs[cache]=value
    return _enum_refs[cache]

class BBE_PG_catalogue_card(bpy.types.PropertyGroup):
    image:bpy.props.EnumProperty(items=thumb_items)

class BBE_PG_catalogue_pair(bpy.types.PropertyGroup):
    first:bpy.props.IntProperty()

class BBE_UL_catalogue(bpy.types.UIList):
    def draw_item(self,context,layout,data,item,icon,active_data,active_propname,index):
        row=layout.row()
        cards=getattr(context.window_manager,'bbe_catalogue_cards')
        for number in range(item.first,min(item.first+2,len(_items))):
            entry=_items[number];cell=row.column(align=True)
            cell.template_icon_view(cards[number],'image',show_labels=False,scale=6.0,scale_popup=18.0)
            cell.label(text=entry['title'])
            cell.label(text=entry['author'])
            cell.label(text=str(entry['count'])+' parts')
            cell.operator('bbe.prefab_catalogue_download',text='Download',icon='IMPORT').entry=entry['id']

class BBE_OT_catalogue_toggle(bpy.types.Operator):
    bl_idname='bbe.prefab_catalogue_toggle'
    bl_label='Online Community Prefabs'
    bl_description='Expand or collapse the community library; images load only when opened'
    def execute(self,context):
        global _expanded
        _expanded=not _expanded
        if _expanded and not _open:return _start(context,search,_source,context.window_manager.bbe_catalogue_query,0)
        return {'FINISHED'}

class BBE_PT_catalogue(bpy.types.Panel):
    bl_idname='BBE_PT_catalogue'
    bl_label='Online Community Prefabs'
    bl_space_type='VIEW_3D'
    bl_region_type='HEADER'
    bl_ui_units_x=24
    def draw(self,context):draw(self.layout,context,native=True)

def sync_rows():
    wm=bpy.context.window_manager
    cards=getattr(wm,'bbe_catalogue_cards');pairs=getattr(wm,'bbe_catalogue_pairs')
    cards.clear();pairs.clear()
    for entry in _items:cards.add().name=entry['id']
    for n in range(0,len(_items),2):pairs.add().first=n
    setattr(wm,'bbe_catalogue_active',0)

def draw(layout,context,native=False):
    row=layout.row(align=True);row.scale_y=1.35;row.operator_context='INVOKE_DEFAULT'
    row.operator('bbe.prefab_catalogue_open',text='Online Community Prefabs',icon='ASSET_MANAGER')


classes=(BBE_PG_catalogue_card,BBE_PG_catalogue_pair,BBE_UL_catalogue,BBE_OT_catalogue_toggle,BBE_PT_catalogue,BBE_OT_catalogue_search,BBE_OT_catalogue_download,BBE_OT_catalogue_upload)
def register():
    from . import catalogue_surface
    catalogue_surface.register()
    bpy.types.WindowManager.bbe_catalogue_cards=bpy.props.CollectionProperty(type=BBE_PG_catalogue_card)
    bpy.types.WindowManager.bbe_catalogue_pairs=bpy.props.CollectionProperty(type=BBE_PG_catalogue_pair)
    bpy.types.WindowManager.bbe_catalogue_active=IntProperty(options={'SKIP_SAVE'})
    bpy.types.WindowManager.bbe_catalogue_query=StringProperty(name='Search prefabs',maxlen=180,options={'SKIP_SAVE'})
    bpy.app.handlers.load_pre.append(reset)
def unregister():
    from . import catalogue_surface
    catalogue_surface.unregister()
    reset()
    if reset in bpy.app.handlers.load_pre:bpy.app.handlers.load_pre.remove(reset)
    for key in ('query','cards','pairs','active'):
        delattr(bpy.types.WindowManager,'bbe_catalogue_'+key)

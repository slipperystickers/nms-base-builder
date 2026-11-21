"""FuriousFurby authored viewport-only base radius guides. No game objects."""
import math
import bpy
from bpy.app.handlers import persistent
PREFIX = 'bbe'
TAG = PREFIX + '_boundary'
POINTER = PREFIX + '_boundary_collection'
MODE = PREFIX + '_boundary_mode'
RADIUS = 1000.0
_draw_handle = None
_batches = {}
KINDS = {'HomePlanetBase', 'PlayerSpaceBase', 'ExternalPlanetBase', 'ExternalSpaceBase'}


def geometry(sphere=False):
    vertices, edges = [], []
    def ring(points):
        first=len(vertices); vertices.extend(points)
        edges.extend((first+i, first+(i+1)%len(points)) for i in range(len(points)))
    angles=[2*math.pi*i/128 for i in range(128)]
    if not sphere:
        for axis in range(3):
            ring([tuple(0 if j==axis else RADIUS*(math.cos(a) if j==(axis+1)%3 else math.sin(a)) for j in range(3)) for a in angles])
    else:
        for i in range(12):
            phi=math.pi*i/12
            ring([(RADIUS*math.cos(a)*math.cos(phi),RADIUS*math.cos(a)*math.sin(phi),RADIUS*math.sin(a)) for a in angles])
        for i in range(-5,6):
            phi=math.pi*i/12
            ring([(RADIUS*math.cos(phi)*math.cos(a),RADIUS*math.cos(phi)*math.sin(a),RADIUS*math.sin(phi)) for a in angles])
    return vertices, edges



def draw_guides():
    import gpu
    from gpu_extras.batch import batch_for_shader
    context=bpy.context
    if not context.region_data or not context.space_data.overlay.show_overlays:return
    collection=getattr(context.scene,POINTER,None)
    if collection is None:return
    theme=context.preferences.themes[0].view_3d
    rgb=tuple(theme.space.text[:3])
    # A two-tone outline keeps the guide legible over both models and sky.
    luminance=sum(a*b for a,b in zip(rgb,(.2126,.7152,.0722)))
    outline=(0,0,0,.65) if luminance>.45 else (1,1,1,.65)
    shader=gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA');gpu.state.depth_test_set('NONE');gpu.state.depth_mask_set(False)
    try:
        for obj in collection.objects:
            if not obj.get(TAG) or not obj.visible_get(view_layer=context.view_layer):continue
            mode=obj.get(TAG)
            if mode not in _batches:
                vertices,edges=geometry(mode=='SPHERE')
                _batches[mode]=batch_for_shader(shader,'LINES',{'pos':vertices},indices=edges)
            with gpu.matrix.push_pop():
                gpu.matrix.multiply_matrix(obj.matrix_world)
                shader.bind();shader.uniform_float('viewportSize',(context.region.width,context.region.height))
                for color,width in [(outline,3.2),(rgb+(1,),1.6)]:
                    shader.uniform_float('color',color);shader.uniform_float('lineWidth',width);_batches[mode].draw(shader)
    finally:
        gpu.state.depth_mask_set(True);gpu.state.depth_test_set('NONE');gpu.state.blend_set('NONE')

def prepare_guides(collection):
    # Native wire edges are always black. Keep eye-controlled guide objects,
    # and render their lines with the theme-aware overlay instead.
    for obj in collection.objects:
        if obj.get(TAG) and obj.type=='MESH' and len(obj.data.vertices):
            obj.data.clear_geometry();obj.data.update()


def layer_nodes(node,collection):
    if node.collection==collection:yield node
    for child in node.children:yield from layer_nodes(child,collection)


def visibility(scene,collection,mode):
    # Only Outliner eyes control these guides. Monitor-disable flags would
    # prevent an eye click from showing them, so never use those as state.
    collection.hide_viewport=False
    for obj in collection.objects:obj.hide_viewport=False
    for layer in scene.view_layers:
        layer.update()
        for node in layer_nodes(layer.layer_collection,collection):
            node.exclude=False;node.hide_viewport=mode=='OFF'
        for obj in collection.objects:
            if obj.name in layer.objects:obj.hide_set(obj.get(TAG)!=('RINGS' if mode=='OFF' else mode),view_layer=layer)


def update(scene, context):
    collection=getattr(scene,POINTER,None)
    if collection:visibility(scene,collection,getattr(scene,MODE))


def clip_guides(scene):
    for window in bpy.context.window_manager.windows:
        if window.scene!=scene:continue
        for area in window.screen.areas:
            if area.type=='VIEW_3D':area.spaces.active.clip_end=max(area.spaces.active.clip_end,10000.0)


@persistent
def migrate(*_):
    for scene in bpy.data.scenes:
        current=getattr(scene,POINTER,None)
        for collection in bpy.data.collections:
            if not collection.get(TAG) or collection.get('boundary_eye_version',0)>=2:continue
            if not any(list(layer_nodes(layer.layer_collection,collection)) for layer in scene.view_layers):continue
            if collection==current:setattr(scene,MODE,'RINGS')
            visibility(scene,collection,'RINGS' if collection==current else 'OFF')
            collection['boundary_eye_version']=2
        if current:
            prepare_guides(current);clip_guides(scene)


def imported(scene, header, parent=None):
    if not isinstance(header,dict) or 'BaseType' not in header:return
    kind=header['BaseType']
    kind=kind.get('PersistentBaseTypes') if isinstance(kind,dict) else kind
    old=getattr(scene,POINTER,None)
    if old:visibility(scene,old,'OFF')
    setattr(scene,POINTER,None)
    if kind not in KINDS:return
    collection=bpy.data.collections.new(PREFIX.upper()+' Build Boundary · 1000u')
    (parent or scene.collection).children.link(collection)
    collection[TAG]=True;collection['radius_u']=RADIUS
    collection['guide_note']='Visual 1000u radius from imported base origin; not an unlock or build-limit override.'
    collection.hide_render=True
    for mode in ('RINGS','SPHERE'):
        mesh=bpy.data.meshes.new(PREFIX+' boundary '+mode)
        v,e=geometry(mode=='SPHERE');mesh.from_pydata(v,e,[]);mesh.update()
        obj=bpy.data.objects.new('1000u '+('Rings' if mode=='RINGS' else 'Wire Sphere'),mesh)
        collection.objects.link(obj);obj[TAG]=mode
        obj.hide_select=True;obj.hide_render=True;obj.display_type='WIRE'
        obj.color=(0.32,0.52,0.72,1);obj.show_in_front=False
        obj.lock_location=(True,)*3;obj.lock_rotation=(True,)*3;obj.lock_scale=(True,)*3
    prepare_guides(collection)
    setattr(scene,POINTER,collection)
    setattr(scene,MODE,'RINGS')
    update(scene,None)
    collection['boundary_eye_version']=2
    clip_guides(scene)


def clear(scene):
    old=getattr(scene,POINTER,None)
    if old:visibility(scene,old,'OFF')
    setattr(scene,POINTER,None)


def draw(layout,context):
    if not getattr(context.scene,POINTER,None):return
    row=layout.row(align=True)
    row.label(text='Build Boundary · 1000u',icon='SPHERE')
    row.prop(context.scene,MODE,text='')


def register():
    global _draw_handle
    _draw_handle=bpy.types.SpaceView3D.draw_handler_add(draw_guides,(),'WINDOW','POST_VIEW')
    setattr(bpy.types.Scene,POINTER,bpy.props.PointerProperty(type=bpy.types.Collection))
    setattr(bpy.types.Scene,MODE,bpy.props.EnumProperty(name='Build Boundary',
        description='Viewport-only 1000u radius from the loaded base origin. Hide/show its collection in the Outliner. Does not change game build limits',
        items=[('OFF','Off','Hide the boundary'),('RINGS','Rings','Three thin great circles; minimal obstruction'),('SPHERE','Wire Sphere','Latitude and longitude lines; no solid surface')],default='RINGS',update=update))
    if migrate not in bpy.app.handlers.load_post:bpy.app.handlers.load_post.append(migrate)
    if not bpy.app.timers.is_registered(migrate):bpy.app.timers.register(migrate,first_interval=.1)


def unregister():
    global _draw_handle
    if _draw_handle is not None:bpy.types.SpaceView3D.draw_handler_remove(_draw_handle,'WINDOW');_draw_handle=None
    _batches.clear()
    if bpy.app.timers.is_registered(migrate):bpy.app.timers.unregister(migrate)
    if migrate in bpy.app.handlers.load_post:bpy.app.handlers.load_post.remove(migrate)
    delattr(bpy.types.Scene,MODE);delattr(bpy.types.Scene,POINTER)

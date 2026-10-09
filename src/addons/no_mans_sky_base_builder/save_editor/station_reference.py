"""Station references: selective native geometry, local appearance profiles, cutaways.

PlayerSpaceStationBase has no resolved descriptor choices. Profiles are manually
matched and never represented as decoded game seeds. This module never writes saves.
"""
from ..furby_errors import report_error
from pathlib import Path
from functools import lru_cache
import json
import bpy
import bmesh
import numpy as np
from mathutils import Vector

ASSETS=Path(__file__).resolve().parents[1]/'resources/station'
TAG='nms_station_reference'
PARTS_TAG='nms_station_player_parts'

@lru_cache(None)
def catalog():
    return json.loads((ASSETS/'catalog.json').read_text(encoding='utf-8'))

def defaults():
    return {k:g['default'] for k,g in catalog()['groups'].items()}

def valid_choices(raw):
    choices=defaults()
    if not isinstance(raw,dict): return choices
    # Older profiles have a separate style choice for each repeated attachment.
    # Preserve the first active one when moving to a shared structural control.
    data=catalog(); legacy={**data.get('legacyDefaults',{}),**raw}; migrated=set()
    for key,mapping in data.get('legacyChoiceMap',{}).items():
        target=mapping['key']
        if key not in raw or target in raw or target in migrated: continue
        if not matches(mapping['requirements'],legacy): continue
        value=mapping['values'].get(raw[key])
        if value in [o[0] for o in data['groups'][target]['options']]:
            choices[target]=value; migrated.add(target)
    for k,value in raw.items():
        if k in choices:
            value=data.get('legacyChoiceMap',{}).get(k,{}).get('values',{}).get(value,value)
            if value in [o[0] for o in data['groups'][k]['options']]: choices[k]=value
    return choices

def matches(requirements,choices):
    return all(choices.get(k)==v for k,v in requirements.items())

def active_groups(choices):
    return [(k,g) for k,g in catalog()['groups'].items()
        if any(matches(condition,choices) for condition in g.get('conditions',[g['requirements']]))]

def profile_file():
    folder=bpy.utils.user_resource('CONFIG',path='nms_station_reference',create=True)
    return Path(folder)/'appearance_profiles.json'

def load_profiles():
    try:
        data=json.loads(profile_file().read_text(encoding='utf-8'))
        return data if isinstance(data,dict) else {}
    except (FileNotFoundError,ValueError,OSError): return {}

def remember_profile(key,choices,visibility=None):
    profiles=load_profiles()
    profiles[key]={'choices':valid_choices(choices),'source':'manual','version':2}
    if visibility is not None: profiles[key]['visibility']=visibility
    file=profile_file(); temp=file.with_suffix('.tmp')
    temp.write_text(json.dumps(profiles,indent=2),encoding='utf-8'); temp.replace(file)

def current_choices(manager):
    try: return valid_choices(json.loads(manager.station_choices_json))
    except (ValueError,TypeError): return defaults()

def remove_tree(collection,legacy=False):
    for child in list(collection.children): remove_tree(child,legacy)
    for obj in list(collection.objects):
        # Only tagged reference objects belong to this module.
        if obj.get(TAG) or (legacy and obj.get('station_reference_only') and 'ObjectID' not in obj):
            mesh=obj.data if obj.type=='MESH' else None
            bpy.data.objects.remove(obj,do_unlink=True)
            if mesh and mesh.users==0: bpy.data.meshes.remove(mesh)
    bpy.data.collections.remove(collection)
    from .station_cached_reference import cleanup_geometry
    cleanup_geometry()

def clear_reference(scene):
    legacy_roots=[]
    for c in list(scene.collection.children):
        if c.get(TAG): remove_tree(c)
        elif c.name.startswith(('INTERIOR -','ENTRANCE -','EXTERIOR -','01 Fixed station reference',
                '02 Representative procedural details','03 Authored no-build','04 Anchors and NPC',
                '05 Non-solid effect','06 Saved building positions','07 Exterior build ring')):
            if c.all_objects and all(o.get('station_reference_only') and 'ObjectID' not in o for o in c.all_objects):
                legacy_roots.append(c)
        elif c.get(PARTS_TAG) and not c.all_objects: bpy.data.collections.remove(c)
    if legacy_roots:
        # The original library has over 20,000 instances. Individual removals
        # repeatedly rebuild Blender's dependency graph and stall the UI.
        collections=set()
        def gather(c):
            collections.add(c)
            for child in c.children: gather(child)
        for c in legacy_roots: gather(c)
        objects={o for c in collections for o in c.objects}
        meshes={o.data for o in objects if o.type=='MESH'}
        bpy.data.batch_remove(ids=objects|collections)
        unused={m for m in meshes if m.users==0}
        if unused: bpy.data.batch_remove(ids=unused)

def collection(name,parent):
    c=bpy.data.collections.new(name); parent.children.link(c); c[TAG]=True
    return c

def join_geometry(objects,name):
    """Bake original world coordinates, without welding or simplifying surfaces."""
    vertices=[]; faces=[]; offset=0
    for obj,transform in objects:
        mesh=obj.data
        points=np.empty((len(mesh.vertices),3),dtype=np.float32)
        mesh.vertices.foreach_get('co',points.ravel())
        # Detached library objects have no evaluated dependency graph. Use the
        # authored matrix saved in the catalog, not an unevaluated matrix_world.
        matrix=np.asarray(transform,dtype=np.float64)
        points=(points@matrix[:3,:3].T+matrix[:3,3]).astype(np.float32)
        mesh.calc_loop_triangles()
        triangles=np.empty((len(mesh.loop_triangles),3),dtype=np.int32)
        mesh.loop_triangles.foreach_get('vertices',triangles.ravel())
        vertices.append(points); faces.append(triangles+offset); offset+=len(points)
    if not vertices: raise ValueError('No station geometry selected for '+name)
    points=np.concatenate(vertices); triangles=np.concatenate(faces).ravel()
    mesh=bpy.data.meshes.new(name)
    mesh.vertices.add(len(points)); mesh.vertices.foreach_set('co',points.ravel())
    mesh.loops.add(len(triangles)); mesh.loops.foreach_set('vertex_index',triangles)
    mesh.polygons.add(len(triangles)//3)
    mesh.polygons.foreach_set('loop_start',np.arange(0,len(triangles),3,dtype=np.int32))
    mesh.polygons.foreach_set('loop_total',np.full(len(triangles)//3,3,dtype=np.int32))
    mesh.update()
    return mesh

def make_object(mesh,name,destination):
    obj=bpy.data.objects.new(name,mesh); destination.objects.link(obj)
    obj[TAG]=True; obj['station_reference_only']=True
    obj['station_section']=name
    obj.hide_select=True; obj.color=(.39,.45,.53,1)
    return obj

# Axis names describe Blender's local frame, not geographical in-game compass.
CUTS=[('Roof - upper section', (0,0,18),(0,0,1)),
      ('North wall - +Y', (0,1005,0),(0,1,0)),
      ('South wall - entrance', (0,880,0),(0,-1,0)),
      ('East wall - +X', (60,0,0),(1,0,0)),
      ('West wall - -X', (-60,0,0),(-1,0,0))]

def split_inside(mesh,destination):
    """Partition surfaces at planes. Complementary halves retain the entire model."""
    remainder=bmesh.new(); remainder.from_mesh(mesh)
    original_area=sum(f.calc_area() for f in remainder.faces)
    area=0.; counts={}
    for name,point,normal in CUTS:
        section=remainder.copy()
        for bm,outer,inner in ((section,False,True),(remainder,True,False)):
            bmesh.ops.bisect_plane(bm,geom=list(bm.verts)+list(bm.edges)+list(bm.faces),
                dist=.000001,plane_co=point,plane_no=normal,clear_outer=outer,clear_inner=inner)
        # Faces lying exactly on a plane belong only to the remainder. A
        # bisect alone leaves them in both halves, duplicating surfaces.
        p=Vector(point); n=Vector(normal)
        coplanar=[f for f in section.faces if all(abs((v.co-p).dot(n))<=.00001 for v in f.verts)]
        bmesh.ops.delete(section,geom=coplanar,context='FACES')
        for bm in (section,remainder):
            bmesh.ops.delete(bm,geom=[v for v in bm.verts if not v.link_faces],context='VERTS')
        if section.faces:
            area+=sum(f.calc_area() for f in section.faces)
            part=bpy.data.meshes.new(name); section.to_mesh(part)
            obj=make_object(part,name,destination)
            counts[name]=len(part.polygons)
            if name.startswith('Roof'): obj.hide_set(True)
        section.free()
    area+=sum(f.calc_area() for f in remainder.faces)
    part=bpy.data.meshes.new('Floors and fixtures'); remainder.to_mesh(part); remainder.free()
    make_object(part,'Floors and fixtures',destination)
    counts['Floors and fixtures']=len(part.polygons)
    bpy.data.meshes.remove(mesh)
    return {'sourceSurfaceArea':original_area,'partitionSurfaceArea':area,'faceCounts':counts}

def assemble(context,choices,visibility=None):
    from .station_outliner import assemble as assemble_outliner
    return assemble_outliner(context,choices,visibility)


def organise_parts(context,parts):
    dest=bpy.data.collections.new('Station Player Parts'); dest[PARTS_TAG]=True
    context.scene.collection.children.link(dest)
    for obj in parts:
        dest.objects.link(obj)
        for c in list(obj.users_collection):
            if c!=dest: c.objects.unlink(obj)
    # Clean only the builder-created empty collections and the default empty one.
    for c in list(context.scene.collection.children):
        if c!=dest and (c.name=='Collection' or c.get(PARTS_TAG)) and not c.objects and not c.children:
            bpy.data.collections.remove(c)
    context.view_layer.update()
    context.view_layer.active_layer_collection=next(c for c in context.view_layer.layer_collection.children if c.collection==dest)
    return dest

def finish_transfer_import(context,base,previous_objects):
    """Use explicit base metadata, never the previous scene type or part IDs."""
    if not isinstance(base,dict): return False
    base_type=base.get('BaseType')
    if not isinstance(base_type,dict) or base_type.get('PersistentBaseTypes')!='PlayerSpaceStationBase':
        return False
    parts=[obj for obj in context.scene.objects if obj not in previous_objects]
    imported_station(context,base,parts,transfer=True)
    return True


def imported_station(context,base,parts,transfer=False):
    manager=context.scene.nms_save_data
    address=base.get('GalacticAddress')
    # A partial station record can still load the reference, but must not borrow
    # another unidentified station's saved appearance.
    if address is None or not str(address).strip():
        from uuid import uuid4
        key='unidentified:'+uuid4().hex
    else:
        key=str(address)
    profile=load_profiles().get(key,{})
    if not isinstance(profile,dict): profile={}
    choices=valid_choices(profile.get('choices',{}))
    manager.station_key=key
    manager.station_transfer_reference=transfer
    manager.station_choices_json=json.dumps(choices)
    manager.station_group=catalog()['familyGroup']
    manager.station_status='Saved station visibility' if profile else 'Choose a hull and big parts with the Outliner eyes'
    organise_parts(context,parts)
    assemble(context,choices,profile.get('visibility'))
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                space=area.spaces.active; space.clip_end=30000
                space.region_3d.view_location=(0,942,4)
                space.region_3d.view_distance=220
                space.region_3d.view_rotation=(Vector((0,942,4))-Vector((130,780,200))).to_track_quat('-Z','Y')
                space.region_3d.view_perspective='ORTHO'
            if area.type=='OUTLINER': area.spaces.active.show_restrict_column_hide=True

# Dynamic enum strings must remain alive for Blender RNA.
_enum_cache={}
FAMILIES=[('_Type_Tet','Tet',''),('_Type_Oct','Oct',''),('_Type_Disk','Disk',''),
          ('_Type_EX','EX',''),('_Type_Tri','Tri',''),('_Type_Simple','Simple','')]
CORRIDORS=[('_Tube_Tri','Triangular',''),('_Tube_Round','Round',''),('_Tube_Square','Square','')]
def main_get(self,kind):
    entries=FAMILIES if kind=='familyGroup' else CORRIDORS
    value=current_choices(self)[catalog()[kind]]
    return next(i for i,row in enumerate(entries) if row[0]==value)

def main_set(self,value,kind):
    entries=FAMILIES if kind=='familyGroup' else CORRIDORS
    choices=current_choices(self); choices[catalog()[kind]]=entries[value][0]
    self.station_choices_json=json.dumps(choices)
    self.station_group=catalog()[kind]
    self.station_option=entries[value][0]

def group_items(self,context):
    choices=current_choices(self)
    result=[(k,g['label'],'Change this reference geometry branch') for k,g in active_groups(choices)]
    _enum_cache['groups']=result
    return result

def option_items(self,context):
    group=catalog()['groups'].get(self.station_group)
    result=[(k,label,'Reference model option') for k,label in group['options']] if group else []
    _enum_cache['options']=result
    return result

def group_changed(self,context):
    choice=current_choices(self).get(self.station_group)
    if choice: self.station_option=choice

def option_changed(self,context):
    choices=current_choices(self)
    if self.station_group in choices and self.station_option:
        choices[self.station_group]=self.station_option
        self.station_choices_json=json.dumps(choices)

class ApplyStationReference(bpy.types.Operator):
    bl_idname='object.nms_apply_station_reference'
    bl_label='Refresh Reference Library'
    bl_description='Load all six hull families and large eye-toggle parts; keep player parts in place'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        manager=context.scene.nms_save_data
        if not manager.station_key:
            report_error(self,{'ERROR'},'Import a station first'); return {'CANCELLED'}
        try:
            choices=current_choices(manager)
            assemble(context,choices)
            from .station_outliner import capture
            remember_profile(manager.station_key,choices,capture(context))
            manager.station_status='Reference ready - use the Outliner eyes'
        except Exception as exc:
            report_error(self,{'ERROR'},str(exc)); return {'CANCELLED'}
        self.report({'INFO'},'Reference updated; player parts kept in place')
        return {'FINISHED'}

class RememberStationVisibility(bpy.types.Operator):
    bl_idname='object.nms_remember_station_visibility'
    bl_label='Remember Station Visibility'
    bl_description='Remember these Outliner eye settings when this station is imported again'
    def execute(self,context):
        from .station_outliner import capture
        manager=context.scene.nms_save_data
        if not manager.station_key:return {'CANCELLED'}
        remember_profile(manager.station_key,current_choices(manager),capture(context))
        self.report({'INFO'},'Station visibility remembered')
        return {'FINISHED'}

def draw(layout,context):
    manager=context.scene.nms_save_data
    if not manager.station_key or not any(c.get(TAG) for c in context.scene.collection.children): return
    box=layout.box(); box.label(text='Station Reference')
    box.label(text=manager.station_status,icon='INFO')
    box.label(text='Outside: use the eyes to choose one hull')
    box.label(text='Expand that hull for bodies and big parts')
    box.operator(RememberStationVisibility.bl_idname,icon='BOOKMARKS')
    box.operator(ApplyStationReference.bl_idname,icon='FILE_REFRESH')
    box.label(text='Outliner eyes: Outside, roof, and walls')

classes=(ApplyStationReference,RememberStationVisibility)

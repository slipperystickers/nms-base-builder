"""Supply-pipe display from the native textured segment; export data stays untouched."""
import bpy
import uuid

def sync_roll(obj, context):
    mod=obj.modifiers.get('Supply pipe segments')
    if not mod or not mod.node_group or not mod.node_group.interface.items_tree.get('Roll'):
        from . import cable_connections
        cable_connections.style(obj)
        mod=obj.modifiers.get('Supply pipe segments')
    if mod and mod.node_group:
        socket=mod.node_group.interface.items_tree.get('Roll')
        if socket:
            mod[socket.identifier]=obj.bbe_supply_roll
            obj.update_tag()


def install(obj,mesh,curve=False):
    if mesh is None:return
    name='Furby Supply Tube Segments '+('Curve' if curve else 'Rig Roll')+' '+mesh.name
    group=bpy.data.node_groups.get(name)
    if group is None:
        group=bpy.data.node_groups.new(name,'GeometryNodeTree')
        group.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry')
        group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry')
        length=group.interface.new_socket(name='Span',in_out='INPUT',socket_type='NodeSocketFloat');length.default_value=1;length.min_value=.001
        if not curve:
            group.interface.new_socket(name='Roll',in_out='INPUT',socket_type='NodeSocketFloat')
        n=group.nodes;l=group.links
        source=bpy.data.objects.new(name+' source',mesh)
        source['furby_supply_preview_source']=True
        source['furby_supply_source_id']=uuid.uuid4().hex
        info=n.new('GeometryNodeObjectInfo');info.inputs['Object'].default_value=source
        inp=n.new('NodeGroupInput');out=n.new('NodeGroupOutput')
        if curve:
            wire=inp.outputs['Geometry']
            measure=n.new('GeometryNodeCurveLength');l.new(wire,measure.inputs['Curve']);span=measure.outputs['Length']
        else:
            line=n.new('GeometryNodeCurvePrimitiveLine');line.inputs['End'].default_value=(0,0,1)
            wire=line.outputs['Curve'];span=inp.outputs['Span']
        count=n.new('ShaderNodeMath');count.operation='CEIL';l.new(span,count.inputs[0])
        minimum=n.new('ShaderNodeMath');minimum.operation='MAXIMUM';minimum.inputs[1].default_value=1;l.new(count.outputs[0],minimum.inputs[0])
        cap=n.new('ShaderNodeMath');cap.operation='MINIMUM';cap.inputs[1].default_value=2048;l.new(minimum.outputs[0],cap.inputs[0])
        count=cap.outputs[0]
        plus=n.new('ShaderNodeMath');plus.operation='ADD';plus.inputs[1].default_value=1;l.new(count,plus.inputs[0])
        points=n.new('GeometryNodeCurveToPoints');points.mode='COUNT';l.new(wire,points.inputs['Curve']);l.new(plus.outputs[0],points.inputs['Count'])
        index=n.new('GeometryNodeInputIndex');less=n.new('ShaderNodeMath');less.operation='LESS_THAN';l.new(index.outputs[0],less.inputs[0]);l.new(count,less.inputs[1])
        ratio=n.new('ShaderNodeMath');ratio.operation='DIVIDE'
        if curve:l.new(span,ratio.inputs[0])
        else:ratio.inputs[0].default_value=1
        l.new(count,ratio.inputs[1])
        scale=n.new('ShaderNodeCombineXYZ');scale.inputs['X'].default_value=1;scale.inputs['Y'].default_value=1;l.new(ratio.outputs[0],scale.inputs['Z'])
        inst=n.new('GeometryNodeInstanceOnPoints');l.new(points.outputs['Points'],inst.inputs['Points']);l.new(less.outputs[0],inst.inputs['Selection']);l.new(info.outputs['Geometry'],inst.inputs['Instance']);l.new(points.outputs['Rotation'],inst.inputs['Rotation']);l.new(scale.outputs[0],inst.inputs['Scale'])
        realize=n.new('GeometryNodeRealizeInstances');l.new(inst.outputs['Instances'],realize.inputs[0]);geometry=realize.outputs[0]
        if not curve:
            rotate=n.new('GeometryNodeTransform')
            angles=n.new('ShaderNodeCombineXYZ')
            l.new(inp.outputs['Roll'],angles.inputs['Z'])
            l.new(angles.outputs[0],rotate.inputs['Rotation'])
            l.new(geometry,rotate.inputs['Geometry'])
            geometry=rotate.outputs['Geometry']
        l.new(geometry,out.inputs['Geometry'])
    mod=obj.modifiers.get('Supply pipe segments') or obj.modifiers.new('Supply pipe segments','NODES')
    if mod.node_group!=group:
        mod.node_group=group
    if not curve:
        roll_key=group.interface.items_tree['Roll'].identifier
        if mod.get(roll_key)!=obj.bbe_supply_roll:
            mod[roll_key]=obj.bbe_supply_roll
        key=next(s.identifier for s in group.interface.items_tree if s.name=='Span' and s.in_out=='INPUT')
        from .cable_connections import endpoints
        start,end=endpoints(obj)
        if start is not None and end is not None:
            driver=mod.driver_add('["'+key+'"]').driver
            existing=driver.variables[0] if driver.variables else driver.variables.new()
            if existing.type!='LOC_DIFF' or existing.targets[0].id!=start or existing.targets[1].id!=end:
                existing.name='span';existing.type='LOC_DIFF'
                existing.targets[0].id=start;existing.targets[1].id=end
            driver.expression='max(span,0.001)'
        elif key not in mod:mod[key]=max(obj.matrix_world.col[2].xyz.length,.001)
    obj.color=(.35,.38,.42,1)


# A temporary, non-build curve uses the same textured segment modifier as a
# committed pipe. It has no ObjectID/record, cannot be selected or exported,
# and is removed before save/undo/load and when placement ends.
_live=[]

class LivePipe:
    def __init__(self,scene,mesh_loader):
        self.scene=scene;self.mesh_loader=mesh_loader;self.mesh=None;self.obj=None
        _live.append(self)
        for handlers in (bpy.app.handlers.save_pre,bpy.app.handlers.load_pre,bpy.app.handlers.undo_pre,bpy.app.handlers.redo_pre):
            if clear_live not in handlers:handlers.append(clear_live)

    @property
    def active(self):
        try:return self.obj is not None and self.obj.name in bpy.data.objects and not self.obj.hide_viewport
        except ReferenceError:return False

    def update(self,start,end,detailed=True):
        if not detailed or start is None or end is None or (end-start).length<.0001:
            self.clear();return False
        if self.mesh is None:self.mesh=self.mesh_loader()
        if self.mesh is None:return False
        if not self.active:
            self.clear()
            curve=bpy.data.curves.new('Supply Pipe Placement Preview','CURVE');curve.dimensions='3D'
            line=curve.splines.new('POLY');line.points.add(1)
            self.obj=bpy.data.objects.new('Supply Pipe Placement Preview',curve)
            self.obj['furby_supply_ghost']=True
            self.obj.hide_select=True;self.obj.hide_render=True
            self.scene.collection.objects.link(self.obj)
            install(self.obj,self.mesh,curve=True)
        self.obj.location=start
        points=self.obj.data.splines[0].points
        points[0].co=(0,0,0,1);points[1].co=(*(end-start),1)
        self.obj.data.update_tag()
        return True

    def clear(self):
        obj,self.obj=self.obj,None
        try:
            if obj is not None and bpy.data.objects.get(obj.name)==obj:
                curve=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
                if curve.users==0:bpy.data.curves.remove(curve)
        except ReferenceError:pass

    def close(self):
        self.clear()
        if self in _live:_live.remove(self)

@bpy.app.handlers.persistent
def clear_live(*_):
    for item in tuple(_live):item.clear();item.mesh=None

def unregister_live():
    for item in tuple(_live):item.close()
    for handlers in (bpy.app.handlers.save_pre,bpy.app.handlers.load_pre,bpy.app.handlers.undo_pre,bpy.app.handlers.redo_pre):
        if clear_live in handlers:handlers.remove(clear_live)

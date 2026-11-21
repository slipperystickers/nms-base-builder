"""First-party, non-destructive feature picking and rigid alignment for BBE builders."""
import math,time
from dataclasses import dataclass
import bpy,gpu
from mathutils import Vector,Matrix
from bpy.app.handlers import persistent
from bpy_extras import view3d_utils as view
from gpu_extras.batch import batch_for_shader
from . import builder_geometry_backend as backend,curve_surface,curve_widgets as w,i18n
PREFIX=backend.PREFIX
_sessions=[]
SOURCE=(.16,.6,1,1);TARGET=(1,.62,.15,1);PREVIEW=(.3,1,.65,.8)

@dataclass
class Feature:
    obj:object
    owner:object
    point:Vector
    direction:Vector
    lines:list
    matrix:Matrix
    owner_matrix:Matrix
    kind:str


def face_tangents(feature):
    """Use the longest outline sides to register the roll of two flat parts."""
    edges = [b - a for a, b in zip(feature.lines[::2], feature.lines[1::2])]
    longest = max((edge.length for edge in edges), default=0.0)
    return [edge.normalized() for edge in edges
            if edge.length > 1e-8 and edge.length >= longest * .9999]


def alignment_delta(source, target, rotate=True, reverse=False):
    if source.owner == target.owner:
        raise ValueError('Choose a target on another object')
    rotation = Matrix.Identity(4)
    if rotate and source.kind != 'POINT':
        axis = target.direction.normalized()
        # Mesh edge vertex numbering should not decide which way a part turns.
        opposite = source.kind == 'FACE' or (source.kind == 'EDGE' and source.direction.dot(axis)<0)
        goal = -axis if opposite != reverse else axis
        if source.direction.length < 1e-8 or goal.length < 1e-8:
            raise ValueError('This feature has no usable direction')
        rotation = source.direction.normalized().rotation_difference(goal).to_matrix().to_4x4()
        if source.kind == 'FACE':
            sides, targets = face_tangents(source), face_tangents(target)
            if sides and targets:
                side = rotation.to_3x3() @ sides[0]
                other = max(targets, key=lambda v: abs(side.dot(v)))
                if side.dot(other) < 0:
                    other = -other
                angle = math.atan2(axis.dot(side.cross(other)), side.dot(other))
                rotation = Matrix.Rotation(angle, 4, axis) @ rotation
    return Matrix.Translation(target.point) @ rotation @ Matrix.Translation(-source.point)


def matrix_error(a, b):
    return max(abs(a[i][j] - b[i][j]) for i in range(4) for j in range(4))


def validate(feature):
    if feature.obj.name not in bpy.data.objects or feature.owner.name not in bpy.data.objects:
        raise ValueError('An object was removed. Choose the features again.')
    if (matrix_error(feature.obj.matrix_world, feature.matrix) > 1e-5 or
            matrix_error(feature.owner.matrix_world, feature.owner_matrix) > 1e-5):
        raise ValueError('An object moved. Choose the features again.')


class Placement:
    """Recompute each preview from the picked pose; Cancel restores native channels."""
    def __init__(self, context, source, target):
        validate(source)
        validate(target)
        obj = source.owner
        if obj.library and not obj.override_library:
            raise ValueError('The source is linked and cannot be moved')
        if obj == target.owner or obj in backend.ancestors(target.owner) or target.owner in backend.ancestors(obj):
            raise ValueError('Choose independent source and target objects')
        self.layer = context.view_layer
        self.source, self.target = source, target
        self.basis = obj.matrix_basis.copy()
        self.channels = {name: tuple(getattr(obj, name)) for name in
                         ('location', 'scale', 'rotation_euler', 'rotation_quaternion', 'rotation_axis_angle')}
        self.alignments = {}
        self.delta = Matrix.Identity(4)
        self.expected = source.owner_matrix.copy()
        self.dirty = False

    def restore(self):
        if self.dirty:
            for name, value in self.channels.items():
                setattr(self.source.owner, name, value)
            self.layer.update()
            self.dirty = False

    def check(self):
        validate(self.target)
        if (matrix_error(self.source.owner.matrix_world, self.expected) > 1e-4 or
                matrix_error(self.source.obj.matrix_world, self.delta @ self.source.matrix) > 1e-4):
            raise ValueError('The source changed. Choose the features again.')

    def place(self, delta):
        self.check()
        obj = self.source.owner
        desired = delta @ self.source.owner_matrix
        self.dirty = True
        try:
            if obj.constraints:
                obj.matrix_basis = self.basis @ self.source.owner_matrix.inverted_safe() @ desired
            else:
                obj.matrix_world = desired
            self.layer.update()
            if (matrix_error(obj.matrix_world, desired) > 1e-4 or
                    matrix_error(self.source.obj.matrix_world, delta @ self.source.matrix) > 1e-4):
                raise ValueError('A parent or constraint prevents this placement.')
        except (RuntimeError, ValueError, ReferenceError):
            self.restore()
            raise
        self.delta = delta
        self.expected = desired


def apply_alignment(context, source, target, rotate=True, reverse=False):
    placement = Placement(context, source, target)
    delta = alignment_delta(source, target, rotate, reverse)
    placement.place(delta)
    return delta


def flat_patch(surface,face):
    """Strictly coplanar connected facets, so mesh triangulation is not a face."""
    normal=surface.normals[face];origin=surface.vertices[surface.faces[face][0]]
    limit=math.cos(math.radians(.5));seen={face};pending=[face];n=0
    while pending:
        current=pending.pop()
        for edge in surface.face_edges[current]:
            for other in surface.edges[edge]-seen:
                if normal.dot(surface.normals[other])<limit:continue
                if any(abs((surface.vertices[i]-origin).dot(normal))>1e-4 for i in surface.faces[other]):continue
                seen.add(other);pending.append(other)
        n+=1
        if n%256==0:yield 'Finding the face boundary…'
    return seen


def centroid(surface,faces):
    total=0.;center=Vector()
    for face in faces:
        coords=[surface.vertices[i] for i in surface.faces[face]];a=coords[0]
        for b,c in zip(coords[1:-1],coords[2:]):
            area=(b-a).cross(c-a).length*.5
            center+=(a+b+c)*(area/3);total+=area
    return center/total if total>1e-12 else surface.vertices[surface.faces[next(iter(faces))][0]].copy()


def segment_distance(point,a,b):
    d=b-a;t=max(0,min(1,(point-a).dot(d)/d.length_squared)) if d.length_squared>1e-10 else 0
    return (point-(a+d*t)).length


def omitted_face_hit(context, space, origin, direction, max_depth, cache, source, guided):
    from . import shapes, shape_faces

    if 'omitted_roots' not in cache:
        cache['omitted_roots'] = [obj for obj in context.view_layer.objects
                                  if obj.get(shapes.ROOT) and obj.get('bbe_shape_excluded')]
    closest = None
    for root in cache['omitted_roots']:
        if guided and guided.owns(root) != (source is None):
            continue
        if source and (source.owner == root or root in backend.ancestors(source.owner)
                       or source.owner in backend.ancestors(root)):
            continue
        s = root.bbe_shape
        mask = root.get('bbe_shape_excluded', '')
        if s.dimension != 'D3' or not mask or root.hide_select or not root.visible_get(viewport=space):
            continue
        key = ('omitted', root.session_uid, mask, s.shell, s.width, s.depth, s.height,
               s.sides, s.detail, s.tube_ratio, s.bend, s.twist, s.pinch, root.get('bbe_shape_fill_scale'))
        if key not in cache:
            cache[key] = shape_faces.omitted_surface(s, mask.split('|'))
        surface = cache[key]
        if surface is None:
            continue
        matrix = root.matrix_world
        try:
            inverse = matrix.inverted()
        except ValueError:
            continue
        local_ray = inverse.to_3x3() @ direction
        scale = local_ray.length
        hit = surface.ray_face(inverse @ origin, local_ray / scale)
        if hit is None:
            continue
        index, distance = hit
        depth = distance / scale
        if 0 <= depth < max_depth:
            max_depth = depth
            closest = root, surface, index
    return closest


def pick_feature(context,xy,region,area,scene,mode,cache,selected,source=None,guided=None):
    # Neighbor rays make vertices and silhouette edges easy to acquire.
    hits=[];dg=context.evaluated_depsgraph_get();rv=area.spaces.active.region_3d
    from .viewport_cutaway import limits, ray_segment
    cuts = limits(scene)
    offsets=[(0,0)] if mode=='FACE' else [(0,0),(-9,0),(9,0),(0,-9),(0,9)]
    for dx,dy in offsets:
        coord=xy+Vector((dx,dy));origin=view.region_2d_to_origin_3d(region,rv,coord);direction=view.region_2d_to_vector_3d(region,rv,coord)
        ray = ray_segment(cuts, origin, direction)
        if ray is None:continue
        origin, reach = ray
        hit,loc,normal,index,obj,matrix=scene.ray_cast(dg,origin,direction,distance=reach)
        if mode == 'FACE':
            # Geometry in front of an opening still wins, including visible trim.
            depth = (loc - origin).dot(direction) - 1e-5 if hit else reach
            omitted = omitted_face_hit(context, area.spaces.active, origin, direction,
                                       depth, cache, source, guided)
            if omitted:
                root, surface, face = omitted
                patch_key = ('omitted_patch', id(surface), face)
                if patch_key not in cache:
                    patch = yield from flat_patch(surface, face)
                    outline = [surface.vertices[i] for edge in surface.boundary(patch) for i in edge]
                    geometry = centroid(surface, patch), outline
                    for member in patch:
                        cache[('omitted_patch', id(surface), member)] = geometry
                center, outline = cache[patch_key]
                world = root.matrix_world.copy()
                outward = world.to_3x3().inverted().transposed() @ surface.normals[face]
                return Feature(root, root, world @ center, outward.normalized(),
                               [world @ p for p in outline], world, world.copy(), mode)
        if hit and obj.type=='MESH' and not obj.hide_select:
            hits.append((obj,index,matrix,loc))
    best=None;best_distance=24*max(.75,context.preferences.system.ui_scale)
    visited=set()
    for obj,index,matrix,loc in hits:
        mesh=obj.evaluated_get(dg).data
        key=(obj.as_pointer(),mesh.as_pointer(),len(mesh.vertices),len(mesh.polygons),tuple(v for row in matrix for v in row))
        if key not in cache:
            surface=curve_surface.Surface.__new__(curve_surface.Surface)
            yield from surface.build_steps(mesh,matrix);cache[key]=surface
        surface=cache[key]
        # Blender can return the original polygon index for a modifier hit, even
        # when the evaluated mesh has different faces (or no original index).
        if obj.modifiers or not 0 <= index < len(surface.faces):
            from mathutils.bvhtree import BVHTree
            if not hasattr(surface, 'align_tree'):
                surface.align_tree = BVHTree.FromPolygons(surface.vertices, surface.faces)
            _, _, index, _ = surface.align_tree.find_nearest(loc)
            if index is None:continue
        face_key=(key,index)
        if face_key in visited:continue
        visited.add(face_key)
        if mode!='EDGE':
            faces=yield from flat_patch(surface,index)
            edges=surface.boundary(faces)
        owner=backend.owner(obj,selected)
        if source and (owner==source.owner or source.owner in backend.ancestors(owner) or owner in backend.ancestors(source.owner)):continue
        def feature(point,direction,lines):return Feature(obj,owner,point,direction,lines,obj.matrix_world.copy(),owner.matrix_world.copy(),mode)
        if mode=='FACE':
            lines=[surface.vertices[v] for edge in sorted(edges) for v in edge]
            return feature(centroid(surface,faces),surface.normals[index],lines)
        if mode=='POINT':
            ids={v for edge in edges for v in edge} or set(surface.faces[index])
            for n,i in enumerate(ids):
                point=surface.vertices[i];screen=view.location_3d_to_region_2d(region,rv,point)
                if screen is not None and (screen-xy).length<best_distance:
                    best_distance=(screen-xy).length;best=feature(point.copy(),Vector(),[])
                if n%256==0:yield 'Detecting points…'
        else:
            yield from surface.patch_steps(index)
            result=surface.section_at(index,loc,xy,region,rv,context.preferences.system.ui_scale,
                                      curve_surface.edge_turn(context))
            if not result:continue
            seed,section,distance=result
            if distance>=best_distance:continue
            a,b=(surface.vertices[i] for i in seed)
            direction=(b-a).normalized()
            points=[surface.vertices[i] for pair in sorted(section) for i in pair]
            # Straight runs align at their midpoint. On a bend, the clicked
            # segment supplies the contact tangent rather than an imaginary chord.
            straight=all(abs((q-p).normalized().dot(direction))>.99985
                         for p,q in zip(points[::2],points[1::2]))
            if straight:
                ends=min(points,key=direction.dot),max(points,key=direction.dot)
                contact=(ends[0]+ends[1])*.5
            else:
                contact=a+direction*max(0.,min((b-a).length,(loc-a).dot(direction)))
            best_distance=distance
            best=feature(contact,direction,points)
    return best


class BBE_OT_align_geometry(bpy.types.Operator):
    bl_idname=PREFIX+'.align_geometry';bl_label='Align';bl_options={'REGISTER','UNDO','BLOCKING'}
    bl_description='Pick a source point, edge or face, then a target. Preview and apply the alignment'
    shape_kind:bpy.props.StringProperty(options={'HIDDEN','SKIP_SAVE'})
    mode:bpy.props.EnumProperty(items=[('POINT','Points','Move two detected vertices together'),('EDGE','Edges','Match two edge centers and directions'),('FACE','Faces','Match two broad face centers and normals')],default='EDGE', options={'SKIP_SAVE'})
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and context.area and context.area.type=='VIEW_3D'
    def invoke(self,context,event):
        if context.region.type!='WINDOW':
            region=next(r for r in context.area.regions if r.type=='WINDOW')
            with context.temp_override(region=region):result=getattr(bpy.ops,PREFIX).align_geometry('INVOKE_DEFAULT',mode=self.mode,shape_kind=self.shape_kind)
            return {'CANCELLED'} if result=={'RUNNING_MODAL'} else result
        if _sessions:self.report({'INFO'},'Finish the current alignment first');return {'CANCELLED'}
        self.area=context.area;self.region=context.region;self.scene=context.scene;self.window=context.window;self.wm=context.window_manager
        self.guided=None
        if self.properties.is_property_set('shape_kind') and self.shape_kind:
            from .shape_placement import ShapeAlignment
            self.guided=ShapeAlignment(context,self)
        self.selected=list(context.selected_objects);self.source=None;self.target=None;self.hover=None;self.reverse=False
        self.placement=None;self.angle=0.;self.axis='Z';self.point_rotation=Matrix.Identity(4)
        self.angle_drag=None;self.angle_text=None
        self.cache={};self.job=None;self.pending_click=False;self.last_xy=None;self.status='';self.orbit=False
        self.helper_key=PREFIX+'_curve_helper';self.helper=getattr(context.scene,self.helper_key);setattr(context.scene,self.helper_key,False)
        self.handles=[bpy.types.SpaceView3D.draw_handler_add(self.draw_panel,(),'WINDOW','POST_PIXEL'),bpy.types.SpaceView3D.draw_handler_add(self.draw_world,(),'WINDOW','POST_VIEW')]
        self.timer=self.wm.event_timer_add(.02,window=self.window);_sessions.append(self)
        self.window.cursor_modal_set('CROSSHAIR');context.window_manager.modal_handler_add(self);self.area.tag_redraw()
        return {'RUNNING_MODAL'}
    def panel_layout(self):
        if self.guided:return self.guided.layout()
        s=min(max(.75,bpy.context.preferences.system.ui_scale),max(.55,(self.region.width-12)/348))
        width=348*s
        buttons=[(m,label,12+i*109,-65,104,28) for i,(m,label) in
                 enumerate([('EDGE','Edges'),('FACE','Faces'),('POINT','Points')])]
        if self.mode=='EDGE' and not self.target:buttons.append(('TOLERANCE','Edge settings',241,-30,95,23))
        if self.target:
            buttons.extend([('MINUS','−90°',12,-145,62,30),
                            ('ANGLE',self.angle_text+'|' if self.angle_text is not None else f'{self.angle:g}°',79,-145,190,30),
                            ('PLUS','+90°',274,-145,62,30)])
            if self.mode=='POINT':
                for i,axis in enumerate('XYZ'):
                    buttons.append((axis,axis,12+i*40,-182,36,28))
            else:
                buttons.append(('FLIP',('Touch faces' if self.reverse else 'Flip piece') if self.mode=='FACE' else 'Swap edge ends',12,-182,148,28))
            buttons.append(('TARGET','Change target',173,-182,163,28))
            buttons.extend([('CANCEL','Cancel',12,-222,105,30),('APPLY','Place',123,-222,213,30)])
            height=234*s
        else:
            if self.source:buttons.append(('SOURCE','Change source',12,-146,155,28))
            buttons.append(('CANCEL','Cancel',179,-146,157,28))
            height=158*s
        x=min(48*s,max(6,self.region.width-width-6))
        top=min(self.region.height-8*s,max(height+6,self.region.height-128*s))
        return s,x,top,width,height,buttons

    def reset_placement(self):
        if self.placement:
            self.placement.restore()
        self.placement=None
        self.target=None
        self.angle=0.
        self.reverse=False
        self.axis='Z'
        self.point_rotation=Matrix.Identity(4)
        self.angle_text=self.angle_drag=None

    def update_placement(self):
        rotation=Matrix.Rotation(math.radians(self.angle),4,self.axis if self.mode=='POINT' else self.target.direction)
        pivot=self.target.point
        if self.reverse not in self.placement.alignments:
            self.placement.alignments[self.reverse]=alignment_delta(self.source,self.target,reverse=self.reverse)
        self.placement.place(Matrix.Translation(pivot) @ rotation @ self.point_rotation @
                             Matrix.Translation(-pivot) @ self.placement.alignments[self.reverse])

    def set_angle(self, angle):
        self.angle=round(math.remainder(angle,360.),5)
        self.update_placement()

    def close_job(self):
        if self.job:self.job.close()
        self.job=None;self.pending_click=False
    def pick_steps(self,context,xy):
        found=yield from pick_feature(context,xy,self.region,self.area,self.scene,self.mode,self.cache,self.selected,self.source,self.guided)
        if self.guided and found:
            if self.guided.owns(found.obj)!=(self.source is None):return None
            if self.source is None:
                found.owner=self.guided.root
                found.owner_matrix=found.owner.matrix_world.copy()
        return found
    def start_pick(self,context,xy,clicked=False):
        self.close_job();self.hover=None;self.last_xy=xy.copy();self.pending_click=clicked
        if self.target or (self.guided and not self.guided.root):return
        self.job=self.pick_steps(context,xy);self.status='Detecting geometry…'
    def advance(self):
        deadline=time.perf_counter()+.006
        while self.job and time.perf_counter()<deadline:
            try:self.status=next(self.job)
            except StopIteration as end:
                self.hover=end.value;self.job=None;self.status=''
                if self.pending_click:
                    self.pending_click=False
                    if self.hover:
                        if self.guided:
                            try:self.guided.accept(bpy.context,self.hover)
                            except (ValueError,RuntimeError,ReferenceError) as exc:self.status=str(exc)
                        elif self.source:
                            try:
                                self.placement=Placement(bpy.context,self.source,self.hover)
                                self.target=self.hover
                                self.update_placement()
                            except (ReferenceError,RuntimeError,ValueError) as exc:
                                self.reset_placement()
                                self.status=str(exc)
                        else:self.source=self.hover
                        self.hover=None
                    else:self.status='Move closer to a visible '+self.mode.lower()+'.'
            except (ReferenceError,RuntimeError,ValueError) as exc:
                self.job=None;self.pending_click=False;self.status=str(exc)
        self.area.tag_redraw()
    def draw_panel(self):
        context=bpy.context
        if context.area!=self.area or context.region!=self.region:return
        if self.guided:return self.guided.draw(context)
        w.update_theme(context);s,x,top,width,height,buttons=self.panel_layout();shader=gpu.shader.from_builtin('UNIFORM_COLOR')
        with w.canvas(context):
            w.rounded(shader,x,top-height,width,height,12*s,w.INK)
            w.text(i18n.interface('ALIGN'),x+14*s,top-25*s,13*s)
            for action,label,bx,by,bw,bh in buttons:
                active=action==self.mode or action=='FLIP' and self.reverse or action==self.axis and self.mode=='POINT'
                enabled=action!='APPLY' or self.target is not None
                color=w.PURPLE if active or action=='APPLY' and enabled else w.BUTTON
                w.rounded(shader,x+bx*s,top+by*s,bw*s,bh*s,5*s,color)
                w.text(i18n.interface(label),x+(bx+bw/2)*s,top+(by+9)*s,11*s,w.TEXT if enabled else w.MUTED,align='CENTER')
            if self.target:
                caption={'POINT':'Rotate about point · world axis','EDGE':'Rotate around edge','FACE':'Face flipped' if self.reverse else 'Faces touching'}[self.mode]
                w.text(i18n.interface(caption),x+14*s,top-86*s,11*s)
                detail='Drag the angle or click to type degrees.'
            else:
                prompt='Pick the destination {feature}.' if self.source else 'Pick the {feature} on the piece to move.'
                w.text(i18n.interface(prompt).format(feature=i18n.interface(self.mode.lower())),x+14*s,top-87*s,11*s)
                detail=self.source.owner.name if self.source else 'The first piece moves.'
            w.text(i18n.interface(self.status or detail)[:55],x+14*s,top-104*s,10*s,w.MUTED)
            for feature,color in [(self.source,SOURCE),(self.target,TARGET),(self.hover,TARGET if self.source else SOURCE)]:
                if feature and not (self.target and feature is self.source):
                    pixel=view.location_3d_to_region_2d(self.region,context.region_data,feature.point)
                    if pixel:w.disc(shader,pixel.x,pixel.y,5*s,color)
    def draw_world(self):
        if bpy.context.area!=self.area or bpy.context.region!=self.region:return
        shader=gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR');groups=[]
        for feature,color in [(self.source,SOURCE),(self.target,TARGET),(self.hover,TARGET if self.source else SOURCE)]:
            if feature and feature.lines and not ((self.guided or self.placement) and feature is self.source):groups.append((feature.lines,color))
        depth=gpu.state.depth_test_get();mask=gpu.state.depth_mask_get()
        try:
            gpu.state.depth_test_set('NONE');gpu.state.depth_mask_set(False)
            for lines,color in groups:
                if not lines:continue
                batch=batch_for_shader(shader,'LINES',{'pos':lines});shader.bind();shader.uniform_float('viewportSize',(self.region.width,self.region.height));shader.uniform_float('lineWidth',2.5);shader.uniform_float('color',color);batch.draw(shader)
        finally:gpu.state.depth_test_set(depth);gpu.state.depth_mask_set(mask)
    def cleanup(self):
        if self not in _sessions:return
        from . import wasd_navigation
        if getattr(wasd_navigation._active,'_owner',None)==self:wasd_navigation.stop()
        _sessions.remove(self);self.close_job()
        if self.guided:self.guided.cleanup()
        elif self.placement:
            try:self.reset_placement()
            except ReferenceError:self.placement=None
        for handle in self.handles:bpy.types.SpaceView3D.draw_handler_remove(handle,'WINDOW')
        self.handles=[];self.wm.event_timer_remove(self.timer);self.window.cursor_modal_restore()
        setattr(self.scene,self.helper_key,self.helper);self.area.tag_redraw();self.cache.clear()
    def action(self,context,action):
        if self.guided:return self.guided.action(context,action)
        if action=='CANCEL':self.cleanup();return {'CANCELLED'}
        try:
            if action=='APPLY' and self.placement:
                self.placement.check()
                self.placement=None
                self.cleanup()
                return {'FINISHED'}
            if action in {'POINT','EDGE','FACE','SOURCE','TARGET'}:
                self.close_job()
                self.reset_placement()
                if action!='TARGET':self.source=None
                if action in {'POINT','EDGE','FACE'}:self.mode=action
                self.hover=None;self.status='';self.cache.clear();self.last_xy=None
            elif self.placement:
                if action=='FLIP':
                    self.reverse=not self.reverse
                    self.update_placement()
                elif action in {'PLUS','MINUS'}:
                    self.set_angle(self.angle+(90 if action=='PLUS' else -90))
                elif action in {'X','Y','Z'} and action!=self.axis:
                    self.point_rotation=Matrix.Rotation(math.radians(self.angle),4,self.axis) @ self.point_rotation
                    self.axis=action
                    self.angle=0.
        except (ValueError,RuntimeError,ReferenceError) as exc:
            self.reset_placement()
            self.status=str(exc)
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def angle_event(self,context,event):
        if self.angle_text is not None:
            if event.value!='PRESS':return
            if event.type in {'RET','NUMPAD_ENTER','LEFTMOUSE'}:
                try:
                    angle=float(self.angle_text)
                    if math.isfinite(angle):self.set_angle(angle)
                except ValueError:pass
                self.angle_text=None
            elif event.type=='ESC':self.angle_text=None
            elif event.type=='BACK_SPACE':self.angle_text=self.angle_text[:-1]
            elif event.unicode and event.unicode in '0123456789.+-' and len(self.angle_text)<12:
                self.angle_text+=event.unicode
        elif self.angle_drag:
            start,value,dragged=self.angle_drag
            dx=(event.mouse_x-start)/max(.75,context.preferences.system.ui_scale)
            if event.type=='ESC':
                self.set_angle(value);self.angle_drag=None
            elif event.type in {'MOUSEMOVE','LEFTMOUSE'}:
                dragged=dragged or abs(dx)>2
                if dragged:self.set_angle(value+dx*.75)
                self.angle_drag=(start,value,dragged)
                if event.type=='LEFTMOUSE' and event.value=='RELEASE':
                    self.angle_drag=None
                    if not dragged:self.angle_text=''
        self.area.tag_redraw()

    def cancel(self,context):
        self.cleanup()

    def modal(self,context,event):
        if self not in _sessions:return {'CANCELLED'}
        if context.window!=self.window:return {'PASS_THROUGH'}
        if getattr(self,'settings_pending',False):
            if event.type=='LEFTMOUSE' and event.value=='RELEASE':
                self.settings_pending=False
                bpy.ops.bbe.curve_trace_settings('INVOKE_DEFAULT')
            return {'RUNNING_MODAL'}
        if getattr(self,'settings_prompt',False):return {'PASS_THROUGH'}
        if self.scene!=context.scene or self.area.type!='VIEW_3D':
            self.cleanup();return {'CANCELLED'}
        if not self.guided and (self.angle_drag or self.angle_text is not None):
            try:self.angle_event(context,event)
            except (RuntimeError,ValueError,ReferenceError) as exc:
                self.reset_placement();self.status=str(exc)
            return {'RUNNING_MODAL'}
        if self.guided and self.guided.drag:return self.guided.adjust_event(context,event)
        if event.type=='TIMER':
            if not self.job:return {'PASS_THROUGH'} if self.guided else {'RUNNING_MODAL'}
            self.advance();return {'RUNNING_MODAL'}
        if event.value=='PRESS' and event.type=='RIGHTMOUSE':
            from . import wasd_navigation
            prefs=wasd_navigation.preferences(context)
            if prefs and prefs.bbe_wasd_enabled:
                self.close_job()
                self.hover=None
                self.last_xy=None
                self.status=''
                self.area.tag_redraw()
                # The nested navigation modal owns motion, keys and RMB release.
                # Align retains the staged shape and either confirmed pick.
                if bpy.ops.bbe.wasd_navigation.poll():
                    bpy.ops.bbe.wasd_navigation('INVOKE_DEFAULT',from_alignment=True)
                return {'RUNNING_MODAL'}
            return {'PASS_THROUGH'} if not self.guided else {'RUNNING_MODAL'}
        if event.value=='PRESS' and event.type=='ESC':return self.action(context,'CANCEL')
        if not self.guided and event.value=='PRESS' and event.type in {'RET','NUMPAD_ENTER'}:return self.action(context,'APPLY')
        if event.type=='MIDDLEMOUSE':
            self.orbit=event.value=='PRESS';self.close_job();self.hover=None;return {'PASS_THROUGH'}
        if self.orbit or event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE','NDOF_MOTION'}:return {'PASS_THROUGH'}
        xy=Vector((event.mouse_x-self.region.x,event.mouse_y-self.region.y));s,x,top,width,height,buttons=self.panel_layout()
        inside=x<=xy.x<=x+width and top-height<=xy.y<=top
        over_angle=inside and any(key=='ANGLE' and x+bx*s<=xy.x<=x+(bx+bw)*s and top+by*s<=xy.y<=top+(by+bh)*s for key,_,bx,by,bw,bh in buttons)
        self.window.cursor_modal_set('SCROLL_X' if over_angle else 'DEFAULT' if inside or self.target else 'CROSSHAIR')
        if event.type=='LEFTMOUSE' and event.value=='PRESS':
            if inside:
                for action,_,bx,by,bw,bh in buttons:
                    if x+bx*s<=xy.x<=x+(bx+bw)*s and top+by*s<=xy.y<=top+(by+bh)*s:
                        if self.guided and action in {'ANGLE','SLIDE'}:
                            self.guided.drag=(action,x+bx*s,bw*s)
                            return self.guided.adjust_event(context,event)
                        if action=='ANGLE' and not self.guided:
                            self.angle_drag=(event.mouse_x,self.angle,False)
                            return {'RUNNING_MODAL'}
                        if action=='TOLERANCE':
                            self.close_job();self.settings_pending=True
                            return {'RUNNING_MODAL'}
                        return self.action(context,action)
            else:self.start_pick(context,xy,True)
        elif event.type=='MOUSEMOVE' and not self.pending_click and not self.target:
            if inside:self.close_job();self.hover=None
            elif self.last_xy is None or (xy-self.last_xy).length>3:self.start_pick(context,xy)
        self.area.tag_redraw();return {'RUNNING_MODAL'}

@persistent
def reset(*_):
    for session in list(_sessions):
        try:session.cleanup()
        except (ReferenceError,RuntimeError):
            if session in _sessions:_sessions.remove(session)

def register():
    bpy.utils.register_class(BBE_OT_align_geometry)
    for handler in (bpy.app.handlers.load_pre,bpy.app.handlers.undo_pre):
        if reset not in handler:handler.append(reset)
def unregister():
    reset()
    for handler in (bpy.app.handlers.load_pre,bpy.app.handlers.undo_pre):
        if reset in handler:handler.remove(reset)
    bpy.utils.unregister_class(BBE_OT_align_geometry)

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


def alignment_delta(source,target,rotate=True,reverse=False):
    if source.owner==target.owner:raise ValueError('Choose a target on another object')
    rotation=Matrix.Identity(4)
    if rotate and source.kind!='POINT':
        direction=target.direction.copy()
        if (source.kind=='FACE') != reverse:direction.negate()
        if source.direction.length<1e-8 or direction.length<1e-8:raise ValueError('This feature has no usable direction')
        rotation=source.direction.normalized().rotation_difference(direction.normalized()).to_matrix().to_4x4()
    return Matrix.Translation(target.point)@rotation@Matrix.Translation(-source.point)


def validate(feature):
    if feature.obj.name not in bpy.data.objects or feature.owner.name not in bpy.data.objects:raise ValueError('An object was removed; pick the features again')
    for a,b in [(feature.obj.matrix_world,feature.matrix),(feature.owner.matrix_world,feature.owner_matrix)]:
        if max(abs(a[i][j]-b[i][j]) for i in range(4) for j in range(4))>1e-5:raise ValueError('An object moved; pick the features again')


def apply_alignment(context,source,target,rotate=True,reverse=False):
    validate(source);validate(target)
    obj=source.owner
    if obj.library and not obj.override_library:raise ValueError('The source is linked and cannot be moved')
    if obj==target.owner or obj in backend.ancestors(target.owner) or target.owner in backend.ancestors(obj):
        raise ValueError('Choose independent source and target objects')
    delta=alignment_delta(source,target,rotate,reverse)
    desired=delta@obj.matrix_world
    old_basis=obj.matrix_basis.copy();old_world=obj.matrix_world.copy()
    if obj.constraints:obj.matrix_basis=old_basis@old_world.inverted_safe()@desired
    else:obj.matrix_world=desired
    context.view_layer.update()
    error=max(abs(obj.matrix_world[i][j]-desired[i][j]) for i in range(4) for j in range(4))
    if error>1e-4:
        obj.matrix_basis=old_basis;context.view_layer.update()
        raise ValueError('The source is constrained. Unlink it from its curve or constraint before aligning')
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
        if hit and obj.type=='MESH' and not obj.hide_select and index>=0:
            if not any(o==obj and i==index for o,i,_,_ in hits):hits.append((obj,index,matrix,dg))
    best=None;best_distance=24*max(.75,context.preferences.system.ui_scale)
    for obj,index,matrix,dg in hits:
        mesh=obj.evaluated_get(dg).data
        if index>=len(mesh.polygons):continue
        key=(obj.as_pointer(),mesh.as_pointer(),len(mesh.vertices),len(mesh.polygons),tuple(v for row in matrix for v in row))
        if key not in cache:
            surface=curve_surface.Surface.__new__(curve_surface.Surface)
            yield from surface.build_steps(mesh,matrix);cache[key]=surface
        surface=cache[key];faces=yield from flat_patch(surface,index)
        edges=surface.boundary(faces)
        owner=backend.owner(obj,selected)
        if source and (owner==source.owner or source.owner in backend.ancestors(owner) or owner in backend.ancestors(source.owner)):continue
        def feature(point,direction,lines):return Feature(obj,owner,point,direction,lines,obj.matrix_world.copy(),owner.matrix_world.copy(),mode)
        if mode=='FACE':
            lines=[surface.vertices[v] for edge in edges for v in edge]
            return feature(centroid(surface,faces),surface.normals[index],lines)
        if mode=='POINT':
            ids={v for edge in edges for v in edge} or set(surface.faces[index])
            for n,i in enumerate(ids):
                point=surface.vertices[i];screen=view.location_3d_to_region_2d(region,rv,point)
                if screen is not None and (screen-xy).length<best_distance:
                    best_distance=(screen-xy).length;best=feature(point.copy(),Vector(),[])
                if n%256==0:yield 'Detecting points…'
        else:
            for n,edge in enumerate(edges):
                a,b=[surface.vertices[i] for i in edge];pa,pb=[view.location_3d_to_region_2d(region,rv,p) for p in (a,b)]
                if pa is None or pb is None:continue
                distance=segment_distance(xy,pa,pb)
                if distance<best_distance and (b-a).length>1e-8:
                    chain=surface.edge_chain(edge,max_turn=.5,allowed=edges)
                    direction=(b-a).normalized();points=[surface.vertices[v] for pair in chain for v in pair]
                    a=min(points,key=lambda p:p.dot(direction));b=max(points,key=lambda p:p.dot(direction))
                    best_distance=distance;best=feature((a+b)/2,direction,[a,b])
                if n%256==0:yield 'Detecting edges…'
    return best


class BBE_OT_align_geometry(bpy.types.Operator):
    bl_idname=PREFIX+'.align_geometry';bl_label='Align';bl_options={'REGISTER','UNDO','BLOCKING'}
    bl_description='Pick a source point, edge or face, then a target. Preview and apply the alignment'
    shape_kind:bpy.props.StringProperty(options={'HIDDEN','SKIP_SAVE'})
    mode:bpy.props.EnumProperty(items=[('POINT','Points','Move two detected vertices together'),('EDGE','Edges','Match two edge centers and directions'),('FACE','Faces','Match two broad face centers and normals')],default='POINT')
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and context.area and context.area.type=='VIEW_3D'
    def invoke(self,context,event):
        if context.region.type!='WINDOW':
            region=next(r for r in context.area.regions if r.type=='WINDOW')
            with context.temp_override(region=region):result=getattr(bpy.ops,PREFIX).align_geometry('INVOKE_DEFAULT',mode=self.mode)
            return {'CANCELLED'} if result=={'RUNNING_MODAL'} else result
        if _sessions:self.report({'INFO'},'Finish the current alignment first');return {'CANCELLED'}
        self.area=context.area;self.region=context.region;self.scene=context.scene;self.window=context.window;self.wm=context.window_manager
        self.guided=None
        if self.properties.is_property_set('shape_kind') and self.shape_kind:
            from .shape_placement import ShapeAlignment
            self.guided=ShapeAlignment(context,self)
        self.selected=list(context.selected_objects);self.source=None;self.target=None;self.hover=None;self.rotate=True;self.reverse=False
        self.cache={};self.job=None;self.pending_click=False;self.last_xy=None;self.status='';self.orbit=False
        self.helper_key=PREFIX+'_curve_helper';self.helper=getattr(context.scene,self.helper_key);setattr(context.scene,self.helper_key,False)
        self.handles=[bpy.types.SpaceView3D.draw_handler_add(self.draw_panel,(),'WINDOW','POST_PIXEL'),bpy.types.SpaceView3D.draw_handler_add(self.draw_world,(),'WINDOW','POST_VIEW')]
        self.timer=self.wm.event_timer_add(.02,window=self.window);_sessions.append(self)
        self.window.cursor_modal_set('CROSSHAIR');context.window_manager.modal_handler_add(self);self.area.tag_redraw()
        return {'RUNNING_MODAL'}
    def panel_layout(self):
        if self.guided:return self.guided.layout()
        s=max(.75,bpy.context.preferences.system.ui_scale);width=348*s;height=278*s
        x=min(48*s,max(8,self.region.width-width-8));top=min(self.region.height-28*s,max(height+8,self.region.height-160*s))
        buttons=[(m,label,12+i*110,-68,104,30) for i,(m,label) in enumerate([('POINT','Points'),('EDGE','Edges'),('FACE','Faces')])]
        if self.mode!='POINT':buttons.extend([('ROTATE','Match rotation',12,-158,156,28),('REVERSE','Same facing' if self.mode=='FACE' else 'Reverse direction',180,-158,156,28)])
        buttons.extend([('RESET','Pick again',12,-196,156,28),('BACK','Back one step',180,-196,156,28),('APPLY','Apply Alignment',12,-234,210,30),('CANCEL','Cancel',232,-234,104,30)])
        return s,x,top,width,height,buttons
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
                        elif self.source:self.target=self.hover
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
                active=action==self.mode or action=='ROTATE' and self.rotate or action=='REVERSE' and self.reverse
                enabled=action!='APPLY' or self.target is not None
                color=w.PURPLE if active or action=='APPLY' and enabled else w.BUTTON
                w.rounded(shader,x+bx*s,top+by*s,bw*s,bh*s,5*s,color)
                w.text(i18n.interface(label),x+(bx+bw/2)*s,top+(by+9)*s,11*s,w.TEXT if enabled else w.MUTED,align='CENTER')
            instruction='Preview ready. Apply or pick again.' if self.target else '2. Pick the target '+self.mode.lower()+'.' if self.source else '1. Pick the source '+self.mode.lower()+'.'
            w.text(i18n.interface(instruction),x+14*s,top-94*s,11*s)
            detail=self.status or ('Source: '+self.source.owner.name if self.source else 'The source moves; the target stays in place.')
            w.text(i18n.interface(detail)[:49],x+14*s,top-116*s,10*s,w.MUTED)
            w.text(i18n.interface('Esc: cancel   Enter: apply   Middle mouse: orbit'),x+14*s,top-260*s,10*s,w.MUTED)
            for feature,color in [(self.source,SOURCE),(self.target,TARGET),(self.hover,TARGET if self.source else SOURCE)]:
                if feature:
                    p=view.location_3d_to_region_2d(self.region,context.region_data,feature.point)
                    if p:w.disc(shader,p.x,p.y,6*s,color)
    def draw_world(self):
        if bpy.context.area!=self.area or bpy.context.region!=self.region:return
        shader=gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR');groups=[]
        for feature,color in [(self.source,SOURCE),(self.target,TARGET),(self.hover,TARGET if self.source else SOURCE)]:
            if feature and feature.lines and not (self.guided and feature is self.source):groups.append((feature.lines,color))
        if self.source and self.target and not self.guided:
            try:
                delta=alignment_delta(self.source,self.target,self.rotate,self.reverse)
                boxes=[]
                for obj in [self.source.owner,*self.source.owner.children_recursive][:256]:
                    if obj.type!='MESH':continue
                    points=[delta@obj.matrix_world@Vector(p) for p in obj.bound_box]
                    for a,b in [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]:boxes.extend((points[a],points[b]))
                groups.append((boxes,PREVIEW))
            except (ReferenceError,ValueError):pass
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
        for handle in self.handles:bpy.types.SpaceView3D.draw_handler_remove(handle,'WINDOW')
        self.handles=[];self.wm.event_timer_remove(self.timer);self.window.cursor_modal_restore()
        setattr(self.scene,self.helper_key,self.helper);self.area.tag_redraw();self.cache.clear()
    def action(self,context,action):
        if self.guided:return self.guided.action(context,action)
        if action=='CANCEL':self.cleanup();return {'CANCELLED'}
        if action=='APPLY':
            if not self.target:return {'RUNNING_MODAL'}
            try:apply_alignment(context,self.source,self.target,self.rotate,self.reverse)
            except (ValueError,ReferenceError) as exc:self.status=str(exc);self.report({'WARNING'},str(exc));return {'RUNNING_MODAL'}
            self.cleanup();return {'FINISHED'}
        if action in {'POINT','EDGE','FACE','RESET'}:
            self.close_job();self.source=self.target=self.hover=None;self.status=''
            if action!='RESET':self.mode=action
        elif action=='BACK':
            self.close_job();self.hover=None
            if self.target:self.target=None
            else:self.source=None
        elif action=='ROTATE':self.rotate=not self.rotate
        elif action=='REVERSE':self.reverse=not self.reverse
        self.area.tag_redraw();return {'RUNNING_MODAL'}
    def modal(self,context,event):
        if self not in _sessions:return {'CANCELLED'}
        if self.guided:
            if context.window!=self.window:return {'PASS_THROUGH'}
            if self.scene!=context.scene or self.area.type!='VIEW_3D':
                self.cleanup();return {'CANCELLED'}
            if self.guided.drag:
                return self.guided.adjust_event(context,event)
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
            if self.guided:return {'RUNNING_MODAL'}
            return self.action(context,'CANCEL')
        if event.value=='PRESS' and event.type=='ESC':return self.action(context,'CANCEL')
        if not self.guided and event.value=='PRESS' and event.type in {'RET','NUMPAD_ENTER'}:return self.action(context,'APPLY')
        if event.type=='MIDDLEMOUSE':
            self.orbit=event.value=='PRESS';self.close_job();self.hover=None;return {'PASS_THROUGH'}
        if self.orbit or event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE','NDOF_MOTION'}:return {'PASS_THROUGH'}
        xy=Vector((event.mouse_x-self.region.x,event.mouse_y-self.region.y));s,x,top,width,height,buttons=self.panel_layout()
        inside=x<=xy.x<=x+width and top-height<=xy.y<=top
        self.window.cursor_modal_set('DEFAULT' if inside else 'CROSSHAIR')
        if event.type=='LEFTMOUSE' and event.value=='PRESS':
            if inside:
                for action,_,bx,by,bw,bh in buttons:
                    if x+bx*s<=xy.x<=x+(bx+bw)*s and top+by*s<=xy.y<=top+(by+bh)*s:
                        if self.guided and action in {'ANGLE','SLIDE'}:
                            self.guided.drag=(action,x+bx*s,bw*s)
                            return self.guided.adjust_event(context,event)
                        return self.action(context,action)
            else:self.start_pick(context,xy,True)
        elif event.type=='MOUSEMOVE' and not self.pending_click:
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

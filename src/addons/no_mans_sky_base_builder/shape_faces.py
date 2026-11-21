"""An isolated, orbitable face picker. Preview geometry never enters the scene."""
from math import cos, sin, pi, tau, sqrt
import bpy
from . import i18n
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader
from . import shape_deform, shape_layout, shapes, curve_surface, curve_widgets as ui


def triangles(s):
    kind=s.shell
    result=[]
    def triangle(group,a,b,c):
        result.append((group,(a,b,c)))
    def patch(group,point,nu,nv):
        for i in range(nu):
            for j in range(nv):
                a,b,c,d=(point((i+x)/nu,(j+y)/nv) for x,y in ((0,0),(1,0),(1,1),(0,1)))
                triangle(group,a,b,c);triangle(group,a,c,d)
    def cap(group,ring,z):
        for a,b in zip(ring,ring[1:]+ring[:1]):
            patch(group,lambda u,v:(v*(a[0]*(1-u)+b[0]*u),v*(a[1]*(1-u)+b[1]*u),z),1,4)
    if kind in {'BOX','PYRAMID','CYLINDER','CONE','WEDGE','PRISM'}:
        density=s.detail/s.id_data.get('bbe_shape_fill_scale',1.)
        n=s.sides if kind=='PRISM' else 3 if kind=='WEDGE' else max(12,round(density*8))
        ring=shape_layout.ring(kind,n,2,2)
        cap('Bottom',ring,-1)
        pointed=kind in {'PYRAMID','CONE'}
        if not pointed:cap('Top',ring,1)
        for i,(a,b) in enumerate(zip(ring,ring[1:]+ring[:1])):
            group='Wall' if kind in {'CONE','CYLINDER'} else f'Side {i+1}'
            def point(u,v):
                radius=1-v if pointed else 1
                return ((a.x*(1-u)+b.x*u)*radius,(a.y*(1-u)+b.y*u)*radius,2*v-1)
            patch(group,point,1 if len(ring)>8 else 4,8)
    elif kind=='TORUS':
        for i in range(4):
            def torus(u,v):
                r=1-s.tube_ratio+s.tube_ratio*cos(tau*v)
                a=(i+u)*pi/2
                return (r*cos(a),r*sin(a),sin(tau*v))
            patch(f'Arc {i+1}',torus,8,12)
    elif kind=='SUPERELLIPSOID':
        for axis in range(3):
            for sign in (-1,1):
                def rounded(u,v):
                    p=[0.,0.,0.];p[axis]=sign;p[(axis+1)%3]=2*u-1;p[(axis+2)%3]=2*v-1
                    def coord(i):
                        a,b=p[(i+1)%3]**2,p[(i+2)%3]**2
                        x=p[i]*sqrt(1-(a+b)/2+a*b/3)
                        return (-1 if x<0 else 1)*abs(x)**.65
                    return tuple(coord(i) for i in range(3))
                patch(('+' if sign>0 else '−')+'XYZ'[axis],rounded,8,8)
    else:
        for half in range(2):
            def polar(u,v):
                t=(half+v)/2
                angle=(t if kind=='DOME' else 2*t-1)*pi/2
                r,z=cos(angle),sin(angle)
                if kind=='DOME':z=2*z-1
                if kind=='SPINDLE':r=r**1.8
                if kind=='CAPSULE':
                    if t<.25:r,z=sin(t*tau),-.5-.5*cos(t*tau)
                    elif t>.75:r,z=cos((t-.75)*tau),.5+.5*sin((t-.75)*tau)
                    else:r,z=1,2*t-1
                return (r*cos(u*tau),r*sin(u*tau),z)
            patch('Dome' if kind=='DOME' else 'Upper' if half else 'Lower',polar,32,8)
        if kind=='DOME':
            cap('Bottom',[(cos(i*tau/32),sin(i*tau/32)) for i in range(32)],-1)
    groups,coords=zip(*result)
    points=np.asarray(coords)*np.array([s.width,s.depth,s.height])*.5
    points=shape_deform.map_points(points.reshape(-1,3),s).reshape(-1,3,3)
    return groups,points


def apply_faces(context,root,excluded):
    encoded='|'.join(sorted(excluded))
    previous=root.get('bbe_shape_excluded','')
    if previous==encoded and root.get('bbe_shape_refined'):return
    # Earlier layouts have different slot numbers. Preserve any hand edits on
    # retained legacy pieces instead of transferring them onto unrelated tiles.
    refine=not root.get('bbe_shape_refined')
    if refine:
        for part in shapes.shape_parts(root):
            if shapes.FRAME not in part or any(abs(a-b)>.0001 for row,saved in
                    zip(part.matrix_basis,shapes.decode(part[shapes.FRAME])) for a,b in zip(row,saved)):
                refine=False
                break
    root['bbe_shape_excluded']=encoded
    try:shapes.build(context,owner=root,refine=refine)
    except Exception:
        root['bbe_shape_excluded']=previous
        raise


class OmittedSurface(curve_surface.Surface):
    def __init__(self):
        from collections import defaultdict
        self.vertices, self.faces, self.normals = [], [], []
        self.edges, self.face_edges = defaultdict(set), []

    def ray_face(self, origin, ray):
        """Nearest forward intersection, including a hit shared by fan triangles."""
        origin, ray = np.asarray(origin), np.asarray(ray)
        along = origin.dot(ray)
        nearest = origin - min(0.0, along) * ray
        if nearest.dot(nearest) > self.radius_squared:
            return None
        cross = np.cross(ray, self.ac)
        det = np.einsum('ij,ij->i', self.ab, cross)
        valid = abs(det) > self.areas * 1e-10
        divisor = np.where(valid, det, 1.)
        offset = origin - self.starts
        u = np.einsum('ij,ij->i', offset, cross) / divisor
        q = np.cross(offset, self.ab)
        v = (q @ ray) / divisor
        distance = np.einsum('ij,ij->i', self.ac, q) / divisor
        valid &= (u >= -1e-8) & (v >= -1e-8) & (u + v <= 1 + 1e-8) & (distance >= 0)
        if valid.any():
            index = int(np.argmin(np.where(valid, distance, np.inf)))
            return index, float(distance[index])
        return None


def omitted_surface(settings, excluded):
    """Read-only triangles for Align, in controller space. No Blender datablocks."""
    from mathutils import Vector

    groups, model = triangles(settings)
    groups = np.asarray(groups)
    surface = OmittedSurface()
    for group in excluded:
        coords = model[groups == group]
        if not len(coords):
            continue
        # Top fans and the three negative rounded-box panels are wound inward.
        if group == 'Top' or group.startswith('−'):
            coords = coords[:, (0, 2, 1)]
        normals = np.cross(coords[:, 1] - coords[:, 0], coords[:, 2] - coords[:, 0])
        lengths = np.linalg.norm(normals, axis=1)
        valid = lengths > 1e-12
        # Weld within each named face so triangulation seams disappear on hover.
        points, ids = np.unique(coords[valid].reshape(-1, 3).round(7), axis=0, return_inverse=True)
        facets = ids.reshape(-1, 3) + len(surface.vertices)
        surface.vertices.extend(Vector(p) for p in points)
        for (a, b, c), normal in zip(facets.tolist(), normals[valid] / lengths[valid, None]):
            if len({a, b, c}) < 3:
                continue
            index = len(surface.faces)
            surface.faces.append((a, b, c))
            surface.normals.append(Vector(normal))
            edges = [tuple(sorted(edge)) for edge in ((a, b), (b, c), (c, a))]
            surface.face_edges.append(edges)
            for edge in edges:
                surface.edges[edge].add(index)
    if surface.faces:
        vertices = np.asarray(surface.vertices)
        surface.radius_squared = float(np.einsum('ij,ij->i', vertices, vertices).max()) + 1e-8
        surface.starts, b, c = vertices[np.asarray(surface.faces)].transpose(1, 0, 2)
        surface.ab, surface.ac = b - surface.starts, c - surface.starts
        surface.areas = np.linalg.norm(np.cross(surface.ab, surface.ac), axis=1)
        return surface
    return None


def part_preview(root,context):
    """Read evaluated proxy triangles in the part's native axes, independent of its placement."""
    part=next((p for p in root.children if shapes.INDEX in p),None)
    if part is None:
        part=next((o for o in context.scene.objects if o.get('ObjectID')==root.bbe_shape.part_id),None)
    pieces=[]
    if part:
        graph=context.evaluated_depsgraph_get()
        for obj,relative in shapes.part_geometry(part):
            evaluated=obj.evaluated_get(graph)
            mesh=evaluated.to_mesh() if obj.type!='MESH' else evaluated.data
            try:
                if mesh is None or not mesh.polygons:continue
                mesh.calc_loop_triangles()
                coords=np.empty(len(mesh.vertices)*3,dtype=np.float32)
                mesh.vertices.foreach_get('co',coords)
                indices=np.empty(len(mesh.loop_triangles)*3,dtype=np.int32)
                mesh.loop_triangles.foreach_get('vertices',indices)
                mat=np.asarray(relative)
                transformed=coords.reshape(-1,3)@mat[:3,:3].T+mat[:3,3]
                pieces.append(transformed[indices.reshape(-1,3)])
            finally:
                if obj.type!='MESH':evaluated.to_mesh_clear()
    guide=not pieces
    if guide:
        # A fully omitted shell can have no instance left to preview.
        corners=np.array([(x,y,z) for x in (-1,1) for y in (-1,1) for z in (-1,1)])
        quads=((0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3))
        pieces=[corners[[tri for a,b,c,d in quads for tri in ((a,b,c),(a,c,d))]]]
    points=np.concatenate(pieces)
    normals=np.cross(points[:,1]-points[:,0],points[:,2]-points[:,0])
    valid=np.linalg.norm(normals,axis=1)>1e-12
    points,normals=points[valid],normals[valid]
    if not len(points):raise ValueError('This part has no visible surface')
    axes=np.argmax(abs(normals),axis=1)
    signs=normals[np.arange(len(axes)),axes]<0
    groups=np.asarray(shapes.PART_FACES)[2*axes+signs]
    return groups,points,guide


_open={}

@bpy.app.handlers.persistent
def close_all(*unused):
    for picker in tuple(_open.values()):
        picker.close()


class BBE_OT_shape_faces(bpy.types.Operator):
    bl_idname='bbe.shape_faces'
    bl_label='Choose Shape Faces'
    bl_description='Click surfaces to include or omit. Drag the preview to see the other side'
    bl_options={'UNDO','BLOCKING'}

    part_face:bpy.props.BoolProperty(name='Choose part face',options={'SKIP_SAVE'})

    @classmethod
    def description(cls,context,props):
        return 'Rotate the part and click the side to face out' if props.part_face else cls.bl_description

    def invoke(self,context,event):
        self.area_key=context.area.as_pointer()
        if self.area_key in _open:return {'CANCELLED'}
        self.root=shapes.selected_root(context)
        if not self.root:return {'CANCELLED'}
        if self.part_face:
            try:self.groups,self.model,self.axis_guide=part_preview(self.root,context)
            except (ValueError,RuntimeError) as exc:
                self.report({'WARNING'},str(exc));return {'CANCELLED'}
            self.chosen=shapes.resolved_part_face(self.root)
            self.excluded=set()
        else:
            if self.root.bbe_shape.dimension!='D3':return {'CANCELLED'}
            self.groups,self.model=triangles(self.root.bbe_shape)
            self.names=set(self.groups)
            self.excluded=set(filter(None,self.root.get('bbe_shape_excluded','').split('|')))&self.names
        self.model-= (self.model.max(axis=(0,1))+self.model.min(axis=(0,1)))/2
        self.radius=max(.001,np.linalg.norm(self.model,axis=2).max())
        self.projection_key=None;self.paint_key=None;self.batch=None;self.buffer=None
        self.yaw,self.pitch=.53,.42
        self.area=context.area;self.region=context.region
        self.press=None;self.hover=None;self.dragged=False
        self.handler=bpy.types.SpaceView3D.draw_handler_add(self.draw_preview,(), 'WINDOW','POST_PIXEL')
        _open[self.area_key]=self
        context.window_manager.modal_handler_add(self);self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def bounds(self):
        region=self.region
        scale=min(bpy.context.preferences.system.ui_scale,region.width/540,region.height/482)
        w,h=520*scale,462*scale
        return (region.width-w)/2,(region.height-h)/2,w,h,scale

    def project(self):
        x,y,w,h,s=self.bounds()
        key=(x,y,w,h,s,self.yaw,self.pitch)
        if key==self.projection_key:return self.projected
        ca,sa=cos(self.yaw),sin(self.yaw);cb,sb=cos(self.pitch),sin(self.pitch)
        axes=np.array([[ca,sa,0],[-sa*sb,ca*sb,cb],[sa*cb,-ca*cb,sb]])
        p=self.model@axes.T
        p[:,:,:2]*=(h-144*s)/2/self.radius
        p[:,:,0]+=x+w/2;p[:,:,1]+=y+h*.52
        self.projection_key=key;self.projected=p
        return p

    def pick(self,x,y):
        v=self.project()
        a=v[:,0];ab=v[:,1]-a;ac=v[:,2]-a
        dx=x-a[:,0];dy=y-a[:,1];den=ab[:,0]*ac[:,1]-ac[:,0]*ab[:,1]
        safe=np.where(abs(den)>1e-6,den,1)
        u=(dx*ac[:,1]-dy*ac[:,0])/safe;v=(ab[:,0]*dy-ab[:,1]*dx)/safe
        hits=(abs(den)>1e-6)&(u>=0)&(v>=0)&(u+v<=1)
        if not hits.any():return None
        return self.groups[np.argmax(np.where(hits,a[:,2]+u*ab[:,2]+v*ac[:,2],-np.inf))]

    def draw_preview(self):
        ctx=bpy.context
        if ctx.area!=self.area or ctx.region!=self.region:return
        x,y,w,h,s=self.bounds()
        ui.update_theme(ctx)
        with ui.canvas(ctx):
            shader=gpu.shader.from_builtin('UNIFORM_COLOR')
            # Isolate the preview visually without changing object visibility or selection.
            region=ctx.region
            ui.polygon(shader,[(0,0),(region.width,0),(region.width,region.height),(0,region.height)],ui.HEADER)
            ui.rounded(shader,x-1,y-1,w+2,h+2,12*s,ui.EDGE)
            ui.rounded(shader,x,y,w,h,12*s,ui.INK)
            title=(i18n.interface('Pick outside face')+'  ·  '+self.root.bbe_shape.part_id) if self.part_face else i18n.interface('Populate shell faces')
            hint=('Drag to rotate  ·  Click the side that should face out' if self.part_face else
                  'Click a face to toggle  ·  Drag to rotate')
            ui.text(title,x+16*s,y+h-28*s,16*s,ui.TEXT)
            ui.text(i18n.interface(hint),x+16*s,y+h-49*s,12*s,ui.MUTED)
            p=self.project()
            px,py,pw,ph=x+8*s,y+70*s,w-16*s,h-138*s
            key=(self.projection_key,self.hover,frozenset(self.excluded))
            if key!=self.paint_key:
                order=slice(None) if self.part_face else np.argsort(p[:,:,2].mean(axis=1))
                ab=p[:,1]-p[:,0];ac=p[:,2]-p[:,0]
                # Undo screen scaling before computing lighting in view coordinates.
                ab[:,:2]/=(h-144*s)/2/self.radius;ac[:,:2]/=(h-144*s)/2/self.radius
                normal=np.cross(ab,ac);normal/=np.maximum(1e-10,np.linalg.norm(normal,axis=1))[:,None]
                normal*=np.where(normal[:,2:3]<0,-1,1)
                light=np.clip(.78+normal@[-.20,.28,.12],.45,1.1)
                if self.part_face:
                    colors=np.where((self.groups==self.chosen)[:,None],(.17,.58,.75),(.52,.56,.60))
                    if self.hover is not None:colors[self.groups==self.hover]=(.40,.87,1.)
                else:
                    colors=np.array([((.56,.53,.51) if g==self.hover else (.27,.30,.34)) if g in self.excluded
                                     else (.35,.78,.91) if g==self.hover else (.17,.58,.75) for g in self.groups])
                rgba=np.column_stack((np.minimum(1,colors*light[:,None]),np.ones(len(light))))
                self.paint=gpu.shader.from_builtin('SMOOTH_COLOR')
                if self.part_face:
                    coords=p.copy()
                    coords[:,:,0]=(p[:,:,0]-px)*2/pw-1
                    coords[:,:,1]=(p[:,:,1]-py)*2/ph-1
                    coords[:,:,2]=-.9*p[:,:,2]/self.radius
                    positions=coords.reshape(-1,3)
                else:
                    positions=p[order,:,:2].reshape(-1,2)
                self.batch=batch_for_shader(self.paint,'TRIS',{'pos':positions.tolist(),
                                        'color':np.repeat(rgba[order],3,axis=0).tolist()})
                if self.part_face:
                    from mathutils import Matrix
                    size=max(1,round(pw)),max(1,round(ph))
                    if self.buffer is None or self.buffer_size!=size:
                        if self.buffer:self.buffer.free()
                        self.buffer=gpu.types.GPUOffScreen(*size)
                        self.buffer_size=size
                    viewport=gpu.state.viewport_get()
                    scissor=gpu.state.scissor_get()
                    try:
                        with self.buffer.bind(),gpu.matrix.push_pop(),gpu.matrix.push_pop_projection():
                            gpu.state.viewport_set(0,0,*size);gpu.state.scissor_set(0,0,*size)
                            gpu.matrix.load_identity();gpu.matrix.load_projection_matrix(Matrix.Identity(4))
                            gpu.state.depth_mask_set(True);gpu.state.depth_test_set('LESS_EQUAL')
                            gpu.state.active_framebuffer_get().clear(color=(*ui.INK[:3],1.),depth=1.)
                            self.paint.bind();self.batch.draw(self.paint)
                    finally:
                        gpu.state.depth_test_set('NONE');gpu.state.depth_mask_set(False)
                        gpu.state.viewport_set(*viewport);gpu.state.scissor_set(*scissor)
                self.paint_key=key
            if self.part_face:
                from gpu_extras.presets import draw_texture_2d
                draw_texture_2d(self.buffer.texture_color,(px,py),pw,ph)
            else:
                self.paint.bind();self.batch.draw(self.paint)
            if self.part_face:
                desc=(i18n.interface('Axis guide')+'  ·  ' if self.axis_guide else '')+i18n.interface('Pick {face}' if self.hover else 'Outside face: {face}').format(face=self.hover or self.chosen)
            else:
                desc=i18n.interface('{included} / {total} faces included').format(included=len(self.names-self.excluded),total=len(self.names))
                if self.hover:desc=i18n.interface(self.hover)+'  ·  '+i18n.interface('Omitted' if self.hover in self.excluded else 'Included')
            ui.text(desc,x+w/2,y+57*s,12*s,ui.TEXT,'CENTER')
            for i,label in enumerate((i18n.interface('Cancel'),i18n.interface('Use {face}').format(face=self.chosen) if self.part_face else i18n.interface('Apply faces'))):
                button_w=w/2-16*s
                left=x+12*s+i*(button_w+8*s)
                ui.rounded(shader,left,y+10*s,button_w,31*s,6*s,ui.PURPLE if i else ui.BUTTON)
                ui.text(label,left+button_w/2,y+20*s,12*s,ui.TEXT,'CENTER')

    def close(self):
        if self.buffer is not None:
            try:self.buffer.free()
            except ReferenceError:pass
            self.buffer=None
        self.batch=None
        _open.pop(self.area_key,None)
        if self.handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self.handler,'WINDOW');self.handler=None
            try:self.area.tag_redraw()
            except ReferenceError:pass

    def cancel(self,context):self.close()

    def modal(self,context,event):
        if self.handler is None:return {'CANCELLED'}
        x,y=event.mouse_region_x,event.mouse_region_y
        l,b,w,h,s=self.bounds()
        if event.type in {'ESC','RIGHTMOUSE'}:
            self.close();return {'CANCELLED'}
        confirm=event.type in {'RET','NUMPAD_ENTER'} and event.value=='PRESS'
        if event.type in {'LEFTMOUSE','MIDDLEMOUSE'} and event.value=='PRESS':
            self.press=(x,y,self.yaw,self.pitch);self.dragged=False
        if event.type=='MOUSEMOVE':
            if self.press:
                ox,oy,yaw,pitch=self.press
                if abs(x-ox)+abs(y-oy)>4*s:self.dragged=True
                if self.dragged:
                    self.yaw=yaw-(x-ox)*.012/s;self.pitch=max(-1.56,min(1.56,pitch-(y-oy)*.012/s))
            self.hover=None if self.dragged and self.press else self.pick(x,y)
        if event.type in {'LEFTMOUSE','MIDDLEMOUSE'} and event.value=='RELEASE' and self.press:
            self.press=None
            if event.type=='LEFTMOUSE' and not self.dragged:
                if not (l<=x<=l+w and b<=y<=b+h):
                    self.close();return {'CANCELLED'}
                if b+10*s<=y<=b+41*s and l+12*s<=x<=l+w-12*s:
                    if x<l+w/2:self.close();return {'CANCELLED'}
                    confirm=True
                else:
                    group=self.pick(x,y)
                    if group and self.part_face:self.chosen=str(group);confirm=True
                    elif group:self.excluded.symmetric_difference_update({group})
        if confirm:
            self.close()
            try:
                if self.part_face:shapes.apply_part_face(context,self.root,self.chosen)
                else:apply_faces(context,self.root,self.excluded)
            except (ValueError,RuntimeError) as error:
                self.report({'WARNING'},str(error));return {'CANCELLED'}
            return {'FINISHED'}
        if event.type in {'MOUSEMOVE','LEFTMOUSE','MIDDLEMOUSE'}:self.area.tag_redraw()
        return {'RUNNING_MODAL'}


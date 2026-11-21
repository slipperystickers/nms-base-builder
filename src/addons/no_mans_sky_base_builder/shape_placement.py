"""New-shape placement and the guided workflow for the existing Align tool."""
import math
import bpy
import gpu
from mathutils import Matrix, Vector
from . import curve_widgets as widgets, i18n


def seat_shape(context, root, placement):
    """Seat actual proxy geometry, including offsets and evaluated modifiers."""
    import numpy as np
    dg = context.evaluated_depsgraph_get()
    vertices = {}
    bottom = None
    inverse = root.matrix_world.inverted_safe()
    for obj in root.children_recursive:
        if obj.type not in {'MESH','CURVE','SURFACE','FONT'} or obj.hide_viewport:continue
        evaluated = obj.evaluated_get(dg)
        mesh = evaluated.data if obj.type=='MESH' else evaluated.to_mesh()
        try:
            if mesh is None or not mesh.vertices:continue
            key = mesh.as_pointer()
            coords = vertices.get(key) if obj.type=='MESH' else None
            if coords is None:
                coords = np.empty(len(mesh.vertices)*3,dtype=np.float32)
                mesh.vertices.foreach_get('co',coords)
                coords = coords.reshape(-1,3)
                if obj.type=='MESH':vertices[key]=coords
            axis = (inverse @ evaluated.matrix_world)[2]
            low = float(np.min(coords[:,0]*axis[0]+coords[:,1]*axis[1]+coords[:,2]*axis[2])) + axis[3]
            bottom = low if bottom is None else min(bottom,low)
        finally:
            if obj.type!='MESH':evaluated.to_mesh_clear()
    root.matrix_world = placement @ Matrix.Translation((0,0,-(bottom or 0)))
    context.view_layer.update()


# The normal Align operator owns the modal handler, geometry detection, and undo.
def busy(area):
    from . import alignment_tools
    return any(op.area==area and getattr(op,'guided',None) for op in alignment_tools._sessions)


class ShapeAlignment:
    def __init__(self,context,op):
        self.op=op
        self.root=None
        self.members=set()
        self.original=list(context.selected_objects)
        self.active=context.view_layer.objects.active
        from . import shapes
        self.reference=shapes.selected_root(context) or shapes.placement_target(context)
        self.layer=context.view_layer
        self.space=context.space_data
        self.rv=self.space.region_3d
        self.saved_view=None
        self.committed=False
        self.drag=None
        self.angle=self.slide=0.
        self.axis='Z'
        self.settings=context.scene.bbe_shape
        self.draft={k:getattr(self.settings,k) for k in ('dimension','outline','shell','height','depth','paint') if self.settings.is_property_set(k)}
        self.chosen=self.settings.get('chosen_part')

    def owns(self,obj):
        return obj in self.members

    def create(self,context,*,at_cursor):
        from . import shapes
        result=bpy.ops.bbe.start_shape('EXEC_DEFAULT',False,kind=self.op.shape_kind,at_cursor=at_cursor)
        if 'FINISHED' not in result:raise ValueError('Could not build the selected shape')
        self.root=shapes.selected_root(context)
        self.members={self.root,*self.root.children_recursive}
        if self.space.local_view:
            for obj in self.members:obj.local_view_set(self.space,True)

    def focus_source(self,context):
        # Work in view axes so "beside" also works in side, top and oblique views.
        from itertools import product
        from bpy_extras.view3d_utils import location_3d_to_region_2d
        rv,region=self.rv,self.op.region
        self.saved_view=(rv.view_location.copy(),rv.view_distance,rv.view_rotation.copy(),rv.view_perspective)
        rotation=rv.view_rotation.copy()
        inverse=rotation.inverted().to_matrix().to_4x4()
        dg=context.evaluated_depsgraph_get()

        def bounds(objects,fallback):
            lo=Vector((math.inf,)*3);hi=-lo
            for obj in objects:
                if obj.type not in {'MESH','CURVE','FONT','SURFACE'} or not obj.visible_get(viewport=self.space):continue
                evaluated=obj.evaluated_get(dg)
                transform=inverse @ evaluated.matrix_world
                for corner in evaluated.bound_box:
                    v=transform @ Vector(corner)
                    for i in range(3):
                        lo[i]=min(lo[i],v[i]);hi[i]=max(hi[i],v[i])
            if not math.isfinite(lo.x):lo=hi=inverse @ fallback
            return lo,hi

        fixed=[self.reference,*self.reference.children_recursive] if self.reference else []
        anchor=self.reference.matrix_world.translation if self.reference else context.scene.cursor.location
        left,right=bounds(fixed,anchor)
        low,high=bounds(self.members,self.root.matrix_world.translation)
        gap=max(1.,.22*max(*(right-left),*(high-low)))
        offset=(left+right-low-high)/2
        offset.x=right.x+gap-low.x
        self.root.location+=rotation @ offset
        low+=offset;high+=offset
        self.layer.update()

        # Fit both actual bounds and check for a visible gap under perspective.
        combined_lo=Vector(map(min,zip(left,low)));combined_hi=Vector(map(max,zip(right,high)))
        mid=(combined_lo+combined_hi)/2
        if rv.view_perspective=='CAMERA':rv.view_perspective='PERSP'
        rv.view_location=rotation @ mid
        rv.view_distance=max(1.,(combined_hi-combined_lo).length*.75)
        boxes=[[rotation @ Vector(c) for c in product(*zip(lo,hi))] for lo,hi in ((left,right),(low,high))]
        xmin=next((r.width for r in self.op.area.regions if r.type=='TOOLS' and r.width>1),0)+16
        xmax=region.width-next((r.width for r in self.op.area.regions if r.type=='UI' and r.width>1),0)-16
        for _ in range(16):
            rv.update()
            projected=[[location_3d_to_region_2d(region,rv,p) for p in corners] for corners in boxes]
            points=projected[0]+projected[1]
            if all(p is not None and xmin<=p.x<=xmax and 26<=p.y<=region.height-100 for p in points):
                if min(p.x for p in projected[1])-max(p.x for p in projected[0])>2:break
            rv.view_distance*=1.2

    def restore_view(self):
        if not self.saved_view:return
        loc,dist,rot,perspective=self.saved_view
        self.rv.view_location=loc;self.rv.view_distance=dist;self.rv.view_rotation=rot;self.rv.view_perspective=perspective
        self.saved_view=None

    def accept(self,context,feature):
        from . import alignment_tools as align
        op=self.op
        align.validate(feature)
        if not op.source:
            op.source=feature
            op.cache.clear()
            return
        align.validate(op.source)
        # The controller owns the transform, so every generated piece moves together.
        align.apply_alignment(context,op.source,feature)
        op.target=feature
        self.snapped=self.root.matrix_world.copy()
        self.angle=self.slide=0.
        self.limit=(feature.lines[-1]-feature.lines[0]).length/2 if feature.kind=='EDGE' else 0.
        from . import shapes
        shapes.choose(context,[self.root])

    def adjust(self):
        target=self.op.target
        axis=Vector((self.axis=='X',self.axis=='Y',self.axis=='Z')) if target.kind=='POINT' else target.direction.normalized()
        pivot=target.point
        self.root.matrix_world=(Matrix.Translation(pivot+axis*self.slide) @
                                Matrix.Rotation(math.radians(self.angle),4,axis) @
                                Matrix.Translation(-pivot) @ self.snapped)
        self.layer.update()
        self.op.area.tag_redraw()

    def adjust_event(self,context,event):
        if event.type=='ESC' and event.value=='PRESS':
            self.drag=None
            return {'RUNNING_MODAL'}
        if event.type in {'MOUSEMOVE','LEFTMOUSE'}:
            key,left,width=self.drag
            value=min(1,max(-1,2*(event.mouse_x-self.op.region.x-left)/width-1))
            if key=='ANGLE':self.angle=round(value*180)
            else:self.slide=value*self.limit
            self.adjust()
            if event.type=='LEFTMOUSE' and event.value=='RELEASE':self.drag=None
        return {'RUNNING_MODAL'}

    def action(self,context,action):
        op=self.op
        try:
            if action=='CANCEL':
                op.cleanup()
                return {'CANCELLED'}
            if action in {'CURSOR','POINT','EDGE','FACE'}:
                self.create(context,at_cursor=action=='CURSOR')
                if action=='CURSOR':
                    self.committed=True;op.cleanup()
                    return {'FINISHED'}
                op.mode=action
                self.focus_source(context)
            elif action=='DONE' and op.target:
                self.committed=True;op.cleanup()
                return {'FINISHED'}
            elif action=='AGAIN' and op.target:
                self.root.matrix_world=op.source.owner_matrix.copy()
                op.target=None;self.layer.update()
                op.cache.clear()
            elif action=='AXIS':
                self.axis={'Z':'X','X':'Y','Y':'Z'}[self.axis]
                self.adjust()
            elif action=='ZERO':
                self.angle=self.slide=0.;self.adjust()
        except (ReferenceError,RuntimeError,ValueError) as exc:
            op.report({'WARNING'},str(exc));op.cleanup()
            return {'CANCELLED'}
        op.status='';op.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def cleanup(self):
        self.restore_view()
        if self.committed or self.root is None:return
        bpy.data.batch_remove(list(self.members))
        self.members.clear();self.root=None
        for k in ('dimension','outline','shell','height','depth','paint'):
            if k in self.draft:setattr(self.settings,k,self.draft[k])
            else:self.settings.property_unset(k)
        if self.chosen is None:
            if 'chosen_part' in self.settings:del self.settings['chosen_part']
        else:self.settings['chosen_part']=self.chosen
        self.layer.update()
        for o in self.original:
            if self.layer.objects.get(o.name)==o:o.select_set(True,view_layer=self.layer)
        self.layer.objects.active=self.active

    def layout(self):
        op=self.op
        s=min(bpy.context.preferences.system.ui_scale,max(.55,(op.region.width-12)/360))
        width=211 if not self.root else 360
        buttons=[]
        def row(y,items):
            w=(width-24-5*(len(items)-1))/len(items)
            for i,(action,label) in enumerate(items):buttons.append((action,label,12+i*(w+5),-y,w,24))
        if not self.root:
            for i,(action,label) in enumerate((('POINT','Point'),('EDGE','Edge'),('FACE','Face'),('CURSOR','3D cursor'))):
                buttons.append((action,label,12+(i%2)*97,-88-(i//2)*57,92,52))
            buttons.append(('CANCEL','×',width-33,-28,21,21));height=157
        elif op.target:
            row(64,[('ANGLE',i18n.interface('Rotate')+f'   {self.angle:.0f}°')])
            y=93
            if op.mode=='EDGE':
                row(y,[('SLIDE',i18n.interface('Along edge')+f'   {self.slide:.2f}')]);y+=29
            elif op.mode=='POINT':
                row(y,[('AXIS',i18n.interface('Rotation axis')+'   '+self.axis)]);y+=29
            row(y,[('AGAIN','Pick target again'),('ZERO','Reset'),('DONE','Done')])
            height=y+10
        else:
            buttons.append(('CANCEL','×',width-33,-28,21,21));height=49
        ceiling=op.region.height
        for header in op.area.regions:
            if header.type in {'HEADER','TOOL_HEADER'} and header.height>1 and header.y>op.region.y+op.region.height/2:
                ceiling=min(ceiling,header.y-op.region.y)
        x=(op.region.width-width*s)/2
        top=(ceiling+height*s)/2 if not self.root else ceiling-10*s
        return s,x,top,width*s,height*s,buttons

    def draw(self,context):
        from . import shape_layout
        from bpy_extras.view3d_utils import location_3d_to_region_2d
        op=self.op
        s,x,top,width,height,buttons=self.layout()
        widgets.update_theme(context);sh=gpu.shader.from_builtin('UNIFORM_COLOR')
        with widgets.canvas(context):
            widgets.rounded(sh,x,top-height,width,height,9*s,widgets.INK)
            feature = i18n.interface(op.mode.title())
            if not self.root:
                instruction = i18n.interface('Align shape')
            elif op.target:
                instruction = i18n.interface('Connected')
            else:
                prompt = 'Pick the matching feature on your build: {feature}' if op.source else 'Pick a feature on the new shape: {feature}'
                instruction = i18n.interface(prompt).format(feature=feature)
            title=i18n.interface(shape_layout.LABELS[op.shape_kind])+' · '+instruction
            widgets.text(title,x+12*s,top-22*s,13*s)
            if self.root and not op.target:
                hint=op.status or ('Click the target on the existing build.' if op.source else 'The new shape starts on the right.')
                widgets.text(i18n.interface(hint)[:55],x+12*s,top-39*s,10*s,widgets.MUTED)
            for action,label,bx,by,bw,bh in buttons:
                px,py=x+bx*s,top+by*s
                color=widgets.PURPLE if action=='DONE' else widgets.BUTTON
                widgets.rounded(sh,px,py,bw*s,bh*s,5*s,color)
                if action in {'ANGLE','SLIDE'}:
                    f=(1+(self.angle/180 if action=='ANGLE' else self.slide/max(.00001,self.limit)))/2
                    widgets.rounded(sh,px+2*s,py+2*s,(bw-4)*s*f,3*s,s,widgets.CYAN)
                widgets.text(i18n.interface(label),px+bw*s/2,py+(bh/2-4)*s,11*s,align='CENTER')
            feature=op.target or op.hover
            if feature:
                p=location_3d_to_region_2d(op.region,op.area.spaces.active.region_3d,feature.point)
                if p is not None:widgets.disc(sh,p.x,p.y,5*s,widgets.CYAN)


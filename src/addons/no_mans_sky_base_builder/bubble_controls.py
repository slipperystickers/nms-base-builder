"""Persistent, selection-local tube buttons using Blender's native gizmo events.

Drawing never edits scene data or pushes history. Each button targets an ordinary
UNDO operator, so Blender owns click handling, tooltips, and undo boundaries.
"""
import math
from array import array
from functools import lru_cache
from textwrap import wrap

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from bpy_extras.view3d_utils import location_3d_to_region_2d
from mathutils import Matrix, Vector

JUNCTION_ICONS = {
    'TEE': ('T', 'BASE_BUBPIPE_T'), 'CROSS': ('+', 'BASE_BUBPIPE_X'),
    'CORNER3': ('3-way', '_PIPEBUBBLE3CORNER'),
    'CORNER4': ('4-corner', '_PIPEBUBBLE4CORNER'),
    'FIVE': ('5-way', '_PIPEBUBBLESTARHALF'), 'SIX': ('6-way', '_PIPEBUBBLESTAR'),
}

def overlap(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))


def panel_position(bounds, obstacles, viewport, size, gap=36):
    """Choose the nearest clear side; clamp the panel inside the usable view."""
    return _panel_position(tuple(bounds),tuple(map(tuple,obstacles)),tuple(viewport),tuple(size),gap)


@lru_cache(maxsize=32)
def _panel_position(bounds, obstacles, viewport, size, gap):
    left, bottom, right, top = viewport
    width, height = size
    x0, y0, x1, y1 = bounds
    # Include space beyond neighboring pieces, rather than putting the panel
    # over a lower tube merely because the selected elbow is near an edge.
    visible=[b for b in obstacles if overlap(b,viewport)]
    nearby=sorted(visible,key=lambda b:(b[0]+b[2]-x0-x1)**2+(b[1]+b[3]-y0-y1)**2)[:20]
    xs={left,right-width,(x0+x1-width)/2,x1+gap,x0-gap-width}
    ys={bottom,top-height,(y0+y1-height)/2,y1+gap,y0-gap-height}
    for a,b,c,d in nearby:
        xs.update((a-gap-width,c+gap))
        ys.update((b-gap-height,d+gap))
    candidates=((x,y) for x in sorted(xs) for y in sorted(ys))
    choices = []
    for x, y in candidates:
        x = max(left, min(right-width, x))
        y = max(bottom, min(top-height, y))
        rect = (x,y,x+width,y+height)
        # Never choose an overlap with the selected part when a clear side exists.
        score = (overlap(rect,bounds)>0, sum(overlap(rect,b) for b in obstacles),
                 (x+width/2-(x0+x1)/2)**2+(y+height/2-(y0+y1)/2)**2)
        choices.append((score, (x,y)))
    return min(choices, key=lambda item:item[0])[1]



# UI-only positions are keyed by viewport, never by selected object or scene geometry.
_PANEL_ANCHORS = {}


def fixed_panel_position(anchor, bounds, obstacles, viewport, size, reserve=380):
    left, bottom, right, top = viewport
    width, height = size
    if anchor is None:
        reserved = min(max(height, reserve), max(height, top-bottom))
        candidates = ((right-width, top), (left, top),
                      (right-width, bottom+reserved), (left, bottom+reserved))
        def score(candidate):
            x, y = candidate
            rect = (x, y-reserved, x+width, y)
            return (sum(overlap(rect, b) for b in obstacles), overlap(rect, bounds))
        anchor = min(candidates, key=score)
    x = max(left, min(max(left, right-width), anchor[0]))
    top_y = max(bottom+height, min(top, anchor[1])) if height <= top-bottom else top
    return (x, top_y-height), (x, top_y)


def _panel_key(context):
    return context.window.as_pointer(), context.area.as_pointer(), context.region.as_pointer()


def _control_panel_position(context, bounds, obstacles, viewport, size):
    key = _panel_key(context)
    if key not in _PANEL_ANCHORS and len(_PANEL_ANCHORS) >= 64:
        _PANEL_ANCHORS.clear()
    position, anchor = fixed_panel_position(_PANEL_ANCHORS.get(key), bounds, obstacles,
                                           viewport, size, 380*context.preferences.system.ui_scale)
    _PANEL_ANCHORS[key] = anchor
    return position


class BBE_OT_move_tube_controls(bpy.types.Operator):
    bl_idname = 'bbe.move_tube_controls'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'Move Tube Controls'
    bl_description = 'Drag this header to place the tube controls; the panel stays here as you build'
    bl_options = {'INTERNAL', 'BLOCKING'}

    def invoke(self, context, event):
        self._key = _panel_key(context)
        if self._key not in _PANEL_ANCHORS:
            return {'CANCELLED'}
        self._anchor = _PANEL_ANCHORS[self._key]
        self._mouse = (event.mouse_region_x, event.mouse_region_y)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            _PANEL_ANCHORS[self._key] = self._anchor
            context.area.tag_redraw()
            return {'CANCELLED'}
        if event.type == 'MOUSEMOVE':
            _PANEL_ANCHORS[self._key] = (self._anchor[0]+event.mouse_region_x-self._mouse[0],
                                       self._anchor[1]+event.mouse_region_y-self._mouse[1])
            context.area.tag_redraw()
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return {'FINISHED'}
        return {'RUNNING_MODAL'}


def projected_bounds(context, obj):
    points = [location_3d_to_region_2d(context.region, context.region_data,
              obj.matrix_world @ Vector(corner)) for corner in obj.bound_box]
    points = [p for p in points if p is not None]
    if not points:
        return None
    return (min(p.x for p in points), min(p.y for p in points),
            max(p.x for p in points), max(p.y for p in points))


def available_junction(scene, obj, parts, issues):
    """Offer a junction here or at a directly touching visible opening.

    A side contact can create a T on the neighboring piece. It needs no extra
    selection, but an unresolved bend farther down the route is not local.
    """
    from . import bubble_preview as pr
    if pr.editable_opening(scene,obj):
        return None,None
    own = pr.junction_option(scene, obj)
    if own:
        return obj, own
    # A tip aimed at the side of a straight offers a new local branch even
    # though the default straight-preserving export suppresses that contact.
    for part in parts:
        if part != obj:
            option = pr.connection_junction_option(scene, part, obj)
            if option:
                return part, option
    return None, None


class BBE_GT_tube_button(bpy.types.Gizmo):
    bl_idname = 'BBE_GT_tube_button'
    __slots__ = ('text', 'width', 'height', 'font_size', 'lines', 'buttons', '_shader',
                 'image_key', '_textures', '_image_shader')

    def setup(self):
        self.text = ''
        self.lines = ()
        self.buttons = ()
        self.image_key = ''
        self._textures = {}
        self.width, self.height, self.font_size = 100, 26, 12
        self._shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        self._image_shader = gpu.shader.from_builtin('IMAGE')

    def draw(self, context):
        # One surface paints the card and all its buttons in a fixed order.
        # The other gizmos own only native hit-testing/operator dispatch.
        if not self.lines:
            return
        self.draw_rect(context, self)
        x,y = self.matrix_basis.translation[:2]
        for button in self.buttons:
            if button.hide:
                continue
            self.draw_rect(context, button)
            bx,by=button.matrix_basis.translation[:2]
            if button.image_key:
                self.draw_icon(context,button)
            blf.size(0,button.font_size)
            blf.color(0,.94,.95,.97,1)
            tw,th=blf.dimensions(0,button.text)
            blf.position(0,bx+(button.width-tw)/2,by+(5 if button.image_key else (button.height-th)/2),0)
            blf.draw(0,button.text)
        blf.size(0, self.font_size)
        for dx,dy,text,color in self.lines:
            blf.color(0,*color)
            blf.position(0,x+dx,y+dy,0)
            blf.draw(0,text)

    def draw_icon(self, context, button):
        from . import icons
        key=button.image_key
        if key not in self._textures:
            preview=icons.get_asset_icons_pcoll().get(key)
            if preview is None or not preview.image_size[0]:
                return
            w,h=preview.image_size
            values=array('f',[0.0])*(w*h*4)
            preview.image_pixels_float.foreach_get(values)
            self._textures[key]=gpu.types.GPUTexture((w,h),format='RGBA8',
                data=gpu.types.Buffer('FLOAT',len(values),values))
        x,y=button.matrix_basis.translation[:2]
        size=min(button.width-8,button.height-23)
        x+=(button.width-size)/2
        y+=20
        previous=gpu.state.blend_get()
        with gpu.matrix.push_pop(),gpu.matrix.push_pop_projection():
            gpu.matrix.load_matrix(Matrix.Identity(4))
            gpu.matrix.load_projection_matrix(Matrix(((2/context.region.width,0,0,-1),
                (0,2/context.region.height,0,-1),(0,0,-1,0),(0,0,0,1))))
            gpu.state.blend_set('ALPHA')
            self._image_shader.bind()
            self._image_shader.uniform_sampler('image',self._textures[key])
            batch_for_shader(self._image_shader,'TRI_FAN',{
                'pos':((x,y),(x+size,y),(x+size,y+size),(x,y+size)),
                'texCoord':((0,0),(1,0),(1,1),(0,1))}).draw(self._image_shader)
            gpu.state.blend_set(previous)

    def draw_rect(self, context, button):
        x,y=button.matrix_basis.translation[:2]
        vertices=((x,y),(x+button.width,y),(x+button.width,y+button.height),(x,y+button.height))
        color=(*button.color_highlight,button.alpha_highlight) if button.is_highlight else (*button.color,button.alpha)
        previous_blend=gpu.state.blend_get()
        with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
            gpu.matrix.load_matrix(Matrix.Identity(4))
            gpu.matrix.load_projection_matrix(Matrix(((2/context.region.width,0,0,-1),
                (0,2/context.region.height,0,-1),(0,0,-1,0),(0,0,0,1))))
            gpu.state.blend_set('ALPHA')
            self._shader.bind()
            self._shader.uniform_float('color',color)
            batch_for_shader(self._shader,'TRI_FAN',{'pos':vertices}).draw(self._shader)
            gpu.state.blend_set(previous_blend)

    def test_select(self, context, location):
        x,y=self.matrix_basis.translation[:2]
        return 0 if x<=location[0]<=x+self.width and y<=location[1]<=y+self.height else -1


class BBE_GGT_tube_controls(bpy.types.GizmoGroup):
    bl_idname = 'BBE_GGT_tube_controls'
    bl_label = 'Bubble tube controls'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT'}

    @classmethod
    def poll(cls, context):
        from . import bubble_preview as pr, undo_guard
        obj=context.active_object
        return (not undo_guard.restoring and context.mode=='OBJECT'
                and len(context.selected_objects)==1
                and obj is not None and obj.select_get()
                and obj.get('ObjectID')=='BASE_BUBPIPE'
                )

    def setup(self, context):
        self.card=self.gizmos.new('BBE_GT_tube_button')
        self.card.hide_select=True
        self.card.color=(.055,.07,.09);self.card.alpha=.96
        self.grip=self.gizmos.new('BBE_GT_tube_button')
        self.grip.use_tooltip=True
        self.grip.target_set_operator('bbe.move_tube_controls')
        self.buttons=[]
        for label,operator in (('-90°','bbe.turn_bubble_elbow'),('+90°','bbe.turn_bubble_elbow'),
                               ('-5°','bbe.turn_bubble_elbow'),('+5°','bbe.turn_bubble_elbow'),
                               ('More angles…','bbe.bubble_joint_pivot'),
                               ('Use junction','bbe.accept_bubble_junction'),
                               ('Select tube','bbe.select_problem_bubble'),
                               ('Straight','object.nms_asset_browser_object_selected'),
                               ('Elbow','object.nms_asset_browser_object_selected'),
                               ('Draft +','bbe.accept_bubble_junction'),
                               ('Add opening','bbe.choose_bubble_opening'),
                               ('Add opening','bbe.choose_bubble_opening'),
                               ('Change direction','bbe.choose_bubble_opening'),
                               ('Remove opening','bbe.remove_bubble_opening'),
                               ('Previous','bbe.preview_bubble_opening'),
                               ('Next','bbe.preview_bubble_opening'),
                               ('Use direction','bbe.expand_bubble_junction'),
                               ('Cancel','bbe.preview_bubble_opening'),
                               ('+X','bbe.bubble_start_direction'),('-X','bbe.bubble_start_direction'),
                               ('+Y','bbe.bubble_start_direction'),('-Y','bbe.bubble_start_direction'),
                               ('+Z','bbe.bubble_start_direction'),('-Z','bbe.bubble_start_direction')):
            gz=self.gizmos.new('BBE_GT_tube_button')
            gz.text=label;gz.color=(.18,.23,.29);gz.alpha=1
            gz.color_highlight=(.22,.43,.61);gz.alpha_highlight=1
            gz.use_tooltip=True
            props=gz.target_set_operator(operator)
            self.buttons.append((gz,props))
        self.card.buttons=tuple(gz for gz,props in self.buttons)
        for index,key in ((7,'BASE_BUBPIPE'),(8,'BASE_BUBPIPE_L')):
            gz,props=self.buttons[index]
            gz.image_key=key
            props.object_id=key
            props.has_variants=False
        for i,(_,props) in enumerate(self.buttons[:4]):
            props.direction = -1 if i%2==0 else 1
            props.angle=math.pi/2 if i<2 else math.radians(5)
        for (_,props),port in zip(self.buttons[18:], ('Right','Left','Top','Bot','Front','Back')):
            props.port=port

    def draw_directions(self, context, state):
        from . import bubble_preview as pr
        obj=context.active_object
        # Reserve the bounds of every possible opening, so cycling a preview
        # cannot move the buttons around or put them on top of the new arm.
        corners=[obj.matrix_world@Vector((x,1+y,z))
                 for x in (-1.6,1.6) for y in (-1.6,1.6) for z in (-1.6,1.6)]
        points=[location_3d_to_region_2d(context.region,context.region_data,p) for p in corners]
        points=[p for p in points if p is not None]
        if not points:
            return
        bounds=(min(p.x for p in points),min(p.y for p in points),max(p.x for p in points),max(p.y for p in points))
        scale=context.preferences.system.ui_scale;region=context.region
        width,height=330*scale,200*scale
        viewport=[16*scale,24*scale,region.width-100*scale,region.height-60*scale]
        for r in context.area.regions:
            if r.type=='UI' and r.width>1:viewport[2]-=r.width
            if r.type=='TOOLS' and r.width>1:viewport[0]+=r.width
        obstacles=([bounds]+[b for p in pr._native_objects(context.scene) if p!=obj and (b:=projected_bounds(context,p))]
                   if _panel_key(context) not in _PANEL_ANCHORS else ())
        x,y=_control_panel_position(context,bounds,obstacles,viewport,(width,height))
        self.grip.hide=False
        self.grip.matrix_basis=Matrix.Translation((x,y+height-42*scale,0))
        self.grip.width=238*scale;self.grip.height=42*scale
        self.card.hide=False
        self.card.matrix_basis=Matrix.Translation((x,y,0))
        self.card.width=width;self.card.height=height;self.card.font_size=12*scale
        choices=pr.direction_choices(context.scene,obj,state['kind'],state['change'])
        port=state['port'];intent=choices.get(port,'')
        label={'Front':'Forward','Back':'Backward','Top':'Up','Bot':'Down','Left':'Left','Right':'Right'}[port]
        count=list(choices).index(port)+1 if port in choices else 0
        kind=pr.JUNCTION_LABELS.get(intent.split(':')[0],'opening')
        self.card.lines=[(12*scale,height-21*scale,'Choose opening direction',(.94,.95,.97,1)),
                         (12*scale,height-40*scale,obj.name,(.65,.72,.8,1)),
                         (12*scale,height-64*scale,f'{label}  ({count}/{len(choices)}) — {kind}',(.8,.88,.97,1)),
                         (12*scale,67*scale,'Connected openings stay in place.',(.65,.72,.8,1))]
        for i,(dx,dy,bw) in enumerate(((12,113,146),(172,113,146),(12,183,146),(172,183,146)),14):
            gz,props=self.buttons[i]
            gz.hide=False;gz.matrix_basis=Matrix.Translation((x+dx*scale,y+height-dy*scale,0))
            gz.width=bw*scale;gz.height=27*scale;gz.font_size=12*scale
            if i==16:
                gz.hide=port not in choices
                props.obj_name=obj.name;props.kind=state['kind'];props.port=port
                props.change_direction=state['change']
            else:
                props.action={14:'PREV',15:'NEXT',17:'CANCEL'}[i]
                gz.hide=i in (14,15) and len(choices)<2

    def draw_prepare(self, context):
        from . import bubble_preview as pr
        if not self.poll(context):
            for gz in self.gizmos:gz.hide=True
            return
        obj=context.active_object
        bounds=projected_bounds(context,obj)
        region=context.region
        if bounds is None or not overlap(bounds,(0,0,region.width,region.height)):
            for gz in self.gizmos:gz.hide=True
            return
        state=pr.direction_session(context)
        if state:
            for gz in self.gizmos:gz.hide=True
            self.draw_directions(context,state)
            return
        for gz in self.gizmos:gz.hide=False
        for gz,props in self.buttons[12:]:gz.hide=True
        scale=context.preferences.system.ui_scale
        can_turn=pr._active_tube_joint(context) is not None
        can_start=pr.can_set_start_direction(context.scene,obj)
        parts,(_,issues,_)=pr._scene_plan(context.scene)
        own_index=parts.index(obj)
        own_issue=issues.get(own_index)
        problem_index=own_index if own_issue else next(iter(issues),None)
        problem=parts[problem_index] if problem_index is not None else None
        detail=(own_issue or '').partition(': ')[2]
        ready=not issues
        junction,option=available_junction(context.scene,obj,parts,issues)
        opening=pr.editable_opening(context.scene,obj)
        redirects=pr.redirect_options(context.scene,obj) if opening else {}
        redirect_choices=dict(pair for values in redirects.values() for pair in values)
        can_redirect=opening and any(p!=opening[0] for p in redirect_choices)
        if opening:
            junction,option=None,None
        cross_target=junction if option else obj
        cross_option=pr.draft_cross_option(context.scene,cross_target,obj)
        upgrades=pr.expansion_options(context.scene,obj) if not option and not cross_option else {}
        if obj.data.get('bbe_bubble_draft'):
            message=('Finish the new branch: connect a straight, or finish the attached elbow. '
                     'Then you can add another opening.'
                     if len(pr._visible_sockets(obj)) >= 3 else 'Draft bend. Add a tube to its free end.')
        elif own_issue:
            message=detail
        else:
            message='This tube is ready.'
        if option:
            # The icon acts only at this local connection. It is recalculated
            # when the build tip changes or turns, without changing selection.
            action=JUNCTION_ICONS[option[0].split(':')[0]][0]
            message=('Use a '+option[1]+' at '+junction.name+'. '
                     'Click '+action+' to connect here. Your current pipe stays selected.')
        if cross_option:
            message=(f'At {cross_target.name}: choose T to finish this connection, or Draft + to leave a fourth opening.'
                     if option else 'Add a fourth opening with Draft +, then connect another tube.')
        elif not option and problem and problem!=obj:
            reason=issues[problem_index].partition(': ')[2]
            message+=' '+problem.name+': '+reason
        if option and pr.junction_export_issues(context.scene,junction,option[0]):
            message+=' Nearby connections still need checking before export.'
        if upgrades and not own_issue:
            message='Add one opening with a junction icon. Preview its direction before confirming.'
        if opening:
            message=('This opening is unused. Change its direction, or remove it.' if can_redirect else
                     'This opening is unused. Connect a tube here, or remove the opening.')
        if can_start:
            direction={'Right':'+X','Left':'-X','Top':'+Y','Bot':'-Y','Front':'+Z','Back':'-Z'}.get(obj.get(pr._START_KEY))
            message=(f'Start toward local {direction}. Add a straight or elbow to begin.' if direction else
                     'Choose a local starting direction, then add a straight or elbow.')
        lines=wrap(message, width=34, break_long_words=False)
        width=330*scale
        extra=30 if opening else 0
        height=max(157+extra+len(lines)*16+(30 if problem!=obj and problem and not option and not opening else 0),
                   184+84*(bool(option)+bool(cross_option)+len(upgrades)))*scale
        viewport=[16*scale,24*scale,region.width-100*scale,region.height-60*scale]
        for r in context.area.regions:
            if r.type=='UI' and r.width>1:viewport[2]-=r.width
            if r.type=='TOOLS' and r.width>1:viewport[0]+=r.width
        obstacles=([b for p in pr._native_objects(context.scene) if (b:=projected_bounds(context,p))]
                   if _panel_key(context) not in _PANEL_ANCHORS else ())
        x,y=_control_panel_position(context,bounds,obstacles,viewport,(width,height))
        self.grip.hide=False
        self.grip.matrix_basis=Matrix.Translation((x,y+height-42*scale,0))
        self.grip.width=238*scale;self.grip.height=42*scale
        self.card.matrix_basis=Matrix.Translation((x,y,0))
        self.card.width=width;self.card.height=height;self.card.font_size=12*scale
        color=(.62,.86,.70,1) if ready else (1,.72,.32,1)
        self.card.lines=[(12*scale,height-21*scale,'Tube controls',(.94,.95,.97,1)),
                         (12*scale,height-40*scale,obj.name,(.65,.72,.8,1))]
        for i,line in enumerate(lines):
            self.card.lines.append((12*scale,height-(144+extra+i*16)*scale,line,color))
        positions=((12,68,110),(128,68,110),(12,98,110),(128,98,110),(12,128,226))
        for i,(gz,props) in enumerate(self.buttons[:5]):
            dx,dy,bw=positions[i]
            gz.matrix_basis=Matrix.Translation((x+dx*scale,y+height-dy*scale,0))
            gz.width=bw*scale;gz.height=25*scale;gz.font_size=12*scale
            gz.hide=not can_turn
        for i,(gz,props) in enumerate(self.buttons[18:]):
            gz.hide=not can_start
            gz.matrix_basis=Matrix.Translation((x+(12+116*(i%2))*scale,y+height-(68+30*(i//2))*scale,0))
            gz.width=110*scale;gz.height=25*scale;gz.font_size=12*scale
        accept,aprops=self.buttons[5]
        select,sprops=self.buttons[6]
        cross,cprops=self.buttons[9]
        cross.hide=cross_option is None
        if cross_option:
            cross.image_key='BASE_BUBPIPE_X'
            cprops.obj_name=cross_target.name
            cprops.source_name=obj.name
            cprops.draft_cross=True
        accept.hide=option is None
        select.hide=bool(opening) or option is not None or cross_option is not None or problem is None or problem==obj
        if option:
            label,accept.image_key=JUNCTION_ICONS[option[0].split(':')[0]]
            accept.text='Use '+label
            aprops.obj_name=junction.name
            aprops.source_name=obj.name
            aprops.draft_cross=False
        elif problem:
            select.text='Select '+problem.name;sprops.obj_name=problem.name
        select.matrix_basis=Matrix.Translation((x+12*scale,y+10*scale,0))
        select.width=226*scale;select.height=25*scale;select.font_size=12*scale
        icons=[self.buttons[7][0],self.buttons[8][0]]
        if option:icons.append(accept)
        if cross_option:icons.append(cross)
        if opening:
            for index in (12,13):
                gz,props=self.buttons[index]
                gz.hide=index==12 and not can_redirect
                gz.matrix_basis=Matrix.Translation((x+(12 if index==12 else 128)*scale,y+height-158*scale,0))
                gz.width=110*scale;gz.height=25*scale;gz.font_size=11*scale
                props.obj_name=obj.name
                if index==12:
                    props.change_direction=True;props.kind=''
        for index,(gz,props) in enumerate(self.buttons[10:12]):
            gz.hide=index>=len(upgrades)
            if not gz.hide:
                kind=list(upgrades)[index]
                label,gz.image_key=JUNCTION_ICONS[kind]
                gz.text='Add '+label
                props.obj_name=obj.name
                props.kind=kind
                props.change_direction=False
                icons.append(gz)
        for row,gz in enumerate(icons):
            gz.matrix_basis=Matrix.Translation((x+250*scale,y+height-(92+84*row)*scale,0))
            gz.width=68*scale;gz.height=78*scale;gz.font_size=11*scale


def register():
    bpy.utils.register_class(BBE_OT_move_tube_controls)
    bpy.utils.register_class(BBE_GT_tube_button)
    bpy.utils.register_class(BBE_GGT_tube_controls)


def unregister():
    bpy.utils.unregister_class(BBE_GGT_tube_controls)
    bpy.utils.unregister_class(BBE_GT_tube_button)
    bpy.utils.unregister_class(BBE_OT_move_tube_controls)
    _PANEL_ANCHORS.clear()
    _panel_position.cache_clear()

"""FuriousFurby header buttons with explicit, shared drawing/hit-test bounds.

Native transform controls are never wrapped or resized. The small connector
control draws in spare header space; tool menus use their own tool-header row.
No native pointers, cursor warping or inferred mouse-click offsets are used.
"""
from types import SimpleNamespace
import bpy
import blf
import gpu
from . import transform_readout

_records={}
# Blender skips its normal layout while the header shows transform text.
# Capture that text before drawing the last tool row in its usual position.
_pending_layouts={}
_bounds={}
_listeners={}
_handlers=[]
_enabled=False
_hover=None
_scroll={}
_drop_marks={}

def over_header(area, event):
    # Blender can run viewport keymaps beneath its transparent header regions.
    return any(region.type in {'HEADER', 'TOOL_HEADER'} and region.width > 1 and region.height > 1
               and region.x <= event.mouse_x < region.x + region.width
               and region.y <= event.mouse_y < region.y + region.height
               for region in area.regions)

def editable_menu(node):
    from .menu_backend import KEYS
    identifier = node.options.get('identifier')
    if identifier == 'bbe.chat_open':
        return 'chat'
    if identifier == 'bbe.open_menu':
        menu = getattr(node.options['props'], 'menu', None)
        return next((key for key, value in KEYS.items() if value == menu), None)
    return None

def header_target(key, x, y):
    for node, rect in _bounds.get(key, ()):
        if surface().inside(rect, x, y):
            menu = editable_menu(node)
            if menu:
                return menu, x >= rect[0]+rect[2]/2, rect
    return None


def surface():
    from . import menu_surface
    return menu_surface

def record(callback,owner,context):
    m=surface();root=m.Layout()
    callback(SimpleNamespace(layout=root),context)
    area_key=(context.window.as_pointer(),context.area.as_pointer())
    kind=context.region.type
    _pending_layouts[(*area_key,kind)]=root
    if kind=='TOOL_HEADER':
        _records[area_key]=root

def nodes(root):
    result=[]
    def walk(n):
        if n.kind in {'operator','panel','menu','prop'}:result.append(n)
        for child in n.children:walk(child)
    walk(root)
    merged=[]
    for n in result:
        if n.kind=='operator' and getattr(n.options['props'],'from_arrow',False) and merged:
            merged[-1].options['toolbar_arrow']=True
        elif n.options.get('icon') in {'HIDE_ON','HIDE_OFF'} and merged:
            merged[-1].options['eye']=n.options['icon']
        else:merged.append(n)
    controls=[]
    for n in merged:
        controls.append(n)
        if n.options.get('identifier') in {'bbeplus.open_assets','object.nms_launch_asset_browser_window'}:
            root=surface().Layout()
            root.operator(surface().PREFIX+'.asset_strip_toggle',text='',icon='TRIA_DOWN')
            controls.append(root.children[-1])
    return controls

def header_colors(context):
    ui=context.preferences.themes[0].user_interface
    base=(*ui.wcol_pulldown.inner[:3],1)
    selected=(*ui.wcol_pulldown.inner_sel[:3],1)
    text=(*ui.wcol_pulldown.text[:3],1)
    return base,tuple(base[i]*.55+selected[i]*.45 for i in range(4)),text


def header_fill(color):
    # The shared rounded shader linearizes its input for WINDOW surfaces.
    # HEADER regions are already display-space; compensate exactly once.
    return tuple(12.92*v if v<=.0031308 else 1.055*(v**(1/2.4))-.055 for v in color[:3])+(color[3],)


def draw(kind):
    global _bounds
    context=bpy.context
    if not _enabled or not context.area or not context.window:return
    region=context.region;key=(context.window.as_pointer(),context.area.as_pointer(),kind)
    _bounds[key]=[]
    root=_pending_layouts.pop(key,None)
    if kind == 'TOOL_HEADER':
        last_toolbar = _records.get(key[:2])
        relocate = (root is None and last_toolbar is not None and last_toolbar.children
                    and context.space_data.show_region_header and context.space_data.show_region_tool_header)
        if transform_readout.header(context, key, relocate):
            root = last_toolbar
    if root is None:return
    m=surface();s=context.preferences.system.ui_scale
    background,hover,ink=header_colors(context)
    controls=nodes(root)
    if not controls:return
    blf.size(0,11*s)
    widths=[max(25*s,blf.dimensions(0,m.leaf_text(n))[0]+(26 if m.leaf_text(n) else 25)*s+(12*s if n.options.get('toolbar_arrow') else 0)+(19*s if n.options.get('eye') else 0)) for n in controls]
    total=sum(widths)
    right=region.width-(90*s if kind=='TOOL_HEADER' else 0)
    navigation=[];left_limit=0
    if kind=='TOOL_HEADER':
        # Leave Blender's native active-tool controls on the left. On narrow
        # windows the row scrolls horizontally; it never changes native layout.
        # Reserve the native Options button on the right: native UI handlers
        # consume clicks before keymaps, so overlays must never cover it.
        start=max(300*s,(region.width-total)/2);left_limit=300*s
        overflow=max(0,start+total-right+8*s)
        if overflow:
            left_limit=324*s;right-=24*s;start=max(left_limit,(region.width-total)/2)
            overflow=max(0,start+total-right+8*s)
            offset=min(overflow,max(0,_scroll.get(key,0)));_scroll[key]=offset
            if offset>0:navigation.append((-1,300*s))
            if offset<overflow:navigation.append((1,right))
            start-=offset
    else:
        # This is an overlay: adding it cannot affect Blender's flex spacers.
        start=region.width/2+150*s
        if start+total>region.width-330*s:
            # Compact widths retain the target and closed/open eye; no overlap
            # with the native orientation/pivot or viewport shading controls.
            start=region.width/2+120*s
            for n in controls:n.options['compact_header']=True
            widths=[46*s for n in controls];total=sum(widths)
        if start+total>region.width-270*s:return
    shader=gpu.shader.from_builtin('UNIFORM_COLOR');x=start
    for direction,nav_x in navigation:
        nav=m.Layout();props=nav.operator(HeaderScroll.bl_idname,text='Earlier menus' if direction<0 else 'More menus');props.direction=direction
        n=nav.children[-1];h=min(23*s,region.height-2*s);y=(region.height-h)/2;w=24*s
        _bounds[key].append((n,(region.x+nav_x,region.y+y,w,h)))
        hot=_hover==(key,HeaderScroll.bl_idname,nav_x)
        m.paint.rounded(shader,nav_x,y,w,h,3*s,header_fill(hover if hot else background))
        cx=nav_x+w/2;cy=y+h/2;color=ink
        m.paint.line(shader,(cx-direction*2*s,cy+4*s),(cx+direction*2*s,cy),1.3*s,color)
        m.paint.line(shader,(cx+direction*2*s,cy),(cx-direction*2*s,cy-4*s),1.3*s,color)
    for n,w in zip(controls,widths):
        h=min(23*s,region.height-2*s);y=(region.height-h)/2
        rect=(x,y,w,h);absolute=(region.x+x,region.y+y,w,h)
        if x>=left_limit and x+w<=right:
            _bounds[key].append((n,absolute))
            hot=_hover==(key,n.options.get('identifier'),x)
            m.paint.rounded(shader,x,y,w,h,3*s,header_fill(hover if hot else background))
            o=n.options;icon=o.get('icon_value',0)
            if o.get('icon')=='CURVE_BEZCURVE' or (n.kind=='operator' and getattr(o['props'],'menu','')=='CURVES'):icon=m.outline_icon('spline',tint=(.75,.65,1))
            if icon:m.draw_image(icon,x+4*s,y+(h-16*s)/2,16*s,16*s)
            if not o.get('compact_header'):
                m.paint.text(m.leaf_text(n),x+23*s,y+h/2-4*s,11*s,ink)
            if o.get('identifier','').endswith('.asset_strip_toggle'):
                from . import asset_strip
                state=asset_strip._states.get(key[:2],{})
                direction=1 if state.get('enabled') else -1
                cx=x+w/2;cy=y+h/2
                m.paint.line(shader,(cx-4*s,cy-direction*2*s),(cx,cy+direction*2*s),1.2*s,ink)
                m.paint.line(shader,(cx,cy+direction*2*s),(cx+4*s,cy-direction*2*s),1.2*s,ink)
            if o.get('toolbar_arrow'):
                cx=x+w-7*s;cy=y+h/2
                m.paint.line(shader,(cx-3*s,cy+1*s),(cx,cy-2*s),s,ink)
                m.paint.line(shader,(cx,cy-2*s),(cx+3*s,cy+1*s),s,ink)
            if o.get('eye'):
                cx=x+w-11*s;cy=y+h/2;color=ink
                # Closed eyelid when connectors are hidden; open eye otherwise.
                closed=o['eye']=='HIDE_ON'
                points=[(cx-6*s,cy),(cx-3*s,cy-3*s),(cx+3*s,cy-3*s),(cx+6*s,cy)]
                for a,b in zip(points,points[1:]):m.paint.line(shader,a,b,1.2*s,color)
                if closed:
                    for dx in (-4,0,4):m.paint.line(shader,(cx+dx*s,cy-2*s),(cx+(dx+1)*s,cy-5*s),s,color)
                else:
                    for a,b in zip([(cx-6*s,cy),(cx-3*s,cy+3*s),(cx+3*s,cy+3*s),(cx+6*s,cy)],[(cx-3*s,cy+3*s),(cx+3*s,cy+3*s),(cx+6*s,cy)]):m.paint.line(shader,a,b,1.2*s,color)
                    m.paint.disc(shader,cx,cy,2*s,color)
        x+=w
    mark = _drop_marks.get(key)
    if mark:
        edge = mark - region.x
        m.paint.line(shader, (edge,2*s), (edge,region.height-2*s), 2*s, ink)

def dispatch(window,area,node,rect):
    m=surface();region=next((r for r in area.regions if r.type=='WINDOW'),None)
    if not region:return
    o=node.options
    def run():
        if window not in bpy.context.window_manager.windows[:] or area not in window.screen.areas[:]:return
        with bpy.context.temp_override(window=window,area=area,region=region):
            if node.kind=='operator':
                kwargs=vars(o['props']).copy();identifier=o['identifier']
                if identifier==m.PREFIX+'.open_menu':
                    current=m._sessions.get(area.as_pointer())
                    if current and (current.stack[0][0] if current.stack else current.menu)==kwargs['menu']:
                        current.finish();return
                    kwargs.pop('from_arrow',None)
                    kwargs.update(anchor_x=round(rect[0]+rect[2]/2),anchor_y=round(rect[1]-3),anchor_center=True)
                    identifier=m.PREFIX+'.custom_menu'
                op=m.operation(identifier)
                if op.poll():op('INVOKE_DEFAULT',**kwargs)
            elif node.kind in {'panel','menu'}:
                m.operation(m.PREFIX+'.custom_menu')('INVOKE_DEFAULT',menu=('PANEL:' if node.kind=='panel' else 'MENU:')+o['identifier'],anchor_x=round(rect[0]+rect[2]/2),anchor_y=round(rect[1]-3),anchor_center=True)
            elif node.kind=='prop' and o['data'].bl_rna.properties[o['key']].type=='BOOLEAN':setattr(o['data'],o['key'],not getattr(o['data'],o['key']))
    bpy.app.timers.register(run,first_interval=.01)

class HeaderEvents(bpy.types.Operator):
    bl_idname=('bbeplus' if __package__.endswith('bbe_plus') else 'bbe')+'.header_events'
    bl_label='Builder Header Input'
    bl_options={'INTERNAL'}
    @classmethod
    def poll(cls,context):
        return (_enabled and context.area and context.area.type=='VIEW_3D'
                and context.region and context.region.type in {'HEADER','TOOL_HEADER'})
    def invoke(self,context,event):
        global _hover
        self.window=context.window;self.key=self.window.as_pointer()
        if event.type not in {'LEFTMOUSE','MOUSEMOVE','WHEELUPMOUSE','WHEELDOWNMOUSE'}:return {'PASS_THROUGH'}
        # Retain menu geometry for the asset strip, but let Blender handle
        # confirmation, cancellation and snapping while the transform is live.
        if (self.key, context.area.as_pointer()) in transform_readout._readouts:
            return {'PASS_THROUGH'}
        hit=None
        for area in self.window.screen.areas:
            for kind in ('HEADER','TOOL_HEADER'):
                key=(self.key,area.as_pointer(),kind)
                for node,rect in _bounds.get(key,[]):
                    if surface().inside(rect,event.mouse_x,event.mouse_y):hit=(area,key,node,rect);break
        if event.type=='MOUSEMOVE':
            new=(hit[1],hit[2].options.get('identifier'),hit[3][0]-next(r.x for r in hit[0].regions if r.type==hit[1][2])) if hit else None
            if new!=_hover:
                _hover=new
                for area in self.window.screen.areas:
                    if area.type=='VIEW_3D':area.tag_redraw()
        if hit and event.type=='LEFTMOUSE' and event.value=='PRESS':
            area, key, node, rect = hit
            source = editable_menu(node)
            if source and key[2] == 'TOOL_HEADER':
                self.source = source
                self.header_key = key
                self.start_x, self.start_y = event.mouse_x, event.mouse_y
                self.origin_button = (area, node, rect)
                self.dragging = False
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
            dispatch(self.window,area,node,rect);return {'FINISHED'}
        if hit and event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE'} and hit[1][2]=='TOOL_HEADER':
            _scroll[hit[1]]=max(0,_scroll.get(hit[1],0)+(80 if event.type=='WHEELDOWNMOUSE' else -80))
            hit[0].tag_redraw();return {'FINISHED'}
        return {'PASS_THROUGH'}

    def modal(self, context, event):
        area, node, rect = self.origin_button
        key = self.header_key
        if event.type in {'WINDOW_DEACTIVATE', 'ESC', 'RIGHTMOUSE'}:
            self.cancel(context)
            return {'CANCELLED'}
        if event.type not in {'MOUSEMOVE', 'LEFTMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        x, y = event.mouse_x, event.mouse_y
        threshold = max(4, context.preferences.inputs.drag_threshold_mouse)*context.preferences.system.ui_scale
        if max(abs(x-self.start_x), abs(y-self.start_y)) > threshold:
            self.dragging = True
        target = header_target(key, x, y)
        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self.cancel(context)
            if self.dragging:
                if target and target[0] != self.source:
                    bpy.ops.bbe.toolbar_menu(action='MOVE', surface='TOP', menu=self.source,
                                             target=target[0], after=target[1])
            elif surface().inside(rect, x, y):
                dispatch(self.window, area, node, rect)
            return {'FINISHED'}
        if self.dragging:
            if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
                _scroll[key] = max(0, _scroll.get(key,0)+(80 if event.type=='WHEELDOWNMOUSE' else -80))
            if target and target[0] != self.source:
                bounds = target[2]
                _drop_marks[key] = bounds[0] + (bounds[2] if target[1] else 0)
            else:
                _drop_marks.pop(key, None)
            area.tag_redraw()
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        _drop_marks.pop(self.header_key, None)
        self.origin_button[0].tag_redraw()

HeaderEvents.__name__=('BBEPLUS' if __package__.endswith('bbe_plus') else 'BBE')+'_OT_header_events'

class HeaderScroll(bpy.types.Operator):
    bl_idname=('bbeplus' if __package__.endswith('bbe_plus') else 'bbe')+'.scroll_header'
    bl_label='Scroll Builder Menus'
    bl_options={'INTERNAL'}
    direction:bpy.props.IntProperty(default=1)
    def execute(self,context):
        key=(context.window.as_pointer(),context.area.as_pointer(),'TOOL_HEADER')
        _scroll[key]=max(0,_scroll.get(key,0)+self.direction*160)
        context.area.tag_redraw()
        return {'FINISHED'}
HeaderScroll.__name__=('BBEPLUS' if __package__.endswith('bbe_plus') else 'BBE')+'_OT_scroll_header'


_keymaps=[]

def register():
    global _enabled
    _enabled=True;bpy.utils.register_class(HeaderEvents);bpy.utils.register_class(HeaderScroll)
    for kind in ('HEADER','TOOL_HEADER'):_handlers.append((bpy.types.SpaceView3D.draw_handler_add(draw,(kind,),kind,'POST_PIXEL'),kind))
    _handlers.append((bpy.types.SpaceView3D.draw_handler_add(transform_readout.draw,(),'WINDOW','POST_PIXEL'),'WINDOW'))
    bpy.app.handlers.load_pre.append(transform_readout.clear)
    config=bpy.context.window_manager.keyconfigs.addon
    if config:
        # Header View2D consumes wheel input before the general Screen map.
        # Poll limits these entries to our VIEW_3D header regions; a miss passes
        # through to Blender, so native controls retain their own scrolling.
        for map_name,events in (('Screen',('LEFTMOUSE','MOUSEMOVE','WHEELUPMOUSE','WHEELDOWNMOUSE')),('View2D',('WHEELUPMOUSE','WHEELDOWNMOUSE'))):
            keymap=config.keymaps.new(name=map_name,space_type='EMPTY',region_type='WINDOW')
            for event in events:
                item=keymap.keymap_items.new(HeaderEvents.bl_idname,event,'ANY' if event=='MOUSEMOVE' else 'PRESS',head=True)
                _keymaps.append((keymap,item))

def unregister():
    global _enabled,_hover
    _enabled=False;_bounds.clear();_records.clear();_pending_layouts.clear();_scroll.clear();_drop_marks.clear();_hover=None
    bpy.app.handlers.load_pre.remove(transform_readout.clear)
    transform_readout.clear()
    for keymap,item in _keymaps:keymap.keymap_items.remove(item)
    _keymaps.clear()
    for handler,kind in _handlers:bpy.types.SpaceView3D.draw_handler_remove(handler,kind)
    _handlers.clear();bpy.utils.unregister_class(HeaderEvents);bpy.utils.unregister_class(HeaderScroll)

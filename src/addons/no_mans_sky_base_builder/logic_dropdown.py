"""Compact Logic dropdown with explicit ownership of dismissal and tool handoff.

FuriousFurby implementation. Native persistent popovers cannot dismiss individual
buttons; this keeps the same arrangement but releases the menu before placement.
"""
import time
import bpy
import blf
import gpu
from . import curve_widgets as ui, i18n, styled_ui as art
from pathlib import Path

_sessions=[]
KINDS=[('POWER','Electrical Wire','U_POWERLINE'),('TELEPORT','Teleport Wire','U_PORTALLINE'),('BYTEBEAT','Byte-Beat Cable','U_BYTEBEATLINE'),('SUPPLY','Supply Pipe','U_PIPELINE')]

class BBE_OT_logic_dropdown(bpy.types.Operator):
    bl_idname='bbe.logic_dropdown'
    bl_label='Logic'
    bl_description='Choose a cable type, place cables, or manage connections and logic parts'
    bl_options={'INTERNAL','BLOCKING'}
    anchor_x:bpy.props.IntProperty(default=-1,options={'SKIP_SAVE'})
    anchor_y:bpy.props.IntProperty(default=-1,options={'SKIP_SAVE'})
    def invoke(self,context,event):
        for menu in list(_sessions):menu.close()
        self.window=context.window;self.area=context.area;self.workspace=context.workspace
        self.region=next((r for r in self.area.regions if r.type=='WINDOW'),None)
        if not self.region:return {'CANCELLED'}
        self.scene=context.scene;self.scale=max(.65,context.preferences.system.ui_scale*.88)
        self.width=460*self.scale;self.height=344*self.scale
        sidebar=next((r.width for r in self.area.regions if r.type=='UI'),0) if self.area.spaces.active.show_region_ui else 0
        available=self.region.width-sidebar
        self.x=max(4,min((self.anchor_x if self.anchor_x>=0 else event.mouse_x)-self.region.x-50*self.scale,available-self.width-4))
        self.top=min(self.region.height-4,(self.anchor_y if self.anchor_y>=0 else event.mouse_y)-self.region.y-8*self.scale)
        self.top=max(self.height+4,self.top)
        self.dropdown=False;self.hover=None;self.mouse=(0,0);self.since=time.monotonic();self.closed=False
        self.handle=bpy.types.SpaceView3D.draw_handler_add(self.draw_canvas,(),'WINDOW','POST_PIXEL')
        self.timer=context.window_manager.event_timer_add(.15,window=self.window)
        _sessions.append(self);context.window_manager.modal_handler_add(self);self.area.tag_redraw()
        return {'RUNNING_MODAL'}
    def close(self):
        if self.closed:return
        self.closed=True
        bpy.types.SpaceView3D.draw_handler_remove(self.handle,'WINDOW')
        bpy.context.window_manager.event_timer_remove(self.timer)
        if self in _sessions:_sessions.remove(self)
        try:self.area.tag_redraw()
        except ReferenceError:pass
    def elements(self):
        result=[('help',426,12,22,24,'?',True),
                ('kind',88,54,360,30,dict((k,n) for k,n,_ in KINDS).get(self.scene.nms_main.line_switch,'Electrical Wire'),True),
                ('place',12,91,436,31,'Place Cables',True),
                ('point',12,155,214,30,'New Point',self.scene.nms_main.line_switch!='TELEPORT'),
                ('connect',234,155,214,30,'Connect',True),
                ('divide',12,189,214,30,'Divide',self.scene.nms_main.line_switch!='TELEPORT'),
                ('disconnect',234,189,214,30,'Disconnect',True),
                ('repair',12,226,436,28,'Repair Selected SRT Connections',True)]
        for index,(key,label) in enumerate([('button','BTN'),('wall_switch','SWITCH'),('prox_switch','PROX'),('inv_switch','INV'),('auto_switch','AUTO'),('floor_switch','FLOOR'),('beat_switch','BEAT')]):
            result.append(('logic_'+key,12+index*62.3,281,58,52,label,True))
        if self.dropdown:
            for index,(key,label,_) in enumerate(KINDS):result.append(('kind_'+key,88,85+index*30,360,30,label,True))
        return result
    def bounds(self,item):
        _,x,y,w,h,*_=item;s=self.scale
        return self.x+x*s,self.top-(y+h)*s,w*s,h*s
    def pick(self,x,y):
        for item in reversed(self.elements()):
            bx,by,w,h=self.bounds(item)
            if bx<=x<=bx+w and by<=y<=by+h:return item
        return None
    def label(self,x,y,text,size=12,color=None):
        blf.size(0,size*self.scale);blf.color(0,*(color or ui.TEXT));blf.position(0,x,y,0);blf.draw(0,i18n.interface(text))
    def draw_canvas(self):
        if self.closed or bpy.context.area!=self.area:return
        s=self.scale
        parts=dict(zip(['button','wall_switch','prox_switch','inv_switch','auto_switch','floor_switch','beat_switch'],['U_SWITCHBUTTON','U_SWITCHWALL','U_SWITCHPROX','U_TRANSISTOR1','U_TRANSISTOR2','U_SWITCHPRESS','BYTEBEATSWITCH']))
        symbols={'point':'git-branch-plus','connect':'link','divide':'git-fork','disconnect':'unlink','repair':'refresh-cw','place':'cable','help':'circle-help'}
        with ui.canvas(bpy.context):
            shader=gpu.shader.from_builtin('UNIFORM_COLOR')
            art.panel(shader,self.x,self.top-self.height,self.width,self.height,s)
            ui.rounded(shader,self.x+12*s,self.top-39*s,29*s,29*s,8*s,art.SURFACE)
            art.image(art.icon('cable'),self.x+17*s,self.top-34*s,19*s,19*s)
            self.label(self.x+50*s,self.top-30*s,'Logic',15,art.TEXT)
            ui.line(shader,(self.x+12*s,self.top-45*s),(self.x+self.width-12*s,self.top-45*s),s,art.EDGE)
            self.label(self.x+15*s,self.top-74*s,'Cable',13,art.MUTED)
            self.label(self.x+15*s,self.top-146*s,'OPERATIONS',11,art.MUTED)
            self.label(self.x+15*s,self.top-274*s,'LOGIC COMPONENTS',11,art.MUTED)
            for item in self.elements():
                key,_,_,_,_,label,enabled=item;x,y,w,h=self.bounds(item);hot=self.hover==key and enabled
                text=art.TEXT if enabled else art.MUTED
                if key=='place':art.gradient_box(x,y,w,h,7*s,art.HOVER if hot else art.PRIMARY,(.388,.267,.620,1))
                elif key=='kind' or key.startswith('kind_'):
                    ui.rounded(shader,x,y,w,h,6*s,art.EDGE if key=='kind' else art.SURFACE)
                    ui.rounded(shader,x+s,y+s,w-2*s,h-2*s,5*s,art.HOVER if hot else art.INK)
                elif hot or key.startswith('logic_'):ui.rounded(shader,x,y,w,h,7*s,art.HOVER if hot else art.SURFACE)
                if key.startswith('logic_'):
                    thumb=art.preview(Path(__file__).parent/'images/asset_icons'/(parts[key[6:]]+'.png'))
                    art.image(thumb,x+(w-32*s)/2,y+17*s,32*s,32*s)
                    blf.size(0,10*s);tw,_=blf.dimensions(0,label);self.label(x+(w-tw)/2,y+4*s,label,10,text)
                elif key=='help':art.image(art.icon('circle-help'),x,y+4*s,19*s,19*s)
                else:
                    if key in symbols:
                        art.image(art.icon(symbols[key]),x+7*s,y+(h-18*s)/2,18*s,18*s)
                        tx=x+32*s
                    else:tx=x+9*s
                    self.label(tx,y+h/2-4*s,label,13,text)
                    if key=='kind':art.image(art.icon('chevron-down'),x+w-23*s,y+7*s,16*s,16*s)
            if self.hover and not self.dropdown and time.monotonic()-self.since>.8:
                tips={'place':'Next click places the first point. Esc / right-click finishes.',
                      'point':'Start a free point or branch from a compatible cable.',
                      'connect':'Choose Chain or Fan, then select the supply starting point.',
                      'divide':'Insert branch points along a selected cable.',
                      'disconnect':'Disconnect the selected cable connections.',
                      'repair':'Repair selected short-range teleporter links.'}
                tip=tips.get(self.hover)
                if tip:
                    size=11*s;tw=min(self.width-20*s,blf.dimensions(0,tip)[0]+18*s)
                    tx=max(6,min(self.mouse[0]+12*s,self.region.width-tw-6));ty=max(6,self.mouse[1]-35*s)
                    ui.rounded(shader,tx,ty,tw,26*s,6*s,art.SURFACE)
                    self.label(tx+8*s,ty+8*s,art.trim(tip,tw-16*s,size),11,art.TEXT)
    def dispatch(self,key,event):
        kind=dict((k,p) for k,_,p in KINDS)[self.scene.nms_main.line_switch]
        actions={'point':'object.nms_point','connect':'object.nms_connect','divide':'object.nms_divide','disconnect':'object.nms_split','repair':'bbe.repair_srt_connections','help':'bbe.function_help'}
        operator='object.nms_logic_'+key[6:] if key.startswith('logic_') else actions.get(key)
        self.close()
        window,area,region=self.window,self.area,self.region
        x,y=event.mouse_x,event.mouse_y
        def run():
            if window not in bpy.context.window_manager.windows[:] or area not in window.screen.areas[:]:return
            with bpy.context.temp_override(window=window,area=area,region=region):
                if key=='place':bpy.ops.bbe.start_cable_connection('INVOKE_DEFAULT',kind=kind,repeat_placement=True,launch_x=x,launch_y=y,launch_ready=True)
                elif operator:
                    namespace,name=operator.split('.')
                    getattr(getattr(bpy.ops,namespace),name)('INVOKE_DEFAULT',**({'topic':'LOGIC'} if key=='help' else {}))
        bpy.app.timers.register(run,first_interval=.02)
        return {'FINISHED'}
    def modal(self,context,event):
        if self.closed:return {'FINISHED'}
        if context.workspace!=self.workspace or context.scene!=self.scene:self.close();return {'CANCELLED'}
        if event.type in {'ESC','RIGHTMOUSE'} and event.value=='PRESS':
            if self.dropdown:self.dropdown=False;self.area.tag_redraw();return {'RUNNING_MODAL'}
            self.close();return {'CANCELLED'}
        if event.type=='MOUSEMOVE':
            self.mouse=(event.mouse_x-self.region.x,event.mouse_y-self.region.y)
            hit=self.pick(*self.mouse);hover=hit[0] if hit else None
            if hover!=self.hover:self.hover=hover;self.since=time.monotonic()
            self.area.tag_redraw()
            # Let native header buttons clear their hover and tooltip state.
            return {'PASS_THROUGH'}
        if event.type=='LEFTMOUSE' and event.value=='PRESS':
            hit=self.pick(event.mouse_x-self.region.x,event.mouse_y-self.region.y)
            if hit is None:
                self.close();return {'CANCELLED'}
            key=hit[0]
            if not hit[-1]:return {'RUNNING_MODAL'}
            if key=='kind':self.dropdown=not self.dropdown
            elif key.startswith('kind_'):self.scene.nms_main.line_switch=key[5:];self.dropdown=False
            elif self.dropdown:self.dropdown=False
            else:return self.dispatch(key,event)
            self.area.tag_redraw()
        if event.type=='TIMER':self.area.tag_redraw()
        return {'RUNNING_MODAL'}

class BBE_OT_open_logic_menu(bpy.types.Operator):
    bl_idname='bbe.open_logic_menu'
    bl_label='Logic'
    bl_description='Cable placement, connections and logic components'
    bl_options={'INTERNAL'}
    def invoke(self,context,event):
        window,area=context.window,context.area
        region=next((r for r in area.regions if r.type=='WINDOW'),None)
        x,y=event.mouse_x,event.mouse_y
        def run():
            if window not in bpy.context.window_manager.windows[:] or area not in window.screen.areas[:]:return
            with bpy.context.temp_override(window=window,area=area,region=region):
                bpy.ops.bbe.logic_dropdown('INVOKE_DEFAULT',anchor_x=x,anchor_y=y)
        bpy.app.timers.register(run,first_interval=.01)
        return {'FINISHED'}

class BBE_OT_open_tools_panel(bpy.types.Operator):
    bl_idname='bbe.open_tools_panel'
    bl_label='Prefabs'
    bl_options={'INTERNAL'}
    def invoke(self,context,event):
        bpy.ops.wm.call_panel('INVOKE_DEFAULT',name='VIEW3D_PT_bbe_toolbar_parts',keep_open=False)
        return {'FINISHED'}

@bpy.app.handlers.persistent
def cancel_all(*_):
    for menu in list(_sessions):menu.close()
def register():
    bpy.utils.register_class(BBE_OT_logic_dropdown)
    bpy.utils.register_class(BBE_OT_open_logic_menu)
    bpy.utils.register_class(BBE_OT_open_tools_panel)
    if cancel_all not in bpy.app.handlers.load_pre:bpy.app.handlers.load_pre.append(cancel_all)
def unregister():
    cancel_all()
    if cancel_all in bpy.app.handlers.load_pre:bpy.app.handlers.load_pre.remove(cancel_all)
    bpy.utils.unregister_class(BBE_OT_open_tools_panel)
    bpy.utils.unregister_class(BBE_OT_open_logic_menu)
    bpy.utils.unregister_class(BBE_OT_logic_dropdown)
    art.clear()

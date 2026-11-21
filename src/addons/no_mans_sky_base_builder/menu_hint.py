"""Small one-time workspace customization hint, authored for FuriousFurby builders."""
import bpy
import time
import blf
import gpu
from gpu_extras.batch import batch_for_shader
from bpy.app.handlers import persistent

_sessions=[]

def preferences(context):
    item=context.preferences.addons.get(__package__)
    return item.preferences if item else None

class MenuHint(bpy.types.Operator):
    bl_idname='bbe.menu_hint'
    bl_label='Customize your menus'
    bl_options={'INTERNAL'}
    def invoke(self,context,event):
        if context.area.type!='VIEW_3D':return {'CANCELLED'}
        if bpy.app.driver_namespace.get('bbe_menu_hint_active'):return {'CANCELLED'}
        bpy.app.driver_namespace['bbe_menu_hint_active']=True
        self.state={'area':context.area,'active':True,'shown':time.monotonic()}
        self.state['handler']=bpy.types.SpaceView3D.draw_handler_add(draw_overlay,(self.state,),'WINDOW','POST_PIXEL')
        _sessions.append(self.state);context.window_manager.modal_handler_add(self);context.area.tag_redraw()
        return {'RUNNING_MODAL'}
    def finish(self):
        remove_hint(self.state)
    def modal(self,context,event):
        if not self.state.get('active'):return {'CANCELLED'}
        if event.type in {'LEFTMOUSE','RIGHTMOUSE','MIDDLEMOUSE','ESC'} and event.value=='PRESS' and time.monotonic()-self.state['shown'] > 1.0:
            self.finish();p=preferences(context)
            if p:
                setattr(p,'bbe_menu_guide_seen',True)
                setattr(p,'bbe_menu_guide_version',3)
            for addon in context.preferences.addons:
                for field in ('menu_guide_version','bbe_menu_guide_version'):
                    if hasattr(addon.preferences,field):setattr(addon.preferences,field,3)
            if bpy.ops.wm.save_userpref.poll():bpy.ops.wm.save_userpref()
            return {'FINISHED','PASS_THROUGH'}
        return {'PASS_THROUGH'}

def remove_hint(state):
    if state.get('active'):
        state['active']=False
        bpy.app.driver_namespace.pop('bbe_menu_hint_active',None)
        bpy.types.SpaceView3D.draw_handler_remove(state.pop('handler'),'WINDOW')
        try:state['area'].tag_redraw()
        except ReferenceError:pass
    if state in _sessions:_sessions.remove(state)

def draw_overlay(state):
    if not state['active'] or bpy.context.area!=state['area']:return
    s=bpy.context.preferences.system.ui_scale
    region=bpy.context.region
    # Blender can overlay both headers and the sidebar inside the WINDOW region.
    # Anchor to their visible edges, not the full region's covered pixels.
    top=float(region.height);right=float(region.width)
    for other in bpy.context.area.regions:
        if other.height>1 and other.type in {'HEADER','TOOL_HEADER'} and other.y>region.y+region.height/2:
            top=min(top,float(other.y-region.y))
        if other.width>1 and other.type=='UI' and other.x>region.x+region.width/2:
            right=min(right,float(other.x-region.x))
    w=min(385*s,max(80,right-20));x=max(10,right-w-12);y=max(8,top-90*s)
    shader=gpu.shader.from_builtin('UNIFORM_COLOR');shader.bind();shader.uniform_float('color',(.06,.035,.10,.96))
    old=gpu.state.blend_get();gpu.state.blend_set('ALPHA')
    try:
        batch_for_shader(shader,'TRIS',{'pos':[(x,y),(x+w,y),(x+w,y+78*s),(x,y),(x+w,y+78*s),(x,y+78*s)]}).draw(shader)
        lines=[('Make room for the tools you use',13),('Workspace Settings: choose Top Bar or Sidebar.',11),('Show hidden tools and arrange each list separately.',11),('Click anywhere to dismiss.',10)]
        for i,(line,size) in enumerate(lines):
            blf.size(0,size*s)
            while blf.dimensions(0,line)[0]>w-20*s and size>7:size-=.5;blf.size(0,size*s)
            blf.color(0,.94,.90,1,1);blf.position(0,x+10*s,y+(58-16*i)*s,0);blf.draw(0,line)
    finally:gpu.state.blend_set(old)

_attempted=False

def maybe_show():
    global _attempted
    if bpy.app.background or _attempted or bpy.app.driver_namespace.get('bbe_menu_hint_active'):return
    p=preferences(bpy.context)
    if not p or getattr(p,'bbe_menu_guide_version',0)>=3:return
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type=='VIEW_3D':
                region=next((r for r in area.regions if r.type=='WINDOW'),None)
                if region:
                    _attempted=True
                    with bpy.context.temp_override(window=win,area=area,region=region):
                        getattr(getattr(bpy.ops,'bbe.menu_hint'.split('.')[0]),'bbe.menu_hint'.split('.')[1])('INVOKE_DEFAULT')
                    return

@persistent
def cancel(*args):
    for state in list(_sessions):remove_hint(state)

def register():
    global _attempted
    _attempted=False
    bpy.utils.register_class(MenuHint)
    for handlers in (bpy.app.handlers.load_pre,bpy.app.handlers.undo_pre,bpy.app.handlers.redo_pre):handlers.append(cancel)

def unregister():
    cancel()
    for handlers in (bpy.app.handlers.load_pre,bpy.app.handlers.undo_pre,bpy.app.handlers.redo_pre):
        if cancel in handlers:handlers.remove(cancel)
    bpy.utils.unregister_class(MenuHint)

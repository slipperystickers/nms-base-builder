import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import module
chat=module('bbe_chat'); menu=module('tools_menu.base_builder_menu')

class Layout:
    def __init__(self):self.calls=[]
    def separator_spacer(self):pass
    def row(self,**kw):return self
    def operator(self,name,**kw):
        props=SimpleNamespace();self.calls.append(('operator',name,kw,props));return props
    def popover(self,**kw):self.calls.append(('popover',kw['panel'],kw,None))

for enabled in (False,True):
    chat._chat_enabled=enabled
    chat._toolbar_status={'preview':'Builder: '+'long received message '*6,'unread':2,'online':7}
    layout=Layout();menu.draw_toolbar(SimpleNamespace(layout=layout),bpy.context)
    controls=[c for c in layout.calls if c[1] in ('bbe.chat_open','VIEW3D_PT_bbe_chat')]
    assert len(controls)==1,controls
    assert layout.calls[-1][1]=='VIEW3D_PT_bbe_toolbar_settings'
    control=controls[0]
    assert control[2]['icon_value']>=0  # Background Blender has no GPU icon IDs.
    if enabled:
        assert control[0]=='operator' and control[3].view=='TOOLBAR'
        assert '…' in control[2]['text'] and control[2]['text'].endswith('▾')
    else:
        assert control[0]=='popover' and control[2]['text']=='Chat'
    assert not any(c[2].get('icon')=='COMMUNITY' for c in layout.calls)
chat._chat_enabled=True
for count in (None,0,1,7,10,99,100,500,-1,'3',True):
    chat._toolbar_status={'online':count}
    expected=count if type(count) is int and count>=0 else None
    assert chat._online_count()==expected
    icon=chat._chat_icon()
    assert icon>=0 and chat._chat_icon()==icon
assert len(chat._badge_previews)==8
original=menu.toolbar_state
for unread_dm in (0, 1):
    chat._toolbar_status={'preview':'Builder: Latest response','unread':unread_dm,'directed':unread_dm,'online':1}
    for tick in (100,101):
        with patch.object(chat.time,'monotonic',return_value=tick):
            layout=Layout();chat.draw_native_toolbar(layout,bpy.context)
            assert layout.alert == (bool(unread_dm) and tick==100)
menu.toolbar_state=lambda context:([i[0] for i in menu.TOOLBAR_ITEMS],{'chat'})
layout=Layout();menu.draw_toolbar(SimpleNamespace(layout=layout),bpy.context)
assert not any(c[1] in ('bbe.chat_open','VIEW3D_PT_bbe_chat') for c in layout.calls)
menu.toolbar_state=original
window=SimpleNamespace(width=1000,height=800)
area=SimpleNamespace(regions=[SimpleNamespace(type='TOOL_HEADER',height=25,y=735)])
anchor=chat._dropdown_anchor(SimpleNamespace(window=window,area=area),SimpleNamespace(mouse_x=700))
assert anchor['x']==.7 and anchor['bottom']==65/800
chat.unregister()
assert chat._badge_previews is None
chat.register()  # Leave the parent add-on registered consistently for shutdown.
print('SINGLE_CHAT_TOOLBAR_PASS',bpy.app.version_string,flush=True)

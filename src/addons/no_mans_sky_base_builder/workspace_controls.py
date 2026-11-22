"""FuriousFurby workspace controls: central connector pill and stable panel order."""
from pathlib import Path
from types import SimpleNamespace
import bpy
import bpy.utils.previews

_previews = None

class VisibilityButton(bpy.types.Operator):
    bl_idname = 'bbe.connector_visibility'
    bl_label = 'Connector Visibility'
    bl_description = 'Show or hide connectors. Cable placement temporarily reveals its targets and preserves this choice'
    bl_options = {'INTERNAL'}
    def execute(self, context):
        field = 'bbe_show_connectors'
        setattr(context.scene, field, not getattr(context.scene, field))
        return {'FINISHED'}

VisibilityButton.__name__ = 'bbe_OT_connector_visibility'

def draw_connectors(layout, scene, field, brand):
    global _previews
    if _previews is None:
        _previews = bpy.utils.previews.new()
        for state in ('on','off'):
            _previews.load(state,str(Path(__file__).parent/'images'/('connector-target-'+state+'.png')),'IMAGE')
    on = bool(getattr(scene,field))
    row=layout.row(align=True)
    row.operator('bbe.connector_visibility',text='Hide connectors' if on else 'Show connectors',icon_value=_previews['on' if on else 'off'].icon_id)
    row.operator('bbe.connector_visibility',text='',icon='HIDE_OFF' if on else 'HIDE_ON')


def attach_header(callback):
    """Draw beside the native transform group without changing its layout."""
    bpy.utils.register_class(VisibilityButton)
    from . import toolbar_surface
    def record_header(owner, context):
        toolbar_surface.record(callback, owner, context)
    bpy.types.VIEW3D_HT_header.append(record_header)
    def detach():
        global _previews
        bpy.types.VIEW3D_HT_header.remove(record_header)
        if 'bl_rna' in VisibilityButton.__dict__:bpy.utils.unregister_class(VisibilityButton)
        if _previews is not None:
            bpy.utils.previews.remove(_previews)
            _previews = None
    return detach

def _panel_types():
    pending=list(bpy.types.Panel.__subclasses__());seen=set()
    while pending:
        cls=pending.pop()
        if cls in seen:continue
        seen.add(cls);pending.extend(cls.__subclasses__())
        if 'bl_rna' in cls.__dict__:yield cls

def order_panels(panels, ranks, key_for):
    """Refresh native panel identities when order changes; Blender caches old ranks."""
    import hashlib
    import sys
    classes = [c for c in panels if key_for(c) in ranks and not getattr(c,'bl_parent_id','')]
    children = [c for c in _panel_types() if getattr(c,'bl_parent_id','') in {p.bl_idname for p in classes}]
    registered = [c for c in classes if 'bl_rna' in c.__dict__]
    signature = hashlib.sha1(repr(sorted(ranks.items())).encode()).hexdigest()[:8]
    ids = {}
    for cls in classes:
        base = cls.__dict__.get('workspace_base_id', cls.bl_idname)
        cls.workspace_base_id = base
        ids[cls.bl_idname] = base + '_' + signature
        cls.workspace_panel_order = ranks[key_for(cls)]
    if all(cls.bl_idname == ids[cls.bl_idname] for cls in classes):
        return
    # Sidebar Manager must first release its native registration wrappers.
    manager = next((m for m in tuple(sys.modules.values()) if m and callable(getattr(m,'refresh_panel_order',None)) and getattr(m,'_enabled',False)),None)
    if manager:
        manager.rebuild(restore=True)
        manager._originals.clear()
    for cls in reversed(children):bpy.utils.unregister_class(cls)
    for cls in reversed(registered):bpy.utils.unregister_class(cls)
    for cls in classes:
        cls.bl_idname = ids[cls.bl_idname]
        cls.bl_order = cls.workspace_panel_order
    for cls in children:
        cls.bl_parent_id = ids[cls.bl_parent_id]
    for cls in sorted(registered,key=lambda c:c.bl_order):bpy.utils.register_class(cls)
    for cls in children:bpy.utils.register_class(cls)
    if manager:manager.refresh_panel_order(classes)

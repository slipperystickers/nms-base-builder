"""Copy/Paste button operators must enumerate grouped/multi-linked parts once."""
import json
import sys
from collections import Counter
from pathlib import Path

import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import addon,module
Group=module('group').Group
ctx=bpy.context
old_clipboard=ctx.window_manager.clipboard


def signature(rows):
    return Counter((r['ObjectID'],tuple(round(float(v),4) for v in r['Position']),r.get('UserData',0)) for r in rows)



def exercise():
    try:
        rows=[dict(ObjectID='^W_FLOOR',Position=[i*2,0,0],Up=[0,1,0],At=[0,0,1],UserData=0,Timestamp=0) for i in range(1000)]
        rows[1]['Position']=rows[0]['Position'][:]  # Two intentional coincident objects must remain two.
        expected=signature(rows)
        ctx.window_manager.clipboard=json.dumps(rows)
        yield 0.10  # Allow the OS clipboard owner to process window messages.
        assert bpy.ops.object.nms_import_nms_data()=={'FINISHED'}
        yield 0.10  # Allow the OS clipboard owner to process window messages.
        parts=sorted((o for o in ctx.scene.objects if o.get('ObjectID')),key=lambda o:o.get('order',0))
        assert len(parts)==1000
        first=Group.group_objects(parts[:100])
        second=Group.group_objects(parts[100:200])
        nested=Group.group_objects([first,second],flatten_groups=True)
        assert nested is not None
        # Real Blender parenting and multiple collection links do not create more
        # game objects, even when both a parent and its children are selected.
        parent=bpy.data.objects.new('Clipboard hierarchy parent',None)
        ctx.scene.collection.objects.link(parent)
        for obj in parts[200:250]:
            world=obj.matrix_world.copy();obj.parent=parent;obj.matrix_world=world
        for name in ('Extra link A','Extra link B'):
            col=bpy.data.collections.new(name);ctx.scene.collection.children.link(col)
            col.objects.link(nested)
            for obj in parts[200:230]:col.objects.link(obj)
        bpy.ops.object.select_all(action='SELECT')
        ctx.view_layer.objects.active=parent
        ctx.view_layer.update()
        for repeat in range(3):
            assert bpy.ops.object.nms_export_nms_data_objects()=={'FINISHED'}
            yield 0.10  # Allow the OS clipboard owner to process window messages.
            copied=json.loads(ctx.window_manager.clipboard)
            assert len(copied)==1000,(repeat,len(copied))
            assert signature(copied)==expected
            assert bpy.ops.object.nms_import_nms_data()=={'FINISHED'}
            yield 0.10  # Allow the OS clipboard owner to process window messages.
        assert bpy.ops.object.nms_export_nms_data_objects()=={'FINISHED'}
        yield 0.10  # Allow the OS clipboard owner to process window messages.
        assert signature(json.loads(ctx.window_manager.clipboard))==expected
        print('PASS BBE actual Copy/Paste operators: 1000 parts, nested groups, multi-collection links, parent+child selection, intentional overlaps; no duplicate records',flush=True)
    finally:
        ctx.window_manager.clipboard=old_clipboard
        yield 0.10  # Allow the OS clipboard owner to process window messages.

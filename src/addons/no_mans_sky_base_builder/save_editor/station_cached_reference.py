"""Append ready-made cutaways and shared exterior instances without rebuilding meshes."""
import json
import bpy


def cleanup_geometry():
    """Release only orphaned instance collections owned by the station reference."""
    unused={c for c in bpy.data.collections if c.get('station_geometry_backend') and c.users==0}
    objects={o for c in unused for o in c.objects}
    meshes={o.data for o in objects if o.type=='MESH'}
    if unused:bpy.data.batch_remove(ids=unused)
    orphaned={o for o in objects if o.users==0}
    if orphaned:bpy.data.batch_remove(ids=orphaned)
    orphaned_meshes={m for m in meshes if m.users==0}
    if orphaned_meshes:bpy.data.batch_remove(ids=orphaned_meshes)


def assemble(context,choices,visibility=None):
    from . import station_reference as ref
    from .station_outliner import capture
    previous=capture(context)
    state=visibility if isinstance(visibility,dict) else previous
    roots=[c for c in context.scene.collection.children if c.get(ref.TAG)]
    sections={o.get('station_section',o.name):(o.hide_get(),o.hide_render)
              for c in roots for o in c.all_objects if not o.get('station_part_key')}
    root=None
    try:
        with bpy.data.libraries.load(str(ref.ASSETS/'station_reference.blend'),link=False) as (source,target):
            if 'Station Reference' not in source.collections:
                raise ValueError('The prebuilt station reference is missing from the installed library')
            target.collections=['Station Reference']
        root=target.collections[0]
        if root is None:raise ValueError('Could not load the prebuilt station reference')
        context.scene.collection.children.link(root)
        from .station_surfaces import attach
        meshes = set()
        for obj in root.all_objects:
            if obj.type == 'MESH':
                meshes.add(obj.data)
            if obj.instance_collection:
                meshes.update(child.data for child in obj.instance_collection.objects if child.type == 'MESH')
        attach(meshes, ref.ASSETS / 'station_surfaces.blend')
        # Appended objects need view-layer bases before their eye state can be set.
        context.view_layer.update()
        outside=next(c for c in root.children if c.get('station_collection_label')=='Outside')
        inside=next(c for c in root.children if c.get('station_collection_label')=='Inside')
        for obj in list(root.all_objects):
            key=obj.get('station_part_key')
            default=obj.get('station_default_hidden',False)
            hidden=state.get('objects',{}).get(key,default) if key else sections.get(obj['station_section'],(default,False))[0]
            obj.hide_set(hidden)
            obj.hide_render=hidden if key else sections.get(obj['station_section'],(default,obj.get('station_default_render_hidden',False)))[1]
        root['appearance_choices']=json.dumps(choices)
        root['appearance_source']='Manual Outliner visibility; procedural seed not decoded'
        root['reference_version']=5
        # Validate the replacement before removing the previous reference.
        if len(root.all_objects)!=86 or len(outside.children)!=6 or len(inside.objects)!=6:
            raise ValueError('The prebuilt station reference has an unexpected layout')
        for old in roots:ref.remove_tree(old)
        root.name='Station Reference';outside.name='Outside';inside.name='Inside'
        for family in outside.children:family.name=family['station_label']
        for obj in list(root.all_objects):obj.name=obj['station_section']
        context.view_layer.update()
        layer=next(c for c in context.view_layer.layer_collection.children if c.collection==root)
        outside_layer=next(c for c in layer.children if c.collection==outside)
        outside_layer.hide_viewport=state.get('outsideHidden',True)
        selected_family=choices.get(ref.catalog()['familyGroup'],'_Type_Tet')
        for family in outside_layer.children:
            key=family.collection['station_family']
            hidden=state.get('families',{}).get(key,key!=selected_family)
            family.hide_viewport=hidden;family.collection.hide_render=hidden
        from .station_tree_view import schedule
        schedule(context,root)
        return root
    except Exception:
        if root:ref.remove_tree(root)
        cleanup_geometry()
        raise

"""Regular BBE bindings. Tools remain in their existing implementation."""
import bpy
import bpy.utils.previews
from types import SimpleNamespace
from . import i18n,menu_contract
_icons=bpy.utils.previews.new()
KEYS={'proxies':'HOME','recovery':'RECOVERY','io':'IO','transforms':'TRANSFORM','color':'COLOR','builder':'BUILDER','transform':'CURVES','shapes':'SHAPES','batch':'BATCH','parts':'PREFABS','cables':'LOGIC','lighting':'LIGHTING','chat':'CHAT'}
TOOLS=[(v,{'HOME':'BBE','IO':'I/O','CURVES':'Curve Tools'}.get(v,v.title()),'') for v in KEYS.values()]

def enum_items(data,key,context):
    for cls in type(data).__mro__:
        prop=vars(cls).get('__annotations__',{}).get(key)
        options=getattr(prop,'keywords',{})
        items=options.get('items')
        if callable(items):return [(str(v[0]),i18n.interface(v[1]),v[2]) for v in items(data,context) if v and v[0]]
    return [(v.identifier,i18n.interface(v.name),v.description) for v in data.bl_rna.properties[key].enum_items if v.identifier]

def definition(root,layout,key,context):
    from .tools_menu import base_builder_menu as toolbar
    if key in {'SHAPES','NEW_SHAPE'}:
        from . import shapes
        shapes.draw(layout,context,guided=key=='NEW_SHAPE')
        return style(root,'SHAPES')
    if key == 'WORKSPACE':
        from . import WorkspaceSettings
        WorkspaceSettings.draw(SimpleNamespace(layout=root), context)
        return style(root, key)
    if key.startswith(('PANEL:','MENU:')):
        family,name=key.split(':',1)
        cls=(bpy.types.Panel if family=='PANEL' else bpy.types.Menu).bl_rna_get_subclass_py(name)
    elif key=='SETTINGS':cls=toolbar.VIEW3D_PT_bbe_toolbar_settings
    else:
        native=next(k for k,v in KEYS.items() if v==key)
        cls=bpy.types.Panel.bl_rna_get_subclass_py(toolbar._ITEMS[native][2])
    if cls is None:raise ValueError('Menu unavailable: '+key)
    owner=SimpleNamespace(layout=layout)
    if hasattr(cls,'toolbar_group'):owner.toolbar_group=cls.toolbar_group
    cls.draw(owner,context)
    return style(root,key)

def style(root,key):
    def walk(n):
        yield n
        for c in n.children:yield from walk(c)
    nodes=list(walk(root))
    helper=next((n for n in nodes if n.kind=='operator' and n.options.get('identifier')=='bbe.function_help'),None)
    if helper and key not in {'IO', 'WORKSPACE'}:
        helper.parent.children.remove(helper);root.header_help=helper
    def detach(n):
        if n.parent and n in n.parent.children:n.parent.children.remove(n)
    def move(n,parent):
        n.enabled=n.is_enabled();n.operator_context=n.inherited('operator_context','INVOKE_DEFAULT')
        detach(n);n.parent=parent;parent.children.append(n);return n
    def label(parent,text):
        n=parent.label(text=i18n.interface(text));n.options['section']=True;return n
    if key in {'WORKSPACE', 'SETTINGS'}:
        for node in nodes:
            o = node.options
            if node.kind == 'box':
                node.options['top_rule'] = True
            if node.kind == 'label' and o.get('text') in (i18n.interface('Top bar menus'), i18n.interface('Sidebar menus')):
                o['section'] = True
            if node.kind == 'label' and o.get('text') == i18n.interface('Show/hide with the checkbox. Use arrows to reorder.'):
                o['text'] = i18n.interface('Drag a menu name to reorder. Use its switch to show or hide it.')
            if o.get('identifier') == 'bbe.toolbar_menu':
                action = o['props'].action
                if action == 'TOGGLE':
                    caption = node.parent.children[1]
                    caption.kind = 'menu_grip'
                    caption.options.update(menu=o['props'].menu, surface=o['props'].surface,
                                           height=25, tip=i18n.interface('Drag to reorder'))
                    node.parent.children[:2] = [caption, node]
                    o.update(text='', switch=True, icon='NONE', width=30, height=25,
                             depress=o.get('icon') == 'CHECKBOX_HLT',
                             tip=i18n.interface('Show / hide') + ' ' + caption.options['text'])
                elif action in {'UP', 'DOWN'}:
                    o.update(arrow='▴' if action == 'UP' else '▾', width=28, height=25,
                             tip=i18n.interface('Move up' if action == 'UP' else 'Move down'))
                else:
                    o['outline'] = 'refresh-cw'
            if o.get('identifier') == 'wm.save_userpref':
                o.update(primary=True, outline='save')
            if o.get('identifier') == 'bbe.cutaway_controls':
                o['outline'] = 'scan-line'
    if key=='PANEL:VIEW3D_PT_bbe_shape_part_picker':
        for n in nodes:
            if n.kind=='operator':n.options['outline']='pipette'
    if key=='BUILDER':
        # The approved BBE+ arrangement, bound only to regular BBE operations.
        from . import part_counts
        from .utils.asset_browser_utils import auto_snap_enabled
        result=type(root)();result.header_help=helper;result.operator_context='INVOKE_DEFAULT'
        def action(parent,identifier,text,art,**props):
            op=parent.operator(identifier,text=i18n.interface(text));n=parent.children[-1];n.options['outline']=art
            for k,v in props.items():setattr(op,k,v)
            return n
        result.header_count=str(part_counts.displayed(bpy.context.scene))
        columns=result.row();columns.options.update(factor=.54,gap=12,decor='columns')
        left=columns.column();right=columns.column()
        label(left,'Duplication')
        action(left,'object.nms_duplicate','Duplicate','copy')
        action(left,'bbe.duplicate_edge_path','Duplicate Along Edge Path','spline')
        action(left,'bbe.duplicate_axis','Duplicate Along Axis','layers')
        label(left,'Common Tools')
        row=left.row()
        action(row,'bbe.swap_corvette_cockpits','Cockpit / Object order','arrow-left-right')
        action(row,'bbe.function_help','','circle-help',topic='COCKPIT')
        action(left,'bbe.repair_bubble_tubes','Repair Bubble Tubes','refresh-cw')
        action(left,'bbe.align_geometry','Align','magnet')
        action(left,'object.nms_delete','Delete','trash-2')
        label(left,'Grouping');row=left.row();row.options['equal']=True
        action(row,'object.nms_group_objects','Group','group');action(row,'object.nms_ungroup_objects','Ungroup','ungroup')
        label(left,'Orientation');row=left.row();row.options['equal']=True
        action(row,'object.nms_mirror','Mirror','flip-horizontal-2');action(row,'object.nms_flip','Flip','flip-vertical-2')
        action(right,'bbe.toggle_auto_snap','Auto-Snap','magnet').options.update(switch=True,depress=auto_snap_enabled())
        snap_defaults=dict(prev_target=False,next_target=False,prev_source=False,next_source=False)
        action(right,'object.nms_snap','Snap','magnet',**snap_defaults).options['primary']=True
        for side in ('target','source'):
            row=right.row();row.options['factor']=.58;row.label(text=i18n.interface(side.title()))
            arrows=row.row();arrows.options['equal']=True
            for direction,symbol in [('prev','‹'),('next','›')]:
                action(arrows,'object.nms_snap','','',**(snap_defaults|{direction+'_'+side:True})).options.update(arrow=symbol)
        tool=bpy.context.scene.nms_build_tool
        label(right,'Mirror across');right.row().prop(tool,'mirror_direction',expand=True)
        right.prop(tool,'center_of_reflection',text='Pivot');right.prop(tool,'check_auto_duplicate',text='Auto duplicate')
        action(right,'object.nms_advanced_mirror','Mirror across '+tool.mirror_direction,'flip-horizontal-2')
        root=result;nodes=list(walk(root))
    elif key=='RECOVERY':
        for n in nodes:
            if n.kind=='label' and n.options.get('text') in {i18n.interface('Project Recovery'),i18n.interface('Manual only')}:
                detach(n)
        retention=next((n for n in nodes if n.kind=='label' and n.options.get('text')==i18n.interface('Keeps the last 3 recovery saves')),None)
        if retention:
            detach(retention)
            status=next((n for n in nodes if n.kind=='label' and n.parent and n in n.parent.children),None)
            if status:
                lines = (status.options['text'], i18n.interface('Last 3 copies retained'))
                status.options.update(text=' · '.join(lines), recovery_status_lines=lines)
        mode=next(n for n in nodes if n.kind=='prop' and n.options['key']=='bbe_recovery_mode')
        mode.options['text']=i18n.interface('Back up')
        if len(mode.parent.children)>1:mode.parent.options['factor']=.67
        else:mode.parent.options.pop('factor',None)
        for n in nodes:
            ident=n.options.get('identifier','')
            if ident=='bbe.recovery_now':n.options.update(outline='save',primary=True,left_align=True)
            if ident=='bbe.open_backup_root':n.options.update(text=i18n.interface('Backup Folder'),outline='folder-open')
            if ident=='bbe.backup_settings':n.options.update(text=i18n.interface('Change Folder'),outline='folder-cog')
            if n.kind=='menu':n.options.update(text=i18n.interface('Open Recovery'),outline='folder-clock')
            if n.kind=='row' and len(n.children)==2 and all(c.kind in {'operator','menu'} for c in n.children):n.options['equal']=True
    elif key=='BATCH':
        for n in nodes:
            if n.kind=='label' and n.options.get('text')==i18n.interface('Select objects with'):n.options['text']=i18n.interface('Select Matching')
            if n.kind=='label' and n.options.get('text') in {i18n.interface('Select Matching'),i18n.interface('Selection Tools')}:n.options['section']=True
            if n.kind=='label' and n.options.get('text')==i18n.interface('Batch Replace'):detach(n)
            if n.options.get('identifier')=='object.nms_select_all_same_colors':detach(n)
            if n.kind=='row' and len(n.children)==2 and all(c.kind=='box' for c in n.children):n.options.update(gap=12,factor=.52,decor='columns')
            if n.options.get('identifier')=='object.nms_batch_replace_target':n.options.update(primary=True,top_rule=True)
    elif key=='COLOR':
        picker=next((n for n in nodes if n.kind=='prop' and n.options['key']=='color_picker'),None)
        if picker:
            grid=picker.parent.parent
            row=grid.parent.row();move(picker,row);picker.options['text']=i18n.interface('Pick Colour')
    elif key=='CURVES':
        for n in nodes:
            if n.kind=='prop' and n.options['key']=='bbe_curve_plane':n.parent.options['factor']=.67
            if n.options.get('identifier')=='bbe.curve_add':
                # Preserve BBE's artwork size; only arrange the eight choices
                # into the same two rows as BBE+.
                n.parent.kind='grid';n.parent.options.update(columns=8,decor='tiles')
    for n in nodes:
        if key=='SHAPES':
            if n.kind=='grid':n.options.update(decor='tiles',columns=4)
            if n.kind=='enum_value':n.options['center']=True
            if n.options.get('identifier')=='bbe.start_shape':
                from .shape_layout import LABELS
                n.options.update(tile=True,text=i18n.interface(LABELS[n.options['props'].kind]))
            if n.options.get('identifier')=='bbe.shape_build':n.options.update(primary=True,outline='layers')
        if key=='PREFABS' and n.options.get('identifier')=='bbe.prefab_catalogue_open':
            n.options.update(font_size=15, primary=True)
        if key=='PREFABS' and n.kind=='row' and len(n.children)==2 and all(c.kind=='operator' for c in n.children):n.options['equal']=True
        if key=='PREFABS' and n.kind=='label' and n.options.get('text')=='Prefabs':
            n.parent.children.remove(n);continue
        ident=n.options.get('identifier','')
        text=n.options.get('text','')
        if n.kind=='row' and n.children and all(c.kind=='enum_value' for c in n.children):n.options.update(decor='segments',equal=True)
        if n.kind=='grid' and key=='COLOR':n.options.update(columns=8,gap=7)
        if ident=='bbe.start_cable_connection':n.options.update(primary=True,outline='cable')
        if key=='LOGIC' and ident.startswith('object.nms_logic_'):
            from pathlib import Path
            parts={'button':('BTN','U_SWITCHBUTTON'),'wall_switch':('SWITCH','U_SWITCHWALL'),'prox_switch':('PROX','U_SWITCHPROX'),'inv_switch':('INV','U_TRANSISTOR1'),'auto_switch':('AUTO','U_TRANSISTOR2'),'floor_switch':('FLOOR','U_SWITCHPRESS'),'beat_switch':('BEAT','BYTEBEATSWITCH')}
            text,part=parts[ident.removeprefix('object.nms_logic_')]
            if part not in _icons:_icons.load(part,str(Path(__file__).parent/'images/asset_icons'/(part+'.png')),'IMAGE')
            n.options.update(tile=True,text=text,icon_value=_icons[part].icon_id)
        if key=='CURVES' and ident=='bbe.curve_add':
            from .curve_shapes import SHAPES
            kind=getattr(n.options['props'],'kind','')
            n.options.update(shape_tile=True,text=i18n.interface(next((title for value,title,_ in SHAPES if value==kind),kind)))
        if n.kind=='label' and key=='LOGIC' and text=='Logic':n.options['text']='Logic Components'
        if key=='LOGIC':
            art={'object.nms_point':'git-branch-plus','object.nms_connect':'link','object.nms_divide':'git-fork','object.nms_split':'unlink','bbe.repair_srt_connections':'refresh-cw'}
            if ident in art:n.options['outline']=art[ident]
            if n.kind=='row' and len(n.children)==2 and all(c.kind in {'operator','row'} for c in n.children):n.options['equal']=True
        if key == 'COLOR' and ident == 'bbe.choose_material_finish':
            n.options.update(material_finish=True, width=36, height=34,
                             tip=n.options['props'].palette.partition(' - ')[2])
            n.parent.options['gap'] = 3
        if key=='COLOR' and ident=='object.nms_apply_colour':n.options['swatch']=True
        if key=='CURVES' and n.kind=='grid':n.options.update(columns=8,decor='tiles')
        if key=='CURVES':
            art={'bbe.curve_draw':'pencil-line','bbe.curve_from_surface':'scan-line','bbe.connect_curve_endpoints':'link','object.nms_duplicate_along_curve':'copy-plus'}
            if ident in art:n.options['outline']=art[ident]
            if ident=='object.nms_duplicate_along_curve':n.options.update(primary=True,text=i18n.interface('Duplicate Along Curve'))
        if n.kind=='gap':n.options['factor']=.35
        if n.kind=='operator' and ident=='bbe.function_help':n.options.update(outline='circle-help',text='')
        if n.kind=='operator' and text in {'Place Cables','Back Up Now','Snap','Duplicate Along Curve','Optimize & Export to Save'}:n.options['primary']=True
    def prune(n):
        for c in list(n.children):
            prune(c)
            if c.kind in {'row','column','box','grid'} and not c.children:n.children.remove(c)
    prune(root)
    return menu_contract.decorate(root)

def cleanup():
    global _icons
    if _icons is not None:bpy.utils.previews.remove(_icons);_icons=None

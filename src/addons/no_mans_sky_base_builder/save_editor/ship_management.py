"""Ship Management: isolated save draft and a draggable inventory grid."""
from ..furby_errors import report_error
import copy
import json
import math
import textwrap
from pathlib import Path
import bpy
import blf
import gpu
from bpy.app.handlers import persistent
from gpu_extras.batch import batch_for_shader
from . import ship_core as core, ship_inventory as catalog, ship_files, ship_repair
from .save_editor_utils import BaseType

SESSION = None
ATLAS = None
HANDLER = None
FRAME = None
MANAGER_WINDOW = None
SOURCE_WINDOW = None
ACTIVE_UI = None


def restore_source_window(session):
    """Put the building scene back if an older temporary window changed it."""
    if not session or SOURCE_WINDOW is None:
        return
    try:
        source = session.get('source_scene')
        if source and any(w == SOURCE_WINDOW for w in bpy.context.window_manager.windows):
            if SOURCE_WINDOW.scene != source:
                SOURCE_WINDOW.scene = source
    except ReferenceError:
        pass


def repair_orphaned_preview_windows():
    """Recover a main window left on the empty preview by an older build."""
    wm = bpy.context.window_manager
    if wm is None:
        return None
    for window in wm.windows:
        if MANAGER_WINDOW is not None and window == MANAGER_WINDOW:
            continue
        preview = window.scene
        if preview and preview.name.startswith('BBE Ship Management Preview'):
            source_name = preview.get('bbe_ship_management_source_scene')
            source = bpy.data.scenes.get(source_name) if source_name else None
            if source and source != preview:
                window.scene = source
    return None


@persistent
def repair_after_load(_):
    bpy.app.timers.register(repair_orphaned_preview_windows, first_interval=.1)


def state():
    if SESSION is None:
        raise ValueError('Open Ship Management first')
    return SESSION


def current_inventory():
    s=state()
    return core.inventory(s['root'],s['context'],s['index'],s['container'])


def store_inventory(inv):
    s=state();core.set_inventory(s['root'],s['context'],s['index'],s['container'],inv);s['dirty']=True
    refresh_status(s)


def refresh_status(s):
    s['link_issues'] = core.inspect_links(s['root'])
    s['slot_issues'] = {ctx: ship_repair.inspect_slots(s['root'], ctx)[0]
                        for ctx in core.contexts(s['root'])}


def pending_repair(s):
    return any(p['context'] == s['context'] for p in s.get('repairs', []))


def at(inv,pos):
    return next((i for i in inv.get('Slots',[]) if i['Index']==dict(X=pos[0],Y=pos[1])),None)


def redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type=='VIEW_3D':area.tag_redraw()


def finish_dialog():
    if SESSION: SESSION['busy']=False
    redraw()


class Dialog:
    def cancel(self,context):finish_dialog()
    def fail(self,exc):
        report_error(self, {'ERROR'},str(exc));finish_dialog();return {'CANCELLED'}


class BBE_OT_ship_class(Dialog,bpy.types.Operator):
    bl_idname='bbe.ship_class';bl_label='Ship Class'
    ship_class:bpy.props.EnumProperty(name='Class',items=[(v,v+' class','') for v in ('C','B','A','S')])
    def invoke(self,context,event):
        s=state();ship=core.ships(s['root'],s['context'])[s['index']]
        if not core.occupied(ship):return self.fail(ValueError('Select an owned ship'))
        self.ship_class=core.get(core.get(core.get(ship,'Inventory',{}),'Class',{}),'InventoryClass','C')
        return context.window_manager.invoke_props_dialog(self,width=440)
    def draw(self,context):
        self.layout.prop(self,'ship_class',expand=True)
        self.layout.label(text='Changes ship class; preserves existing rolled base stats.')
        self.layout.label(text='Inventory, technology and hyperslots are kept.')
    def execute(self,context):
        try:
            s=state();draft=copy.deepcopy(s['root']);core.set_class(draft,s['context'],s['index'],self.ship_class);s['root']=draft;s['dirty']=True
        except Exception as exc:return self.fail(exc)
        finish_dialog();return {'FINISHED'}


class BBE_PG_ship_stat(bpy.types.PropertyGroup):
    stat_id:bpy.props.StringProperty()
    value:bpy.props.FloatProperty(precision=4)


class BBE_OT_ship_stats(Dialog,bpy.types.Operator):
    bl_idname='bbe.ship_stats';bl_label='Edit Ship Stats'
    bl_description='Edit saved base ship stats in this draft; the game calculates final technology bonuses'
    values:bpy.props.CollectionProperty(type=BBE_PG_ship_stat)
    def invoke(self,context,event):
        s=state();ship=core.ships(s['root'],s['context'])[s['index']]
        if not core.occupied(ship):return self.fail(ValueError('Select an owned ship'))
        self.values.clear()
        stats=core.get(core.get(ship,'Inventory',{}),'BaseStatValues',[])
        if not stats:return self.fail(ValueError('This ship has no saved base stats'))
        for stat in stats:
            row=self.values.add()
            row.stat_id=str(core.get(stat,'BaseStatID',''))
            row.value=float(core.get(stat,'Value',0))
        s['busy']=True
        return context.window_manager.invoke_props_dialog(self,width=460,confirm_text='Apply to Draft')
    def draw(self,context):
        for row in self.values:
            name=row.stat_id.lstrip('^').replace('SHIP_','').replace('_',' ').title()
            self.layout.prop(row,'value',text=name)
        self.layout.label(text='These are saved base rolls; technology bonuses are calculated in game.')
    def execute(self,context):
        try:
            s=state();draft=copy.deepcopy(s['root'])
            ship=core.ships(draft,s['context'])[s['index']]
            stats=core.get(core.get(ship,'Inventory',{}),'BaseStatValues',[])
            if len(stats)!=len(self.values):raise ValueError('Ship stats changed while editing')
            changed=False
            for stat,row in zip(stats,self.values):
                if str(core.get(stat,'BaseStatID',''))!=row.stat_id:raise ValueError('Ship stat order changed while editing')
                value=float(row.value)
                if not math.isfinite(value):raise ValueError('Ship stats must be finite numbers')
                if value!=float(core.get(stat,'Value',0)):
                    core.put(stat,'Value',value);changed=True
            if changed:s['root']=draft;s['dirty']=True
        except Exception as exc:return self.fail(exc)
        finish_dialog();return {'FINISHED'}


class BBE_OT_ship_add(Dialog,bpy.types.Operator):
    bl_idname='bbe.ship_add';bl_label='Add Minimal Corvette'
    ship_name:bpy.props.StringProperty(name='Name',default='New Corvette',maxlen=80)
    def invoke(self,context,event):
        return context.window_manager.invoke_props_dialog(self,width=430)
    def draw(self,context):
        self.layout.label(text='Create an S-class starter Corvette in the selected EMPTY slot.')
        self.layout.prop(self,'ship_name')
        self.layout.label(text='Staged until Save Changes. Then export your Blender build to it.')
    def execute(self,context):
        try:
            s=state();draft=copy.deepcopy(s['root']);core.add_minimal(draft,s['context'],s['index'],self.ship_name);s['root']=draft;s['dirty']=True
        except Exception as exc:return self.fail(exc)
        finish_dialog();return {'FINISHED'}


def roll_choices(self,context):
    s=SESSION
    values=[('KEEP','Current roll','Keep the number shown below')]
    if s:
        item=at(current_inventory(),s['selected'])
        if item:
            values += [(v,'#'+v,'Existing roll for this exact upgrade in this save') for v in catalog.known_rolls(s['root'],item['Id'])]
    # Keep strings alive for Blender's dynamic enum.
    BBE_OT_ship_item._choices=values
    return values


class BBE_OT_ship_item(Dialog,bpy.types.Operator):
    bl_idname='bbe.ship_item';bl_label='Edit Inventory Item'
    bl_description='Edit this item quantity or procedural roll, or remove the selected item from the draft'
    action:bpy.props.EnumProperty(items=[('EDIT','Edit',''),('REMOVE','Remove','')])
    amount:bpy.props.IntProperty(name='Quantity / charge',min=-1,max=2147483647)
    roll:bpy.props.StringProperty(name='Procedural roll',description='Decimal RNG suffix after #. Changing it rerolls the upgrade; stats are calculated by the game')
    existing:bpy.props.EnumProperty(name='Reuse existing roll',items=roll_choices)
    def invoke(self,context,event):
        state()['busy']=True
        item=at(current_inventory(),state()['selected'])
        if not item:return self.fail(ValueError('Select an item first'))
        self.amount=item['Amount'];self.roll=item['Id'].split('#',1)[1] if '#' in item['Id'] else ''
        self.existing='KEEP'
        return context.window_manager.invoke_props_dialog(self,width=470)
    def draw(self,context):
        item=at(current_inventory(),state()['selected']);l=self.layout
        l.label(text=catalog.info(item).get('name') or item['Id']);l.label(text=item['Id'])
        if self.action=='REMOVE':l.label(text='Remove this item from the draft?',icon='TRASH');return
        entry=catalog.info(item)
        if item['Type']['InventoryType']!='Technology':
            l.prop(self,'amount',text='Total quantity')
            l.label(text=f"{catalog.required_cells(entry,self.amount)} slot(s) needed; capacity {catalog.capacity_for(entry)} each" if entry else f"Saved capacity: {item['MaxAmount']}")
        elif entry.get('chargeable'):
            l.prop(self,'amount',text='Charge')
            l.label(text=f"Charge capacity: {item['MaxAmount']}")
        if '#' in item['Id'] or catalog.info(item).get('procedural'):
            l.prop(self,'roll');l.prop(self,'existing')
            l.label(text='Rolls are not ranked. Final upgrade stats are calculated in game.')
    def execute(self,context):
        try:
            inv=current_inventory();item=at(inv,state()['selected'])
            if not item:raise ValueError('Item no longer exists')
            if self.action=='REMOVE':inv['Slots'].remove(item)
            else:
                entry=catalog.info(item)
                if item['Type']['InventoryType']!='Technology' and entry:
                    roll=item['Id'].split('#',1)[1] if '#' in item['Id'] else '00000'
                    catalog.place_items(inv,entry,state()['selected'],self.amount,roll,replace=item)
                else:
                    if not -1<=self.amount<=item['MaxAmount']:raise ValueError('Charge exceeds capacity')
                    if entry.get('chargeable'):item['Amount']=self.amount
                if self.roll:catalog.set_roll(item,self.existing if self.existing!='KEEP' else self.roll)
            store_inventory(inv)
        except Exception as exc:return self.fail(exc)
        finish_dialog();return {'FINISHED'}


class BBE_PG_ship_catalog_item(bpy.types.PropertyGroup):
    item_id:bpy.props.StringProperty()


def search_changed(self,context):
    if not SESSION:return
    ship=core.ships(SESSION['root'],SESSION['context'])[SESSION['index']]
    tech=SESSION['container']=='Inventory_TechOnly'
    needle=self.search.casefold().strip();self.results.clear();self.active=0
    for item in catalog.CATALOGUE:
        if catalog.allowed(item,ship,tech) and (not needle or needle in (item['id']+' '+item['name']).casefold()):
            row=self.results.add();row.item_id=item['id'];row.name=item['name'] or item['id']
            if len(self.results)>=250:break


class BBE_PG_ship_catalog(bpy.types.PropertyGroup):
    search:bpy.props.StringProperty(name='Search name or ID',update=search_changed)
    results:bpy.props.CollectionProperty(type=BBE_PG_ship_catalog_item)
    active:bpy.props.IntProperty()


class BBE_UL_ship_catalog(bpy.types.UIList):
    def draw_item(self,context,layout,data,item,icon,active_data,active_propname,index):
        row=layout.row();row.label(text=item.name);row.label(text=item.item_id)


class BBE_OT_ship_insert(Dialog,bpy.types.Operator):
    bl_idname='bbe.ship_insert';bl_label='Add Inventory Item'
    amount:bpy.props.IntProperty(name='Quantity / charge',default=1,min=1,max=99999)
    roll:bpy.props.StringProperty(name='Procedural roll',default='00000')
    def invoke(self,context,event):
        st=context.window_manager.bbe_ship_catalog;st.search='';search_changed(st,context)
        return context.window_manager.invoke_props_dialog(self,width=620)
    def draw(self,context):
        st=context.window_manager.bbe_ship_catalog;l=self.layout;l.prop(st,'search')
        l.template_list('BBE_UL_ship_catalog','',st,'results',st,'active',rows=9)
        if st.results:
            entry=catalog.BY_ID[st.results[st.active].item_id]
            if entry['type']!='Technology':
                l.prop(self,'amount',text='Total quantity')
                l.label(text=f"Uses {catalog.required_cells(entry,self.amount)} slot(s); {catalog.capacity_for(entry)} per slot")
            elif entry.get('chargeable'):l.prop(self,'amount',text='Charge')
            if entry.get('procedural'):l.prop(self,'roll')
        l.label(text='Items are filtered for this ship; type more to narrow large result sets.')
    def execute(self,context):
        try:
            s=state();inv=current_inventory();pos=s['selected'];st=context.window_manager.bbe_ship_catalog
            if at(inv,pos):raise ValueError('Choose an empty cell first')
            if dict(X=pos[0],Y=pos[1]) not in inv.get('ValidSlotIndices',[]):raise ValueError('Unlock the cell first')
            if not st.results:raise ValueError('No matching item')
            entry=catalog.BY_ID[st.results[st.active].item_id]
            catalog.place_items(inv,entry,pos,self.amount,self.roll);store_inventory(inv)
        except Exception as exc:return self.fail(exc)
        finish_dialog();return {'FINISHED'}


class BBE_OT_ship_replace_file(Dialog, bpy.types.Operator):
    bl_idname = 'bbe.ship_replace_file'
    bl_label = 'Replace / Repair Ship'
    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(default='*.nmsship;*.json;*.txt;*.nmsbase;*.nmsprefab', options={'HIDDEN'})
    mode: bpy.props.EnumProperty(name='Replacement', items=[
        ('FULL', 'Replace entire ship', 'Replace ship, inventories, appearance and build from a complete Corvette package'),
        ('OBJECTS', 'Replace build objects only', 'Keep the ship record, inventories and appearance; requires a correctly linked Corvette')])

    def invoke(self, context, event):
        s = state()
        self._session = s
        self._target = (s['context'], s['index'])
        s['busy'] = True
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        self.layout.prop(self, 'mode')
        self.layout.label(text='Full replacement requires a complete .nmsship package.')
        self.layout.label(text='Next: review destination and linked builds. No save writes yet.')

    def execute(self, context):
        try:
            s = state()
            if s is not getattr(self, '_session', None) or self._target != (s['context'], s['index']):
                raise ValueError('The selected save or ship changed; choose the replacement again.')
            payload = ship_repair.read_replacement(self.filepath, self.mode)
            records = ship_repair.linked_builds(s['root'], *self._target)
            if self.mode == 'OBJECTS':
                ship_repair.make_plan(s['root'], *self._target, payload, self.mode)
            s['replacement_review'] = dict(payload=payload, mode=self.mode,
                context=self._target[0], index=self._target[1], records=records,
                source=Path(self.filepath).name, fingerprint=ship_repair.fingerprint(s['root']))
            bpy.ops.bbe.ship_replace_review('INVOKE_DEFAULT')
            return {'FINISHED'}
        except Exception as exc:
            return self.fail(exc)


class BBE_OT_ship_replace_review(Dialog, bpy.types.Operator):
    bl_idname = 'bbe.ship_replace_review'
    bl_label = 'Review Ship Replacement'
    anchor: bpy.props.IntProperty(name='Keep destination metadata from build record', min=1)
    confirm_duplicates: bpy.props.BoolProperty(name='Replace ALL duplicate linked builds listed above', default=False)
    confirm_target: bpy.props.BoolProperty(name='I confirm this destination and the replacement shown above', default=False)

    def invoke(self, context, event):
        s = state()
        review = s.get('replacement_review')
        if review is None:
            return self.fail(ValueError('Choose a replacement file first.'))
        self._session = s
        self._review = review
        self.anchor = review['records'][0] + 1 if review['records'] else 1
        self.confirm_duplicates = self.confirm_target = False
        return context.window_manager.invoke_props_dialog(self, width=700, confirm_text='Stage Replacement')

    def draw(self, context):
        s = state(); r = self._review; l = self.layout
        from .function_help import help_button
        help_button(l, 'REPLACE')
        ship = core.ships(s['root'], r['context'])[r['index']]
        l.label(text=f"Destination: {r['context']} / Slot {r['index'] + 1:02} / {core.get(ship, 'Name') or 'Unnamed / empty'}", icon='ERROR')
        l.label(text=f"Source: {r['source']}")
        full = r['mode'] == 'FULL'
        l.label(text='REPLACE ENTIRE SHIP' if full else 'REPLACE BUILD OBJECTS ONLY')
        if full:
            l.label(text=f"New Corvette: {core.get(r['payload']['ship'], 'Name')} / {len(r['payload']['objects'])} parts")
            l.label(text='Replaces ship record, cargo, technology, class, stats, hyperslots and appearance.')
            l.label(text='Appearance: package settings' if r['payload'].get('custom') is not None else 'Appearance: default Corvette settings (package has no appearance record)')
        else:
            l.label(text=f"New build: {len(r['payload']['objects'])} parts")
            l.label(text='Keeps ship, cargo, technology, class, stats, hyperslots and appearance.')
        from .corvette_actions import warning
        warning(l, r['payload']['objects'])
        bases = core.get(core.player(s['root'], r['context']), 'PersistentPlayerBases', [])
        box = l.box(); box.label(text='Build records replaced:')
        for number in r['records']:
            base = bases[number]
            box.label(text=f"Record {number + 1}: {core.get(base, 'Name') or 'Unnamed'} ({len(core.get(base, 'Objects', []))} parts)")
        if not r['records']:
            box.label(text='No linked build: create one for this slot.')
        if len(r['records']) > 1:
            box.prop(self, 'anchor')
            box.prop(self, 'confirm_duplicates')
        l.label(text='Other ship slots and the freighter are preserved.')
        l.label(text='This stages a draft. Save Changes creates verified backups before writing.')
        l.prop(self, 'confirm_target')

    def cancel(self, context):
        if SESSION is getattr(self, '_session', None):
            SESSION.pop('replacement_review', None)
        finish_dialog()

    def execute(self, context):
        try:
            s = state(); r = self._review
            if s is not self._session or s.get('replacement_review') is not r:
                raise ValueError('This replacement review expired.')
            if ship_repair.fingerprint(s['root']) != r['fingerprint']:
                raise ValueError('The draft changed; review the replacement again.')
            if not self.confirm_target:
                raise ValueError('Confirm the destination before staging replacement.')
            plan = ship_repair.make_plan(s['root'], r['context'], r['index'], r['payload'], r['mode'],
                anchor=self.anchor - 1 if r['records'] else None, replace_duplicates=self.confirm_duplicates)
            draft = ship_repair.apply_plan(s['root'], plan)
            plans = [*s.get('repairs', []), plan]
            ship_repair.validate_reviewed_draft(s['original'], draft, plans)
            s['root'] = draft; s['repairs'] = plans; s['dirty'] = True
            s.pop('replacement_review', None)
            refresh_status(s)
            s['selected'] = (0, 0); s['move_special'] = None
            s['error'] = f"Replacement staged for slot {r['index'] + 1}. Review, then Save Changes."
        except Exception as exc:
            return self.fail(exc)
        finish_dialog(); return {'FINISHED'}


class BBE_OT_ship_save(Dialog,bpy.types.Operator):
    bl_idname='bbe.ship_save';bl_label='Save Ship Changes'
    def invoke(self,context,event):return context.window_manager.invoke_props_dialog(self,width=610)
    def draw(self,context):
        s=state();l=self.layout
        l.label(text='Write the reviewed draft to this save slot?',icon='QUESTION')
        for p in s['links']:l.label(text=str(p))
        l.label(text='Both save points will receive this draft, based on the latest save.')
        l.label(text='Verified backups are created before replacement.')
        for plan in s.get('repairs', []):
            l.label(text=f"REPLACE {plan['context']} slot {plan['index']+1}: " + ('entire ship' if plan['mode']=='FULL' else 'build objects'), icon='ERROR')
        if any(s.get('link_issues', {}).values()):
            l.label(text='Other uncertain ownership records will be preserved exactly.', icon='INFO')
        for ctx in core.contexts(s['root']):
            count=sum(core.occupied(v) for v in core.ships(s['root'],ctx));l.label(text=f'{ctx}: {count} owned ships')
    def execute(self,context):
        try:
            s=state()
            ship_repair.validate_reviewed_draft(s['original'],s['root'],s.get('repairs', []))
            if s['root']==s['original']:raise ValueError('No changes to save')
            backups=ship_files.commit(s['root'],s['links'],s['hashes'])
            s['original']=copy.deepcopy(s['root']);s['dirty']=False;_,s['hashes'],s['source']=ship_files.read(s['links'])
            s['repairs'] = []; refresh_status(s)
            s['error']=f'Saved. {len(backups)} verified backups created.'
            s['source_scene'].nms_save_data.refresh_bases_list()
        except Exception as exc:return self.fail(exc)
        finish_dialog();return {'FINISHED'}


class BBE_OT_ship_link_status(Dialog,bpy.types.Operator):
    bl_idname='bbe.ship_link_status';bl_label='Corvette Link Status'
    def invoke(self,context,event):
        return context.window_manager.invoke_props_dialog(self,width=680,confirm_text='Close')
    def draw(self,context):
        s=state();l=self.layout
        l.label(text='Inventory, technology, class, stats and hyperslot edits remain available.')
        l.label(text='Replace / Repair Ship reviews a specific replacement; other uncertain records stay unchanged.')
        l.label(text='Move Up/Down and Add Corvette are locked only in those contexts.')
        l.label(text='Duplicate Save / Clear Builds requires valid links in all contexts.')
        for ctx,issues in s.get('link_issues',{}).items():
            box=l.box();box.label(text='Expedition' if ctx=='Season' else 'Main',icon='ERROR' if issues else 'CHECKMARK')
            if not issues:box.label(text='All Corvette build links are recognized.')
            for issue in issues[:8]:
                for line in textwrap.wrap(issue,90):box.label(text=line)
            if len(issues)>8:box.label(text=f'{len(issues)-8} additional link warnings in this context.')
            for index, messages in s.get('slot_issues', {}).get(ctx, {}).items():
                if messages:
                    box.label(text=f"Slot {index+1:02}: {core.get(core.ships(s['root'],ctx)[index], 'Name') or 'Unnamed / empty'}", icon='ERROR')
                    for message in messages:
                        for line in textwrap.wrap(message,90):box.label(text=line)
    def execute(self,context):
        finish_dialog();return {'FINISHED'}


class BBE_PG_ship_keep(bpy.types.PropertyGroup):
    keep:bpy.props.BoolProperty(default=False)
    context_name:bpy.props.StringProperty()
    index:bpy.props.IntProperty()
    ship:bpy.props.BoolProperty()


class BBE_UL_ship_keep(bpy.types.UIList):
    def draw_item(self,context,layout,data,item,icon,active_data,active_propname,index):
        context_label = 'Expedition' if item.context_name == 'Season' else 'Main'
        layout.prop(item, 'keep', text=f'{context_label} | {item.name}')


class BBE_OT_ship_duplicate(Dialog,bpy.types.Operator):
    bl_idname='bbe.ship_duplicate';bl_label='Duplicate Save'
    bl_description='Create a new save slot from this save, keeping selected ships and builds'
    entries: bpy.props.CollectionProperty(type=BBE_PG_ship_keep, options={'SKIP_SAVE', 'HIDDEN'})
    active: bpy.props.IntProperty(options={'SKIP_SAVE', 'HIDDEN'})
    save_name:bpy.props.StringProperty(name='New save name',default='Builder Save',maxlen=100)
    slot:bpy.props.IntProperty(name='Empty save slot',min=1,max=15,default=9)
    @classmethod
    def poll(cls,context):
        data=getattr(context.scene,'nms_save_data',None)
        return bool(data and data.get_current_slot_data())
    def invoke(self,context,event):
        try:
            slot=context.scene.nms_save_data.get_current_slot_data()
            links=list(dict.fromkeys(p for p in slot['saves'] if p and Path(p).exists()))
            if not links:raise ValueError('Select a save slot containing game save files')
            self._root,self._hashes,self._source=ship_files.read(links)
            contexts = core.contexts(self._root)
            if not contexts:
                raise ValueError('No supported player context found in this save')
            for ctx in contexts:
                core.validate_links(self._root, ctx)
            self._empty=ship_files.empty_slots(self._source.parent)
            if not self._empty:raise ValueError('No empty game save slots')
            self.slot=self._empty[0]
            self.entries.clear()
            self.active = 0
            for ctx in contexts:
                default_ship = core.default_keep(self._root, ctx)
                for i,ship in enumerate(core.ships(self._root,ctx)):
                    if not core.occupied(ship):continue
                    row = self.entries.add()
                    row.context_name = ctx
                    row.index = i
                    row.ship = True
                    row.keep = i == default_ship
                    label = 'Corvette' if core.corvette(ship) else 'Ship'
                    row.name = f"{label} {i+1}: {core.get(ship,'Name') or 'Unnamed'}"
                for i,base in enumerate(core.get(core.player(self._root,ctx),'PersistentPlayerBases',[])):
                    if core.kind(base)=='PlayerShipBase':continue
                    row = self.entries.add()
                    row.context_name = ctx
                    row.index = i
                    name = core.get(base, 'Name') or core.kind(base) or 'Unnamed build'
                    row.name = f"Base {i+1}: {name} ({len(core.get(base, 'Objects', []))} parts)"
            return context.window_manager.invoke_props_dialog(self,width=650,confirm_text='Create Copy')
        except Exception as exc:return self.fail(exc)
    def draw(self,context):
        l=self.layout
        l.prop(self,'save_name');l.prop(self,'slot');l.label(text='Empty slots: '+', '.join(map(str,self._empty)))
        l.label(text='Check the bases and ships to keep. Each populated context needs one ship.')
        l.template_list('BBE_UL_ship_keep','',self.properties,'entries',self.properties,'active',rows=12)
        l.label(text='A retained Corvette also retains its linked build.')
        l.label(text='Uses the selected saved source, excluding unsaved Ship Management edits.')
        l.label(text='Creates a NEW save slot. The source save is kept intact.')
    def execute(self,context):
        try:
            if self.slot not in self._empty:raise ValueError('Choose one of the empty slots listed')
            ships={};bases={}
            for row in self.entries:
                if row.keep:(ships if row.ship else bases).setdefault(row.context_name,[]).append(row.index)
            root=core.clean_copy(self._root,self.save_name,ships,bases)
            ship_files.commit(root,ship_files.slot_paths(self._source.parent,self.slot),self._hashes,source=self._source,name=self.save_name,create=True)
            self.report({'INFO'},f'Created save slot {self.slot}: {self.save_name}. Refresh the account list to select it.')
        except Exception as exc:return self.fail(exc)
        return {'FINISHED'}


# Draw the whole background/grid in one GPU batch. Shader and batch creation
# for each individual slot made the former full-screen overlay sluggish.
def rect(x,y,w,h,colour):
    p=FRAME['pos'];c=FRAME['colour'];vertices=((x,y),(x+w,y),(x+w,y+h),(x,y),(x+w,y+h),(x,y+h))
    p.extend(vertices);c.extend([colour]*6)


def icon_overlay(x,y,w,h,colour):
    p=FRAME['overlay_pos'];c=FRAME['overlay_colour']
    p.extend(((x,y),(x+w,y),(x+w,y+h),(x,y),(x+w,y+h),(x,y+h)))
    c.extend([colour]*6)


def text(x,y,value,size=13,colour=(.88,.91,.96,1),width=10000):
    FRAME['text'].append((x,y,str(value),size,colour,width))


def icon(x,y,w,index):
    global ATLAS
    if index<0:return
    if ATLAS is None:
        img=bpy.data.images.load(str(core.RES/'ship_inventory_icons.png'),check_existing=True)
        ATLAS=gpu.texture.from_image(img)
    u=index/40;v=(index+1)/40
    FRAME['icon_pos'].extend(((x,y),(x+w,y),(x+w,y+w),(x,y),(x+w,y+w),(x,y+w)))
    FRAME['icon_uv'].extend(((u,0),(v,0),(v,1),(u,0),(v,1),(u,1)))


def flush_frame():
    shader=gpu.shader.from_builtin('SMOOTH_COLOR')
    shader.bind()
    batch_for_shader(shader,'TRIS',{'pos':FRAME['pos'],'color':FRAME['colour']}).draw(shader)
    if FRAME['icon_pos']:
        shader=gpu.shader.from_builtin('IMAGE');shader.bind();shader.uniform_sampler('image',ATLAS)
        batch_for_shader(shader,'TRIS',{'pos':FRAME['icon_pos'],'texCoord':FRAME['icon_uv']}).draw(shader)
    if FRAME['overlay_pos']:
        shader=gpu.shader.from_builtin('SMOOTH_COLOR');shader.bind()
        batch_for_shader(shader,'TRIS',{'pos':FRAME['overlay_pos'],'color':FRAME['overlay_colour']}).draw(shader)
    for x,y,value,size,colour,width in FRAME['text']:
        blf.size(0,size)
        if blf.dimensions(0,value)[0]>width:
            lo,hi=0,len(value)
            while lo<hi:
                mid=(lo+hi+1)//2
                if blf.dimensions(0,value[:mid])[0]<=width:lo=mid
                else:hi=mid-1
            value=value[:lo]
        blf.color(0,*colour);blf.position(0,x,y,0);blf.draw(0,value)


def layout_geometry(region):
    w,h=region.width,region.height
    cell=min(105,max(48,(w-290)/10),max(48,(h-300)/6))
    return 255,h-170,cell,cell


def draw_overlay(self):
    global FRAME
    s=SESSION
    if not s or bpy.context.area!=self._area or bpy.context.region.type!='WINDOW':return
    region=bpy.context.region;w,h=region.width,region.height
    FRAME={'pos':[],'colour':[],'icon_pos':[],'icon_uv':[],'overlay_pos':[],'overlay_colour':[],'text':[]}
    gpu.state.blend_set('ALPHA');rect(0,0,w,h,(.022,.03,.045,1));self._buttons=[];self._cells=[];self._popup_buttons=[]
    def button(x,y,bw,title,action,active=False,enabled=True,warning=None):
        rect(x,y,bw,27,(.12,.31,.45,1) if active else (.09,.12,.17,1))
        text(x+7,y+(15 if warning else 8),('! ' if warning else '')+title,11 if warning else 12,(1,.32,.32,1) if warning else (.88,.91,.96,1) if enabled else (.4,.44,.5,1),width=bw-10)
        if warning:text(x+7,y+3,warning,9,(1,.48,.48,1),width=bw-10)
        if enabled:self._buttons.append((x,y,bw,27,action))
    text(18,h-31,'SHIP MANAGEMENT (BETA)',20)
    text(320,h-30,'Inventory & Technology',19)
    dirty=s.get('dirty',False);text(w-185,h-28,'Unsaved draft' if dirty else 'Saved snapshot',13)
    for i,ctx in enumerate(core.contexts(s['root'])):button(18+i*112,h-70,106,'Main' if ctx=='Main' else 'Expedition',('context',ctx),s['context']==ctx)
    owned=core.ships(s['root'],s['context'])
    restricted=bool(s.get('link_issues',{}).get(s['context'])) or pending_repair(s)
    slot_issues=s.get('slot_issues',{}).get(s['context'],{})
    if any(s.get('link_issues',{}).values()) or any(slot_issues.values()):
        button(600,h-38,220,'Ownership notice / Link Status',('links',None))
    for i,ship in enumerate(owned):
        label=core.get(ship,'Name') or ('Unnamed ship' if core.occupied(ship) else 'EMPTY')
        button(18,h-110-i*30,216,f'{i+1:02}  {label}',('ship',i),i==s['index'],warning=next(iter(slot_issues.get(i,[])),None))
    button(18,h-490,103,'Move Up',('move',-1),enabled=not restricted);button(131,h-490,103,'Move Down',('move',1),enabled=not restricted)
    button(18,h-526,216,'Add Minimal Corvette',('add',None),enabled=not restricted)
    cls=core.get(core.get(core.get(owned[s['index']],'Inventory',{}),'Class',{}),'InventoryClass','—')
    button(18,h-562,216,'Ship Class: '+cls,('class',None))
    button(18,h-598,103,'Repair Build...',('repair',None))
    button(131,h-598,103,'Replace File...',('replace',None))
    button(18,75,216,'Save Changes...',('save',None));button(18,38,216,'Close',('close',None))
    button(w-37,h-38,28,'X',('close',None))
    for i,(container,label) in enumerate((('Inventory_TechOnly','Technology'),('Inventory','Cargo'))):
        button(255+i*132,h-70,124,label,('container',container),s['container']==container)
    ship=owned[s['index']]
    if restricted:
        text(18,105,'Ship links locked — see Link Status',11,(1,.75,.38,1),216)
    if not core.occupied(ship):
        text(275,h-140,'Empty slot — select an owned ship to edit.' if restricted else 'Empty ship slot - add a minimal Corvette to begin.',16)
        flush_frame();gpu.state.blend_set('NONE');return
    messages=slot_issues.get(s['index'],[])
    if messages:
        text(255,h-137,'! '+messages[0],12,(1,.38,.38,1),w-275)
        text(255,h-155,'Repair keeps your saved build and readable ship data. Link Status shows all issues.',11,(1,.65,.65,1),w-275)
    try:
        inv=current_inventory();core.validate_inventory(inv)
    except (ValueError,TypeError,KeyError,AttributeError):
        text(255,h-190,'Inventory cannot be edited safely. Repair Build can retain its parts and review data resets.',13,(1,.45,.45,1),w-275)
        flush_frame();gpu.state.blend_set('NONE');return
    for i,(label,action) in enumerate((('Add item','insert'),('Edit / Roll','edit'),('Remove','remove'),('Unlock All','unlock'),('Move Hyperslot','special'))):
        button(255+i*112,h-108,105,label,(action,None))
    button(815,h-108,132,'Edit Ship Stats...',('stats',None))
    inv=current_inventory();linked=catalog.links(inv);x0,top,cw,ch=layout_geometry(region)
    valid={(v['X'],v['Y']) for v in inv.get('ValidSlotIndices',[])}
    specials={(v['Index']['X'],v['Index']['Y']) for v in inv.get('SpecialSlots',[]) if v['Type']['InventorySpecialSlotType']=='TechBonus'}
    rows=6
    page=s.get('cargo_page',0) if s['container']=='Inventory' else 0
    if s['container']=='Inventory':
        button(820,h-70,98,'Rows 1–6' if page==0 else 'Rows 7–12',('page',None),True)
        text(930,h-62,'Mouse wheel changes cargo rows',12)
    cells={(v['Index']['X'],v['Index']['Y']):v for v in inv.get('Slots',[])}
    self._cells=[]
    for y in range(rows):
        for x in range(10):
            px=x0+x*cw;py=top-(y+1)*ch;pos=(x,y+6*page);item=cells.get(pos)
            border=(*linked[pos]['colour'],1) if pos in linked else (.18,.22,.28,1)
            bg=(.20,.10,.34,1) if pos in specials else (.065,.09,.13,1) if pos in valid else (.028,.033,.044,1)
            if pos in specials:
                purple=(.89,.38,1,1)
                rect(px,py,cw-3,ch-3,purple)
                if pos in linked:
                    rect(px+3,py+3,cw-9,ch-9,border)
                    rect(px+6,py+6,cw-15,ch-15,bg)
                else:rect(px+3,py+3,cw-9,ch-9,bg)
            else:
                rect(px,py,cw-3,ch-3,border)
                rect(px+3,py+3,cw-9,ch-9,bg)
            if item:
                data=catalog.info(item)
                if s['container']=='Inventory_TechOnly':
                    inset=7 if pos in specials and pos in linked else 4
                    icon(px+inset,py+inset,min(cw-3-2*inset,ch-3-2*inset),data.get('icon',-1))
                    icon_overlay(px+inset,py+inset,cw-3-2*inset,18,(.008,.013,.025,.88))
                    if pos not in linked:
                        icon_overlay(px+inset+3,py+ch-8,cw-9-2*inset,2,(.88,.91,.96,1))
                    if data.get('chargeable'):
                        icon_overlay(px+cw-37,py+ch-21,29,15,(.008,.013,.025,.80))
                tint=(.94,.62,1,1) if pos in specials else (.88,.91,.96,1)
                name=data.get('name') or item['Id']
                label_x=px+inset+5 if s['container']=='Inventory_TechOnly' else px+5
                text(label_x,py+5,name,10,tint,width=cw-(label_x-px)-5)
                if s['container']=='Inventory' or data.get('chargeable'):
                    text(px+cw-32,py+ch-16,str(item['Amount']),10,tint,width=29)
            elif pos not in valid:text(px+7,py+ch/2-3,'Locked',10,width=cw-12)
            if pos in specials:text(px+5,py+ch-15,'SC',10,(.94,.62,1,1))
            if pos==s['selected']:
                rect(px,py,cw-3,2,(.9,.94,1,1));rect(px,py,2,ch-3,(.9,.94,1,1));rect(px,py+ch-5,cw-3,2,(.9,.94,1,1));rect(px+cw-5,py,2,ch-3,(.9,.94,1,1))
            self._cells.append((px,py,cw-3,ch-3,pos))
    if w>=1610:
        panel=1320;rect(panel,113,w-panel-16,h-252,(.055,.075,.105,1))
        text(panel+12,h-164,'SHIP STATS',16)
        text(panel+12,h-194,'Saved base rolls',12,(.65,.75,.85,1))
        base=core.get(owned[s['index']],'Inventory',{})
        for i,stat in enumerate(core.get(base,'BaseStatValues',[])):
            name=core.get(stat,'BaseStatID','').lstrip('^').replace('SHIP_','').title()
            value=core.get(stat,'Value',0)
            text(panel+12,h-218-i*32,name,12,width=115)
            button(panel+127,h-227-i*32,min(135,w-panel-160),f'{value:.4f}',('stats',None))
        text(panel+12,h-340,'Technology output is calculated in game.',11,(.65,.75,.85,1))
    if len(specials)>4:text(255,105,f'{len(specials)} hyperslots: more than 4 may cause instability. Existing slots are preserved.',12,(1,.65,.3,1))
    selected=at(inv,s['selected'])
    details=(catalog.info(selected).get('name') or selected['Id'])+'  |  '+selected['Id'] if selected else 'Select a slot'
    text(255,81,details,14,width=w-275)
    text(255,58,'Drag to move/swap | Right-click to edit roll/quantity | Right-click > Move Hyperslot, then click destination',12,width=w-275)
    text(255,38,'Purple SC = supercharged | Coloured border = adjacent technology family | Diagonals do not link',12,width=w-275)
    text(18,13,s.get('error','Edits stay in this draft until Save Changes.'),12,(1,.75,.38,1),w-36)
    if s.get('context_menu') is not None:
        choices=[]
        if selected:choices.extend((('Edit quantity / roll','edit'),('Remove item','remove')))
        elif s['selected'] in valid:choices.append(('Add item','insert'))
        if s['container']=='Inventory_TechOnly' and s['selected'] in specials:
            choices.append(('Move Hyperslot','special'))
        if choices:
            mx,my=s['context_menu'];mw=200;mh=6+len(choices)*29
            left=max(0,min(mx,w-mw-2));bottom=max(0,min(my-mh,h-mh-2))
            icon_overlay(left,bottom,mw,mh,(.035,.05,.075,.98))
            for i,(label,op) in enumerate(choices):
                py=bottom+mh-3-(i+1)*29
                icon_overlay(left+3,py,mw-6,27,(.09,.15,.22,.98))
                text(left+10,py+8,label,12,width=mw-18)
                self._popup_buttons.append((left+3,py,mw-6,27,(op,None)))
    flush_frame();gpu.state.blend_set('NONE')



class BBE_OT_ship_move_hyperslot(bpy.types.Operator):
    bl_idname='bbe.ship_move_hyperslot';bl_label='Move Hyperslot'
    bl_description='Move this existing supercharged slot: click an unlocked destination. No extra slots are created'
    def execute(self,context):
        s=state();s['move_special']=s['selected'];s['error']='Click an unlocked destination for this hyperslot. Escape cancels the move.'
        redraw();return {'FINISHED'}


class BBE_OT_ship_management_window(bpy.types.Operator):
    bl_idname='bbe.ship_management_window';bl_label='Ship Management (Beta) Window'
    bl_description='Manage ship slots, technology, cargo and supercharged slots'
    def invoke(self,context,event):
        global SESSION,HANDLER,ACTIVE_UI
        if context.area.type!='VIEW_3D':report_error(self, {'ERROR'},'Open Ship Management in the 3D View');return {'CANCELLED'}
        try:
            if SESSION is None:raise ValueError('Open Ship Management from a Corvette save')
            self._area=context.area;self._space=context.space_data;self._ui_flags={p:getattr(self._space,p) for p in ('show_region_ui','show_region_toolbar','show_region_header')}
            for p in self._ui_flags:setattr(self._space,p,False)
            self._region=next(r for r in context.area.regions if r.type=='WINDOW');self._buttons=[];self._cells=[];self._popup_buttons=[];self._drag=None
            self._space.shading.type='SOLID'
            HANDLER=bpy.types.SpaceView3D.draw_handler_add(draw_overlay,(self,),'WINDOW','POST_PIXEL')
            ACTIVE_UI=self
            context.window_manager.modal_handler_add(self);context.area.tag_redraw();return {'RUNNING_MODAL'}
        except Exception as exc:report_error(self, {'ERROR'},str(exc));return {'CANCELLED'}
    def close(self):
        global SESSION,HANDLER,ACTIVE_UI
        if HANDLER:bpy.types.SpaceView3D.draw_handler_remove(HANDLER,'WINDOW')
        SESSION=None;HANDLER=None;ACTIVE_UI=None
        try:
            for p,v in getattr(self,'_ui_flags',{}).items():setattr(self._space,p,v)
        except ReferenceError:pass
        redraw();return {'FINISHED'}
    def modal(self,context,event):
        s=SESSION
        if not s:return self.close()
        if s['busy']:return {'PASS_THROUGH'}
        if event.type=='ESC' and event.value=='PRESS':
            if s.get('context_menu') is not None:
                s['context_menu']=None;redraw();return {'RUNNING_MODAL'}
            if s.get('move_special') is not None:
                s['move_special']=None;s['error']='Hyperslot move cancelled.';redraw();return {'RUNNING_MODAL'}
            bpy.ops.bbe.ship_discard('INVOKE_DEFAULT');return {'RUNNING_MODAL'}
        if event.type in ('WHEELUPMOUSE','WHEELDOWNMOUSE') and s['container']=='Inventory':
            s['cargo_page']=0 if event.type=='WHEELUPMOUSE' else 1;redraw();return {'RUNNING_MODAL'}
        if event.type not in ('LEFTMOUSE','RIGHTMOUSE','MOUSEMOVE'):return {'RUNNING_MODAL'}
        mx,my=event.mouse_x-self._region.x,event.mouse_y-self._region.y
        hit=lambda box:box[0]<=mx<=box[0]+box[2] and box[1]<=my<=box[1]+box[3]
        cell=next((b[4] for b in self._cells if hit(b)),None)
        try:
            if event.type=='RIGHTMOUSE' and event.value=='PRESS':
                s['context_menu']=(mx,my) if cell is not None else None
                if cell is not None:s['selected']=cell
                self._area.tag_redraw();return {'RUNNING_MODAL'}
            menu_action=None
            if event.type=='LEFTMOUSE' and event.value=='PRESS' and s.get('context_menu') is not None:
                menu_action=next((b[4] for b in self._popup_buttons if hit(b)),None)
                s['context_menu']=None
                if menu_action is None:
                    self._area.tag_redraw();return {'RUNNING_MODAL'}
                cell=None
            if event.type=='LEFTMOUSE' and event.value=='RELEASE' and self._drag:
                start,special=self._drag;self._drag=None
                if cell is not None and cell!=start:
                    inv=current_inventory()
                    core.move_item(inv,start,cell)
                    store_inventory(inv);s['selected']=cell;s['discard']=False
            elif event.value=='PRESS' and event.type in ('LEFTMOUSE','RIGHTMOUSE'):
                action=menu_action or next((b[4] for b in self._buttons if hit(b)),None)
                if cell is not None:
                    s['selected']=cell
                    if s.get('move_special') is not None:
                        inv=current_inventory();core.move_supercharge(inv,s['move_special'],cell);store_inventory(inv);s['move_special']=None;s['error']='Hyperslot moved; total count unchanged.'
                    else:self._drag=(cell,False)
                if action:
                    op,arg=action;s['error']='';s['discard']=False
                    if op in ('context','ship','container','move'):s['move_special']=None;self._drag=None
                    if op=='context':s['context']=arg;s['index']=0;self._cells=[]
                    elif op=='ship':s['index']=arg;self._cells=[]
                    elif op=='container':s['container']=arg;self._cells=[]
                    elif op=='page':s['cargo_page']=1-s.get('cargo_page',0);self._cells=[]
                    elif op=='move':
                        i=s['index'];j=i+arg
                        if 0<=j<12:
                            order=list(range(12));order[i],order[j]=order[j],order[i]
                            draft=copy.deepcopy(s['root']);core.reorder(draft,s['context'],order);s['root']=draft;s['dirty']=True;s['index']=j
                    elif op=='unlock':inv=current_inventory();core.unlock(inv,s['container']=='Inventory_TechOnly');store_inventory(inv)
                    elif op=='special':
                        if s['container']!='Inventory_TechOnly':raise ValueError('Hyperslots belong in Technology')
                        inv=current_inventory()
                        if not any(v['Index']==dict(X=s['selected'][0],Y=s['selected'][1]) and v['Type']['InventorySpecialSlotType']=='TechBonus' for v in inv.get('SpecialSlots',[])):raise ValueError('Select an existing hyperslot first')
                        bpy.ops.bbe.ship_move_hyperslot()
                    elif op=='close':bpy.ops.bbe.ship_discard('INVOKE_DEFAULT')
                    else:
                        s['busy']=True
                        if op=='class':bpy.ops.bbe.ship_class('INVOKE_DEFAULT')
                        elif op=='links':bpy.ops.bbe.ship_link_status('INVOKE_DEFAULT')
                        elif op=='replace':bpy.ops.bbe.ship_replace_file('INVOKE_DEFAULT')
                        elif op=='repair':bpy.ops.bbe.corvette_repair_keep('INVOKE_DEFAULT', in_manager=True)
                        elif op=='stats':bpy.ops.bbe.ship_stats('INVOKE_DEFAULT')
                        elif op=='add':bpy.ops.bbe.ship_add('INVOKE_DEFAULT')
                        elif op=='save':bpy.ops.bbe.ship_save('INVOKE_DEFAULT')
                        elif op=='insert':bpy.ops.bbe.ship_insert('INVOKE_DEFAULT')
                        elif op in ('edit','remove'):bpy.ops.bbe.ship_item('INVOKE_DEFAULT',action='REMOVE' if op=='remove' else 'EDIT')
        except Exception as exc:s['error']=str(exc);s['busy']=False
        self._area.tag_redraw();return {'RUNNING_MODAL'}
    def cancel(self,context):
        global HANDLER,ACTIVE_UI
        if SESSION and SESSION.get('dirty'):
            if HANDLER:bpy.types.SpaceView3D.draw_handler_remove(HANDLER,'WINDOW')
            HANDLER=None;ACTIVE_UI=None
        else:self.close()


class BBE_OT_ship_discard(Dialog,bpy.types.Operator):
    bl_idname='bbe.ship_discard';bl_label='Close Ship Management'
    def invoke(self,context,event):
        if SESSION is None:return {'CANCELLED'}
        if not SESSION.get('dirty'):return self.execute(context)
        SESSION['busy']=True
        return context.window_manager.invoke_props_dialog(self,width=450,confirm_text='Discard Draft')
    def draw(self,context):
        self.layout.label(text='Discard unsaved Ship Management changes?',icon='QUESTION')
        self.layout.label(text='Nothing has been written to the game save.')
    def execute(self,context):
        global MANAGER_WINDOW,SESSION
        preview=SESSION.get('preview_scene') if SESSION else None
        restore_source_window(SESSION)
        if ACTIVE_UI:ACTIVE_UI.close()
        else:SESSION=None
        window=MANAGER_WINDOW;MANAGER_WINDOW=None
        if window and any(w==window for w in context.window_manager.windows):
            def close_window():
                try:
                    with bpy.context.temp_override(window=window):bpy.ops.wm.window_close()
                except (ReferenceError,RuntimeError):pass
                if preview and preview.name in bpy.data.scenes and preview.users==0:
                    bpy.data.scenes.remove(preview)
                return None
            bpy.app.timers.register(close_window,first_interval=.25)
        return {'FINISHED'}


class BBE_OT_ship_lost(Dialog,bpy.types.Operator):
    bl_idname='bbe.ship_lost';bl_label='Ship Management Closed'
    def invoke(self,context,event):
        return context.window_manager.invoke_props_dialog(self,width=450,confirm_text='Discard Draft')
    def draw(self,context):
        self.layout.label(text='The Ship Management window closed with unsaved changes.',icon='QUESTION')
        self.layout.label(text='Discard this draft, or Cancel to reopen it.')
    def execute(self,context):
        global SESSION
        SESSION=None
        return {'FINISHED'}
    def cancel(self,context):
        if SESSION:SESSION['busy']=False
        # Creating a new OS window while Blender is destroying this popup can
        # crash its recursive menu handler. Reopen after the dialog is gone.
        wm=context.window_manager
        def reopen():
            if SESSION and MANAGER_WINDOW is None:
                open_manager_window(wm)
            return None
        bpy.app.timers.register(reopen,first_interval=.35)


def open_manager_window(wm):
    global MANAGER_WINDOW,HANDLER,ACTIVE_UI
    from ..tools.asset_browser_operators import get_process_window_handles,resize_window,set_window_title
    handles=set(get_process_window_handles())
    existing={w.as_pointer() for w in wm.windows}
    # A temporary window shares scene changes with its parent. A separate
    # main window lets the empty UI preview leave the building scene intact.
    bpy.ops.wm.window_new_main()
    window=next(w for w in wm.windows if w.as_pointer() not in existing)
    MANAGER_WINDOW=window
    preview=bpy.data.scenes.new('BBE Ship Management Preview')
    source_scene = SESSION.get('source_scene') if SESSION else None
    if source_scene:
        preview['bbe_ship_management_source_scene'] = source_scene.name
    window.scene=preview
    SESSION['preview_scene']=preview
    attempts={'n':0,'maximized':False}
    def start():
        attempts['n']+=1
        if not any(w==window for w in wm.windows):return None
        try:
            for hwnd in set(get_process_window_handles())-handles:
                resize_window(hwnd,1660,910);set_window_title(hwnd,'Ship Management (Beta)')
            area=max((a for a in window.screen.areas if a.type=='VIEW_3D'),key=lambda a:a.width*a.height)
            region=next(r for r in area.regions if r.type=='WINDOW')
            if not attempts['maximized']:
                with bpy.context.temp_override(window=window,area=area,region=region):bpy.ops.screen.screen_full_area()
                attempts['maximized']=True
            area=max((a for a in window.screen.areas if a.type=='VIEW_3D'),key=lambda a:a.width*a.height)
            region=next(r for r in area.regions if r.type=='WINDOW')
            with bpy.context.temp_override(window=window,area=area,region=region):bpy.ops.bbe.ship_management_window('INVOKE_DEFAULT')
            return None
        except (ReferenceError,RuntimeError,ValueError,StopIteration):
            return .05 if attempts['n']<40 else None
    def monitor():
        global SESSION,HANDLER,ACTIVE_UI,MANAGER_WINDOW
        if any(w==window for w in wm.windows):return .25
        restore_source_window(SESSION)
        if HANDLER:bpy.types.SpaceView3D.draw_handler_remove(HANDLER,'WINDOW')
        HANDLER=None;ACTIVE_UI=None;MANAGER_WINDOW=None
        preview=SESSION.get('preview_scene') if SESSION else None
        if preview and preview.name in bpy.data.scenes and preview.users==0:
            bpy.data.scenes.remove(preview)
        if SESSION:SESSION['preview_scene']=None
        if SESSION and SESSION.get('dirty'):
            SESSION['busy']=True
            try:
                source=SOURCE_WINDOW
                area=next(a for a in source.screen.areas if a.type=='VIEW_3D')
                region=next(r for r in area.regions if r.type=='WINDOW')
                with bpy.context.temp_override(window=source,area=area,region=region):bpy.ops.bbe.ship_lost('INVOKE_DEFAULT')
            except (ReferenceError,RuntimeError,StopIteration):
                SESSION['busy']=False
        else:SESSION=None
        return None
    bpy.app.timers.register(start,first_interval=.05)
    bpy.app.timers.register(monitor,first_interval=.25)


class BBE_OT_ship_management(bpy.types.Operator):
    bl_idname='bbe.ship_management';bl_label='Ship Management (Beta)'
    bl_description='Open ship slots, technology and cargo for the selected Corvette save'
    @classmethod
    def poll(cls,context):
        data=getattr(context.scene,'nms_save_data',None)
        return bool(data and data.nms_base_type==BaseType.CORVETTE and data.get_current_slot_data())
    def invoke(self,context,event):
        global SESSION,SOURCE_WINDOW
        if SESSION:
            self.report({'WARNING'},'Ship Management is already open');return {'CANCELLED'}
        try:
            data=context.scene.nms_save_data
            if data.nms_base_type!=BaseType.CORVETTE:raise ValueError('Choose the Corvette tab first')
            slot=data.get_current_slot_data()
            if not slot:raise ValueError('Select an account and save slot first')
            links=list(dict.fromkeys(p for p in slot['saves'] if p and Path(p).exists()))
            root,hashes,source=ship_files.read(links)
            issues=core.inspect_links(root)
            selected=data.get_current_base_identifiers()
            ctx=getattr(selected,'save_context',None)
            if ctx not in issues:ctx=next(iter(issues))
            owned=core.ships(root,ctx);index=getattr(selected,'user_data',None)
            if type(index) is not int or not 0<=index<12 or not core.occupied(owned[index]):
                index=core.get(core.player(root,ctx),'PrimaryShip',0)
            if type(index) is not int or not 0<=index<12 or not core.occupied(owned[index]):
                index=next((i for i,ship in enumerate(owned) if core.occupied(ship)),0)
            SESSION=dict(root=root,original=copy.deepcopy(root),hashes=hashes,source=source,links=links,context=ctx,index=index,container='Inventory_TechOnly',selected=(0,0),busy=False,error='',link_issues=issues,repairs=[])
            refresh_status(SESSION)
            SOURCE_WINDOW=context.window;SESSION['source_scene']=context.scene
            open_manager_window(context.window_manager)
            return {'FINISHED'}
        except Exception as exc:
            SESSION=None;report_error(self, {'ERROR'},str(exc));return {'CANCELLED'}


CLASSES=(BBE_PG_ship_catalog_item,BBE_PG_ship_catalog,BBE_UL_ship_catalog,BBE_PG_ship_keep,BBE_UL_ship_keep,BBE_PG_ship_stat,BBE_OT_ship_class,BBE_OT_ship_stats,BBE_OT_ship_add,BBE_OT_ship_item,BBE_OT_ship_insert,BBE_OT_ship_replace_file,BBE_OT_ship_replace_review,BBE_OT_ship_save,BBE_OT_ship_link_status,BBE_OT_ship_duplicate,BBE_OT_ship_move_hyperslot,BBE_OT_ship_discard,BBE_OT_ship_lost,BBE_OT_ship_management_window,BBE_OT_ship_management)

def register():
    for cls in CLASSES:bpy.utils.register_class(cls)
    bpy.types.WindowManager.bbe_ship_catalog=bpy.props.PointerProperty(type=BBE_PG_ship_catalog)
    bpy.app.handlers.load_post.append(repair_after_load)
    bpy.app.timers.register(repair_orphaned_preview_windows, first_interval=.1)

def unregister():
    global SESSION,HANDLER,ATLAS
    if HANDLER:bpy.types.SpaceView3D.draw_handler_remove(HANDLER,'WINDOW')
    SESSION=HANDLER=ATLAS=None
    if repair_after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(repair_after_load)
    if bpy.app.timers.is_registered(repair_orphaned_preview_windows):
        bpy.app.timers.unregister(repair_orphaned_preview_windows)
    del bpy.types.WindowManager.bbe_ship_catalog
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)

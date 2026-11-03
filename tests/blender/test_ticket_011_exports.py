"""Ticket 009/010/011 reproduction on disposable HG files and a real Blender scene."""
import copy, json, os, sys, tempfile
from pathlib import Path
from types import SimpleNamespace as NS, MethodType
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_support import module, addon, QA
actions=module('save_editor.corvette_actions'); repair=module('save_editor.ship_repair')
core=module('save_editor.ship_core'); files=module('save_editor.ship_files')
manager=module('save_editor.save_manager'); utils=module('save_editor.save_editor_utils')
optimizer=module('save_editor.corvette_optimizer'); builder=module('builder_v2')
T=json.loads((core.RES/'minimal_corvette.json').read_text())
M=manager.SaveManager
folder=Path(tempfile.mkdtemp(prefix='ticket011-',dir=QA/'tmp'))
paths=[folder/'save9.hg',folder/'save10.hg']
accounts=[('Default','Select account',''),('qa-only','Disposable account','')]
slots=[dict(slot=5,saves=[str(p) for p in paths],save_name='Disposable test')]
results=[]; errors=[]
patches=[patch.object(M,'get_accounts_enum_list',return_value=accounts),
         patch.object(utils,'get_save_slots_list',return_value=slots),
         patch.object(files.backup_policy,'settings',return_value=(str(folder/'backups'),100)),
         patch.object(optimizer,'settings_file',return_value=folder/'optimizer.json'),
         patch.object(actions,'report_error',side_effect=lambda op,severity,msg:errors.append(msg))]
for p in patches:p.start()

def fixture(bad=None):
    ships=[copy.deepcopy(T['empty']) for _ in range(12)]; bases=[]
    # Build record index deliberately differs from ship slot index and list order.
    for index,name in ((3,'Horseman'),(0,'Indian'),(2,'Spaceman')):
        ships[index]=copy.deepcopy(T['ship']);ships[index]['Name']=name
        base=copy.deepcopy(T['base']);base.update(UserData=index,Name=name);bases.append(base)
    player=dict(ShipOwnership=ships,PersistentPlayerBases=bases,PrimaryShip=2,PlayerFreighterName="QA freighter",
                CharacterCustomisationData=[copy.deepcopy(T['custom']) for _ in range(23)])
    root=dict(BaseContext=dict(PlayerStateData=player,SpawnStateData={'LastKnownPlayerState':'OnFoot'}),
              CommonStateData={'SaveName':'Disposable QA'},ActiveContext='Main')
    if bad=='eleven_slots':player['ShipOwnership'].pop()
    if bad=='inactive_expedition':root['ExpeditionContext']={'PlayerStateData':{'ShipOwnership':[],'PersistentPlayerBases':[],'PlayerFreighterName':'QA expedition'}}
    if bad=='duplicate_link':bases.append(copy.deepcopy(bases[2]))
    return core.translate(root,False)

def write(root):
    for path in paths:
        save=files.SaveFile(path);save.json_data=root;save.save()

def select(index=2):
    d=bpy.context.scene.nms_save_data
    d.check_plugin_enabled=True
    d.nms_account_selected='qa-only';d.nms_save_slot='5'
    d.refresh_bases_list()
    selected=next(b for b in d.extracted_base_data['corvettes'] if b.user_data==index and b.save_context=='Main')
    d.nms_base_index=str(selected.base_index)
    assert d.get_current_base_identifiers().user_data==index
    return d

def operator(optimized):
    op=NS(optimized=optimized,report=lambda severity,msg:None,dialog_key='')
    for method in ('check','cancel'):
        setattr(op,method,MethodType(getattr(actions.BBE_OT_corvette_export,method),op))
    return op

def invoke(op):
    # Only substitute the dialog display; all destination discovery, scene
    # serialization, validation, compression, backups and disk writes are real.
    context=NS(scene=bpy.context.scene,view_layer=bpy.context.view_layer,window=None,
               window_manager=NS(invoke_props_dialog=lambda *a,**k:{'RUNNING_MODAL'}))
    return actions.BBE_OT_corvette_export.invoke(op,context,None)

def run_export(optimized,repeat):
    d=bpy.context.scene.nms_save_data
    before=files.SaveFile(paths[0]).load()
    before_ships=copy.deepcopy(core.ships(before,'Main'))
    op=operator(optimized)
    assert invoke(op)=={'RUNNING_MODAL'},errors
    assert op.destination=='SELECTED' and op.slot=='2' and op._index==2
    op.confirm=True
    assert actions.BBE_OT_corvette_export.execute(op,bpy.context)=={'FINISHED'},errors
    after=files.SaveFile(paths[0]).load()
    assert files.SaveFile(paths[1]).load()==after
    assert len(core.ships(after,'Main'))==12
    assert sum(map(core.occupied,core.ships(after,'Main')))==3
    assert len(core.get(core.player(after,'Main'),'PersistentPlayerBases'))==3
    assert len(repair.linked_builds(after,'Main',2))==1
    for i in range(12):
        if i!=2:assert core.ships(after,'Main')[i]==before_ships[i],i
    assert d.get_current_base_identifiers().user_data==2
    base=core.get(core.player(after,'Main'),'PersistentPlayerBases')[repair.linked_builds(after,'Main',2)[0]]
    assert len(core.get(base,'Objects'))==3
    results.append(dict(test='overwrite',optimized=optimized,repeat=repeat,ship_slots=12,occupied=3,builds=3,selected_slot=3))

try:
    bpy.context.scene.nms_main.new_file()
    for i,part in enumerate(('B_COK_A','BUILDFLATPANEL','BUILDWALL')):
        obj=builder.add_part(part,high_res=False,user_data=0).object;obj.location=(i*4,0,0)
    bpy.context.scene.nms_base_tool.string_base='Spaceman'
    for optimized in (False,True):
        write(fixture());select()
        for repeat in range(4):run_export(optimized,repeat)
        # Real .blend save/reopen and production load handlers keep the local destination.
        project=folder/f'roundtrip-{optimized}.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(project))
        bpy.ops.wm.open_mainfile(filepath=str(project))
        d=bpy.context.scene.nms_save_data
        assert d.get_current_base_identifiers().user_data==2
        assert json.loads(bpy.context.scene['bbe_ship_export_origin'])['index']==2
        run_export(optimized,'after_blend_reopen')
        # Same build in slot 5, then overwrite slot 3: do not silently remove or modify 5.
        root=files.SaveFile(paths[0]).load()
        payload,_=repair.rebuild_payload(root,'Main',4,objects=T['base']['Objects'],name='Spaceman',new=True)
        cloned=repair.apply_plan(root,repair.make_plan(root,'Main',4,payload,'FULL'))
        write(cloned);select()
        op=operator(optimized);assert invoke(op)=={'RUNNING_MODAL'}
        op.confirm=True;assert actions.BBE_OT_corvette_export.execute(op,bpy.context)=={'FINISHED'}
        after=files.SaveFile(paths[0]).load()
        assert len(core.get(core.player(after,'Main'),'PersistentPlayerBases'))==4
        assert core.ships(after,'Main')[4]==core.ships(cloned,'Main')[4]
        results.append(dict(test='existing_other_slot_copy_preserved',optimized=optimized,slots=[3,5]))
        for problem,expected in (('eleven_slots','Expected 12 ship slots'),('inactive_expedition','Expected 12 ship slots'),('stale','The save changed')):
            write(fixture(None if problem=='stale' else problem));select()
            if problem=='stale':
                root=files.SaveFile(paths[1]).load();root['QAChangedAfterList']=True
                save=files.SaveFile(paths[1]);save.json_data=root;save.save()
            before=files.hashes(paths);errors.clear()
            assert invoke(operator(optimized))=={'CANCELLED'}
            assert errors and expected in errors[-1],errors
            assert files.hashes(paths)==before
            results.append(dict(test=problem,optimized=optimized,error=errors[-1],writes=False))
        # Multiple builds linked to one slot must require the separate duplicate consent.
        write(fixture('duplicate_link'));select();before=files.hashes(paths)
        op=operator(optimized);assert invoke(op)=={'RUNNING_MODAL'};op.confirm=True
        assert actions.BBE_OT_corvette_export.execute(op,bpy.context)=={'CANCELLED'}
        assert files.hashes(paths)==before
        results.append(dict(test='duplicate_link_blocked',optimized=optimized,writes=False))
    for optimized in (False,True):
        write(fixture());d=select()
        d.nms_base_index='Default'
        op=operator(optimized);assert invoke(op)=={'RUNNING_MODAL'}
        assert op.destination=='CHOOSE' and op.slot=='NONE'
        before=files.hashes(paths)
        op.confirm=True
        assert actions.BBE_OT_corvette_export.execute(op,bpy.context)=={'CANCELLED'}
        assert files.hashes(paths)==before
        results.append(dict(test='no_selection_cannot_export',optimized=optimized,writes=False))
        op=operator(optimized);assert invoke(op)=={'RUNNING_MODAL'}
        op.destination='NEW';op.check(bpy.context)
        assert op.slot=='1' and not op.confirm
        op.confirm=True
        assert actions.BBE_OT_corvette_export.execute(op,bpy.context)=={'FINISHED'},errors
        after=files.SaveFile(paths[0]).load()
        assert sum(map(core.occupied,core.ships(after,'Main')))==4
        assert len(repair.linked_builds(after,'Main',1))==1
        results.append(dict(test='explicit_new_ship',optimized=optimized,slot=2))
        write(fixture());d=select()
        root=files.SaveFile(paths[0]).load()
        core.get(core.player(root,'Main'),'PersistentPlayerBases').reverse()
        write(root);d.refresh_bases_list()
        actual=d.get_current_base_identifiers().user_data
        assert actual==2
        op=operator(optimized);assert invoke(op)=={'RUNNING_MODAL'}
        results.append(dict(test='refresh_after_build_list_reorder',optimized=optimized,selected_before=3,selected_after=actual+1,export_slot=int(op.slot)+1))
        assert op._index==2
        op.cancel(bpy.context)
        for remaining in ('missing','ambiguous'):
            write(fixture());d=select()
            root=files.SaveFile(paths[0]).load()
            bases=core.get(core.player(root,'Main'),'PersistentPlayerBases')
            if remaining=='missing': bases.pop(2)
            else: bases.append(copy.deepcopy(bases[2]))
            write(root);d.refresh_bases_list()
            assert d.get_current_base_identifiers() is None and d.nms_base_index=='Default'
            assert d.session_status
            results.append(dict(test='refresh_'+remaining+'_clears_selection',optimized=optimized))
        write(fixture());d=select()
        actions.remember_ship_source(bpy.context.scene,paths,'Main',2,'Spaceman')
        op=operator(optimized);assert invoke(op)=={'RUNNING_MODAL'}
        assert not actions.overwrite_warning(op)
        op.confirm=True;op.slot='3';op.check(bpy.context)
        warning=actions.overwrite_warning(op)
        assert warning and any('Horseman' in line for line in warning) and not op.confirm
        op.cancel(bpy.context)
        # Same-name ships in another slot must still trigger the warning.
        root=fixture();core.put(core.ships(root,'Main')[3],'Name','Spaceman');write(root);d=select(3)
        op=operator(optimized);assert invoke(op)=={'RUNNING_MODAL'}
        assert actions.overwrite_warning(op)
        op.cancel(bpy.context)
        actions.remember_ship_source(bpy.context.scene,[folder/'another-save.hg'],'Main',3,'Spaceman')
        op=operator(optimized);assert invoke(op)=={'RUNNING_MODAL'}
        assert any('different save' in line for line in actions.overwrite_warning(op))
        op.cancel(bpy.context)
        results.append(dict(test='different_ship_red_warning',optimized=optimized,same_name=True,different_save=True,confirmation_reset=True))
    write(fixture());d=select()
    assert 'Imported' in d.import_base(bpy.context,d.get_current_base_identifiers(),[str(p) for p in paths])
    assert json.loads(bpy.context.scene['bbe_ship_export_origin'])['index']==2
    addon._clear_build_source(bpy.context.scene)
    assert 'bbe_ship_export_origin' not in bpy.context.scene
    op=operator(False);assert invoke(op)=={'RUNNING_MODAL'}
    assert 'SOURCE UNKNOWN' in actions.overwrite_warning(op)[0]
    op.cancel(bpy.context)
    output=dict(version=addon.ADDON_VERSION,blender=bpy.app.version_string,folder=str(folder),results=results,
                boundaries='Synthetic HG saves only. No live NMS or player saves. Dialog display substituted, real operator invoke/execute and writer.')
    destination=QA/f'ticket011-fixed-{addon.ADDON_VERSION}-{bpy.app.version[0]}{bpy.app.version[1]}.json'
    destination.write_text(json.dumps(output,indent=2))
    print('TICKET011_EXPORTS_PASS',str(destination),flush=True)
finally:
    for p in reversed(patches):p.stop()



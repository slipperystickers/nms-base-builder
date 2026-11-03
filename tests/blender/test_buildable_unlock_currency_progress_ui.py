"""Real dialog and progress repaint test, using only generated HG/account files.

Run factory-startup Blender with --enable-event-simulate. NMS_KUMA_TEST_ADDON
selects source/installed code; BBE_UNLOCK_QA_DIR keeps their outputs separate.
"""
from pathlib import Path
import copy
import hashlib
import json
import os
import sys
import traceback
from types import SimpleNamespace
import bpy
sys.path.insert(0,str(Path(__file__).parent))
from test_support import module,QA as DEFAULT_QA
QA=Path(os.environ.get('BBE_UNLOCK_QA_DIR',str(DEFAULT_QA/'unlock-currency-source')))
QA.mkdir(parents=True,exist_ok=True)
(QA/'tmp').mkdir(exist_ok=True)
bpy.context.preferences.filepaths.temporary_directory=str(QA/'tmp')
bpy.context.preferences.view.show_splash=False
ui=module('save_editor.buildable_unlocks_ui')
progress_ui=module('progress_ui')
save_module=module('save_editor.save_file')
manager=module('save_editor.save_manager')
backups=module('save_editor.backup_policy')
core=ui.core
fixture=QA/'generated-account';fixture.mkdir(exist_ok=True)
backups.settings=lambda:(str(QA/'verified-backups'),20)
# Large unrelated records exercise real parsing, preservation and compression.
payload=[dict(Index=i,Seed=2**63+i,Text='Unrelated fixture data '+str(i),Values=[i%13,.125,-2]) for i in range(65000)]
original_roots={}
for index,filename in enumerate(('save9.hg','save10.hg')):
    root=dict(BaseContext=dict(PlayerStateData=dict(KnownProducts=['^KEEP_PRODUCT'],KnownTech=['^KEEP_TECH'],
                KnownSpecials=['^KEEP_SPECIAL'],Units=1000+index,Nanites=200+index,Specials=30+index,
                Inventory={'Preserve':index})),
              ExpeditionContext=dict(PlayerStateData=dict(KnownProducts=['^SEASON_KEEP'],KnownTech=[],KnownSpecials=[],
                Units=11,Nanites=22,Specials=33)),
              CommonStateData={'SaveName':'Disposable currency UI fixture','SaveUniversalId':'0x123456789ABCDEF0'},
              UnrelatedRecords=payload,Unknown={'Sentinel':index,'Unicode':'星🚀'})
    path=fixture/filename
    save=save_module.SaveFile(path);save.json_data=root;save.save()
    original_roots[str(path.resolve())]=root
account={'UserSettingsData':{field:['^ACCOUNT_KEEP'] for field in core.ACCOUNT_FIELDS},'UnknownAccount':{'Keep':987}}
(fixture/'accountdata.hg').write_bytes(json.dumps(account).encode()+b'\0')
(fixture/'mf_accountdata.hg').write_bytes(b'untouched account metadata fixture')
original_bytes={p.name:p.read_bytes() for p in fixture.glob('*.hg')}
paths=list(original_roots)
manager.SaveManager.get_current_slot_data=lambda self:{'saves':paths}
manager.SaveManager.get_current_base_identifiers=lambda self:SimpleNamespace(save_context='Main')
state={'step':0,'populate_calls':0,'frames':[],'samples':{},'waits':0}
window=bpy.context.window
area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
region=next(r for r in area.regions if r.type=='WINDOW')

def view_context():return bpy.context.temp_override(window=window,area=area,region=region)
original_populate=ui._populate
def counted_populate(*args,**kwargs):
    state['populate_calls']+=1
    return original_populate(*args,**kwargs)
ui._populate=counted_populate
original_draw=ui.BBE_OT_buildable_unlocks.draw
def dialog_draw(self,context):
    state['dialog']=self
    return original_draw(self,context)
ui.BBE_OT_buildable_unlocks.draw=dialog_draw
original_update=progress_ui.Activity.update
def activity_update(self,fraction,detail=None):
    state['samples'].setdefault(self.title,[]).append(float(fraction))
    return original_update(self,fraction,detail)
progress_ui.Activity.update=activity_update
original_redraw=progress_ui.Activity._redraw
def capture_redraw(self,force=False):
    before=self._last_draw
    result=original_redraw(self,force)
    if self._last_draw!=before and self._owns_ui:
        kind='opening' if self.title.startswith('Opening') else 'saving' if self.title.startswith('Saving') else 'other'
        existing=[f for f in state['frames'] if f['kind']==kind]
        if kind!='other' and len(existing)<8:
            path=QA/f'{kind}-progress-{len(existing):02}.png'
            with view_context():bpy.ops.screen.screenshot(filepath=str(path))
            state['frames'].append(dict(kind=kind,fraction=self.fraction,detail=self.detail,path=str(path)))
    return result
progress_ui.Activity._redraw=capture_redraw

def finish(passed,error=''):
    result={key:value for key,value in state.items() if key not in ('dialog','selected_row')}
    result.update(status='PASS' if passed else 'FAIL',error=error,addon=str(Path(ui.__file__).parents[1]),
                  only_generated_save_files=True,requested_balances={'Units':4294967295,'Nanites':654321,'Quicksilver':123456})
    (QA/'result.json').write_text(json.dumps(result,indent=2))
    print('UNLOCK_CURRENCY_PROGRESS_UI_'+result['status'],error,flush=True)
    bpy.ops.wm.quit_blender()

def run():
    try:
        step=state['step']
        if step==0:
            with view_context():
                assert bpy.ops.bbe.buildable_unlocks('INVOKE_DEFAULT')=={'RUNNING_MODAL'}
            assert state['populate_calls']==1, 'Opening populated the full catalogue more than once'
            assert {p.name:p.read_bytes() for p in fixture.glob('*.hg')}==original_bytes
            assert progress_ui._active is None
        elif step==1:
            review=ui._state(bpy.context)
            assert ui.SESSION and len(review.currencies)==3 and not any(row.selected for row in review.currencies)
            assert all(row.mixed for row in review.currencies)
            with view_context():bpy.ops.screen.screenshot(filepath=str(QA/'currency-dialog-before.png'))
            requested={'Units':'4,294,967,295','Nanites':'654,321','Quicksilver':'123,456'}
            for row in review.currencies:
                row.selected=True;row.amount=requested[row.name]
            reward=next(row for row in review.items if row.supported and row.account_reward and not row.already_known)
            reward.selected=True
            review.active=list(review.items).index(reward)
            state['selected_reward_key']=reward.item_key
            state['dialog'].game_closed=True  # Generated fixtures only; never a live destination.
            area.tag_redraw()
        elif step==2:
            with view_context():bpy.ops.screen.screenshot(filepath=str(QA/'currency-dialog-ready.png'))
            window.event_simulate(type='RET',value='PRESS',x=region.x+region.width//2,y=region.y+region.height//2)
            window.event_simulate(type='RET',value='RELEASE',x=region.x+region.width//2,y=region.y+region.height//2)
        elif step==3:
            if ui.SESSION is not None:
                state['waits']+=1
                if state['waits']<5:return 1
                raise AssertionError('Apply did not close the dialog')
            assert progress_ui._active is None
            for path,original in original_roots.items():
                actual=save_module.SaveFile(path).load()
                assert {name:core.currency_value(actual,'Main',name) for name in core.CURRENCY_FIELDS}=={
                    'Units':4294967295,'Nanites':654321,'Quicksilver':123456}
                assert actual['ExpeditionContext']==original['ExpeditionContext']
                assert actual['UnrelatedRecords']==original['UnrelatedRecords'] and actual['Unknown']==original['Unknown']
                assert actual['BaseContext']['PlayerStateData']['Inventory']==original['BaseContext']['PlayerStateData']['Inventory']
                assert '^KEEP_PRODUCT' in actual['BaseContext']['PlayerStateData']['KnownProducts']
            actual_account=json.loads((fixture/'accountdata.hg').read_bytes().rstrip(b'\0'))
            assert actual_account['UnknownAccount']==account['UnknownAccount']
            assert (fixture/'mf_accountdata.hg').read_bytes()==original_bytes['mf_accountdata.hg']
            copies=[p for p in (QA/'verified-backups').rglob('*.hg')]
            assert len(copies)>=4
            assert all(p.read_bytes()==original_bytes[p.name] for p in copies)
            for kind in ('opening','saving'):
                frames=[f for f in state['frames'] if f['kind']==kind]
                assert frames and any(0<f['fraction']<1 for f in frames), (kind,frames)
            for samples in state['samples'].values():
                assert samples==sorted(samples) and samples[-1]==1.,samples
            state['backup_files_verified']=len(copies)
            state['all_unrelated_data_preserved']=True
            finish(True);return None
        state['step']+=1
        return 1
    except Exception as error:
        traceback.print_exc();finish(False,str(error));return None
bpy.app.timers.register(run,first_interval=2)

"""Promote audited native assets into source, preserving every existing catalogue row."""
from pathlib import Path
import csv, hashlib, json, re, shutil
from PIL import Image
REPO=Path(__file__).resolve().parents[1]
ADDON=REPO/'src/addons/no_mans_sky_base_builder'
AUDIT=Path(r'C:\Users\kengo\OneDrive\Desktop\NMS\outputs\nms-update-20261028')
BUILT=AUDIT/'built'
def main():
    assert json.loads((BUILT/'asset-failures.json').read_text())=={}
    source=json.loads((AUDIT/'new-objects.json').read_text())
    ready=json.loads((BUILT/'asset-audit.json').read_text())
    overrides_path=ADDON/'resources/catalog_icon_overrides.json'
    icon_overrides=json.loads(overrides_path.read_text())['icons'] if overrides_path.exists() else {}
    path=ADDON/'resources/DT_PartDefinition.csv'
    rows=list(csv.DictReader(path.open(encoding='utf-16',newline='')));fields=list(rows[0]);existing={r['---']:r for r in rows}
    names=json.loads((ADDON/'resources/nice_names.json').read_text())
    added=[]
    for row in source:
        pid=row['id']
        if pid not in ready:continue
        # GroupID is the game's explicit variant root. FamilyIds overlap
        # between unrelated styles (Hornet/Viper/Mantis, Basilisk/Reaper), so
        # using them here mixed different parts in the same popup.
        native_root=row['groupId']
        if native_root and native_root in ready:
            parent=native_root if native_root!=pid else None
            visible=parent is None
        else:
            parent=None
            visible=row['menuVisible']
        category='Corvette';sub='Hull Plating';template='B_STR_AB_NE'
        for prefix,subcat,ref in [('B_COK','Cockpits and Habitation Modules','B_COK_A'),('B_HAB','Cockpits and Habitation Modules','B_HAB_A'),('B_CON','Hull Connectors','B_CON_15'),('B_DECO','Exterior Decoration','B_DECO_T'),('B_GEN','Reactors','B_GEN_5'),('B_TUR','Defensive Systems','B_TUR_A'),('B_TRU','Thrusters','B_TRU_A'),('B_WNG','Wings','B_WNG_A'),('B_WALL','Utility Modules','B_WALL_PLAN0')]:
            if pid.startswith(prefix):sub=subcat;template=ref;break
        if pid.startswith('GRAV_'):category='Technology';sub='Gravity';template='GRAVPLANT'
        ref=existing.get('^'+template,{})
        title=row['name'].strip()
        if title==row['nameKey'] and title.startswith(('UI_','BLD_')):
            # Native records without a localized name remain importable but are
            # not advertised as released build-menu items.
            title=pid;visible=False;parent='B_WALL_PLAN0' if 'CANT' in pid else 'B_WALL_WIND2'
        if pid.startswith('B_STR_'):title+=' ('+pid.split('_',3)[-1].replace('_',' ')+')'
        if pid.startswith('B_WNG_') and pid.count('_')>2:title+=' ('+pid.rsplit('_',1)[-1]+')'
        data={field:ref.get(field,'') for field in fields}
        data.update({'---':'^'+pid,'ObjectModel':f"/Script/Engine.StaticMesh'/Game/NMSBaseBuilder/Features/Models_FBX/{pid}.{pid}'",
            'Icon':f"/Script/Engine.Texture2D'/Game/NMSBaseBuilder/Features/UI/Icons/{pid}.{pid}'",
            'Category':category,'SubCategory':sub,'NiceName':title.upper(),'bShowInDrawer':str(visible),
            'VariantOf':'^'+parent if parent else 'None','bIncludeMessage':'False','bFossilPart':'False'})
        if '^'+pid not in existing:rows.append(data)
        else:rows[rows.index(existing['^'+pid])]=data
        names[pid]=title
        for folder,destination in [('assets',ADDON/'resources/hd_additions/assets'),('simple',ADDON/'models-simple'),('icons',ADDON/'images/asset_icons')]:
            destination.mkdir(parents=True,exist_ok=True)
            suffix='.png' if folder=='icons' else '.blend'
            native_icon=AUDIT/'native'/row['icon'].replace('\\','/').lower()
            if folder=='icons' and pid in icon_overrides:
                current=destination/(pid+suffix)
                assert hashlib.sha256(current.read_bytes()).hexdigest()==icon_overrides[pid]['pngSha256'],pid
            elif folder=='icons' and native_icon.is_file():
                # Preserve authored colors/camera/full mip zero; generated art is fallback only.
                Image.open(native_icon).convert('RGBA').save(destination/(pid+suffix),optimize=True)
            else:
                shutil.copy2(BUILT/folder/(pid+suffix),destination/(pid+suffix))
        added.append(dict(id=pid,name=title,visible=visible,parent=parent,category=category,subcategory=sub,
                          nativePlacement=row['placementScene'],nativeComponents=row['components']))
    with path.open('w',encoding='utf-16',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    (ADDON/'resources/nice_names.json').write_text(json.dumps(names,indent=4)+'\n',encoding='utf-8')
    textures=json.loads((BUILT/'used-textures.json').read_text())
    destination=ADDON/'resources/hd_additions/textures';destination.mkdir(parents=True,exist_ok=True)
    for name in textures:shutil.copy2(BUILT/'textures'/name,destination/name)
    manifest={'gameBuild':26271400,'gameVersion':'7.10','assets':added,'textures':textures,
        'excluded':{'B_LND_D':'Native model LANDINGGEAR_LEG_D is absent from installed game archives.',
                    'B_TRU_I':'Native model ZENGINEI is absent from installed game archives.'}}
    (ADDON/'resources/forsaken_assets.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('Catalogue assets',len(added),'visible families',sum(x['visible'] for x in added),'textures',len(textures))
if __name__=='__main__':main()

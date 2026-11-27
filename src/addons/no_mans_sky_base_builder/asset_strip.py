"""Optional single-row catalogue. First-party presentation with builder bindings.

No permanent modal observer and no native header resizing. Only visible thumbnails
become textures; the viewport menu handlers draw and receive input above this strip.
"""
import json, time, textwrap, blf
from functools import lru_cache
from pathlib import Path
import bpy, gpu
from bpy.app.handlers import persistent
from . import styled_ui as art, curve_widgets as paint, i18n

PLUS=__package__.endswith('bbe_plus')
PREFIX='bbeplus' if PLUS else 'bbe'
if not PLUS:
    from . import asset_weights
    from .utils import new_assets
_states={}
_handlers=[]
_keymaps=[]
_saved=None
PREFAB_CATEGORY = 'Presets / Prefabs'
PREFAB_PREFIX = 'prefab:'
_catalogue_cache = (None, None, None)
_search_cache = (None, None, ())

def key(context):return (context.window.as_pointer(),context.area.as_pointer())
def settings():
    global _saved
    if _saved is None:
        try:_saved=json.loads((Path(bpy.utils.user_resource('CONFIG'))/(PREFIX+'-asset-strip.json')).read_text())
        except (OSError,ValueError):_saved={}
    return _saved

def save(state):
    values={k:state[k] for k in ('height','category','group','enabled')}
    values['layout_version']=2
    settings().update(values)
    path=Path(bpy.utils.user_resource('CONFIG'))/(PREFIX+'-asset-strip.json')
    try:path.write_text(json.dumps(values),encoding='utf8')
    except OSError:pass

def catalogue(context):
    global _catalogue_cache
    if PLUS:
        from . import gallery
        return gallery.index()
    browser = context.scene.nms_asset_browser
    categories = browser.get_categories_data()
    presets = browser.get_preset_data()
    previous_categories, previous_presets, combined = _catalogue_cache
    if categories is not previous_categories or presets is not previous_presets:
        from .preset import Preset
        root = Path(Preset.PRESET_PATH)
        groups = {}
        for name in sorted(presets, key=str.casefold):
            info = presets[name]
            folder = Path(info['link']).parent
            label = 'Uncategorized Prefabs' if folder == root else folder.name.replace('_', ' ')
            groups.setdefault(label, {})[PREFAB_PREFIX + name] = info
        combined = {**categories, PREFAB_CATEGORY: groups}
        _catalogue_cache = (categories, presets, combined)
    return combined

def preview(part):
    if PLUS:
        from . import gallery
        return gallery.preview(part)
    from . import icons
    return icons.get_asset_icons_pcoll().get(part)

def place(context,part):
    if PLUS:return bpy.ops.bbeplus.place('EXEC_DEFAULT',part=part)
    if part.startswith(PREFAB_PREFIX):
        return bpy.ops.object.nms_asset_browser_object_selected(
            'EXEC_DEFAULT', object_id=part[len(PREFAB_PREFIX):], is_preset=True)
    return bpy.ops.object.nms_asset_browser_object_selected('EXEC_DEFAULT',object_id=part)

def show_options(context, state, part):
    from .tools.asset_browser_grid import show_asset_options
    info = next(info for pid, info, _ in state['cards'] if pid == part)
    object_id = part.removeprefix(PREFAB_PREFIX) if info.get('is_preset') else part
    if not info.get('is_preset'):
        new_assets.record_click(context, object_id)
    hover(context, state, '')
    show_asset_options(context, object_id, info, horizontal=True)
    context.area.tag_redraw()


def snapping(toggle=False):
    if PLUS:
        from . import gallery as backend
    else:
        from .utils import asset_browser_utils as backend
    return backend.toggle_auto_snap() if toggle else backend.auto_snap_enabled()

def title(part,info):
    if info.get('is_preset'):return info['name']
    return i18n.part_names().get(part) or info.get('name') or info.get('Name') or part

def card_title(state, part, info):
    label=str(title(part,info))
    if state.get('family') and state['family']!=part:
        parent,metadata=state['items'][0]
        root=str(title(parent,metadata))
        from .asset_families import variant_label
        return variant_label(root, label)
    return label

def hints(part,info):
    if info.get('is_preset'):return [info['name'], i18n.tooltip('Local prefab')]
    from . import part_stats
    lines=[str(title(part,info)),str(part)]
    description=info.get('description') or info.get('Description')
    if isinstance(description,str):lines.extend(description.splitlines())
    lines.extend(part_stats.lines(part))
    return [i18n.tooltip(line) for line in lines]

def cursor(context,state,resize):
    if not resize and not state.get('resize_cursor',False):return
    # A normal regional cursor lets Blender restore its own cursor when the
    # pointer leaves the viewport (a modal cursor would leak over other editors).
    context.window.cursor_set('SCROLL_Y' if resize else 'DEFAULT')
    state['resize_cursor']=resize

def hover(context,state,hit):
    hit=hit or ''
    if hit==state.get('hover'):return False
    state['hover']=hit;state['hover_since']=time.monotonic()
    if hit:
        # One redraw after the hover delay, never an idle polling timer.
        area=context.area;stamp=state['hover_since']
        def redraw():
            if state.get('enabled') and state.get('hover_since')==stamp:
                try:area.tag_redraw()
                except ReferenceError:pass
        bpy.app.timers.register(redraw,first_interval=.5)
    return True

def clear_hover(window, area):
    state = _states.get((window.as_pointer(), area.as_pointer()))
    if state and state.get('hover'):
        state['hover'] = ''
        area.tag_redraw()

def visible(context):
    if not context.space_data.show_region_header or not context.space_data.show_region_tool_header:
        return False
    from . import toolbar_surface
    return key(context) in toolbar_surface._records and bool(toolbar_surface.nodes(toolbar_surface._records[key(context)]))

@lru_cache(maxsize=128)
def sorted_choices(values, locale):
    return tuple(sorted(values, key=lambda value: (i18n.for_locale(locale, value).casefold(), value)))


def _search_rows(tree, locale):
    global _search_cache
    previous_tree, previous_locale, rows = _search_cache
    if tree is previous_tree and locale == previous_locale:
        return rows
    labels = i18n.part_names()
    rows = []
    for category, sections in tree.items():
        for group, parts in sections.items():
            if category != PREFAB_CATEGORY and group in {'ALL', 'All'}:
                continue
            for part, info in parts.items():
                name = str(info.get('name') or info.get('Name') or '')
                text = ' '.join((part, name, labels.get(part, ''), category, group))
                rows.append((part, info, text.casefold()))
    _search_cache = (tree, locale, rows)
    return rows


def refresh(context,state):
    if state.get('family'):
        return state['items']
    tree=catalogue(context)
    if state.get('catalogue_source') is not tree:
        state.update(catalogue_source=tree, signature=None, search_signature=None)
    query=state.get('search','').casefold().split()
    searching=bool(query)
    if searching!=state.get('search_active',False):
        state['scroll']=0 if searching else state.get('browse_scroll',0)
        state['signature']=None
    state['search_active']=searching
    locale=i18n.interface_locale()
    cats=sorted_choices(tuple(tree),locale)
    if not cats:
        state.update(categories=[],groups=[],items=[])
        return []
    if state['category'] not in tree:state['category']=cats[0]
    groups=tree[state['category']]
    names=sorted_choices(tuple(v for v in groups if state['category']==PREFAB_CATEGORY or v not in {'ALL','All'}),locale)
    state.update(categories=cats, groups=names)
    if names and state['group'] not in names:
        state['group']=names[0]
        state['scroll']=0
    if not names:
        state['group']=''
        if not searching:
            state.update(items=[], signature=None)
            return []
    if searching:
        signature=(context.scene.as_pointer(),id(tree),tuple(query),locale)
        if signature!=state.get('search_signature'):
            matches = {}
            first, *other_terms = query
            for part, info, text in _search_rows(tree, locale):
                if first in text and (not other_terms or all(term in text for term in other_terms)):
                    matches.setdefault(part, info)
            state.update(search_items=list(matches.items()),search_signature=signature)
        state['items']=state['search_items']
        return state['items']
    signature=(context.scene.as_pointer(),state['category'],state['group'],len(groups[state['group']]))
    if signature!=state.get('signature'):
        state['items']=list(groups[state['group']].items());state['signature']=signature
    return state['items']

def open_variants(state, part, info):
    from .asset_families import family_parts
    state.update(family=part, return_scroll=state['scroll'], scroll=0, hover='',
                 choice=None, editing=False, items=list(family_parts(part, info).items()))


def close_variants(state):
    if state.pop('family', None):
        state.update(scroll=state.pop('return_scroll'), signature=None, hover='')

def corner_button(card, size, inset, floating, *, right=False):
    x, y, w, h = card
    bx = x+w-size-inset if right else x+inset
    by = y+h-size
    for _, (cx, cy, cw, ch) in floating:
        if bx < cx+cw and bx+size > cx and by < cy+ch and by+size > cy:
            by = cy-size
    return (bx, by, size, size)


def geometry(context,state):
    r=context.region;s=context.preferences.system.ui_scale
    left=8*s;right=r.width-8*s
    for region in context.area.regions:
        if region.type=='TOOLS' and region.width>1 and context.space_data.show_region_toolbar:left=max(left,region.width+6*s)
        if region.type=='UI' and region.width>1 and context.space_data.show_region_ui:right=min(right,region.x-r.x-8*s)
    if context.space_data.show_gizmo_navigate:right-=88*s
    # Share the header's measured button bounds, not a guessed mouse anchor.
    from . import toolbar_surface
    bounds=[rect for node,rect in toolbar_surface._bounds.get((*key(context),'TOOL_HEADER'),[]) if node.options.get('identifier')!=toolbar_surface.HeaderScroll.bl_idname]
    if bounds:
        first=min(rect[0] for rect in bounds)-r.x
        last=max(rect[0]+rect[2] for rect in bounds)-r.x
        state['header_span']=(first,last)
    # A native transform readout temporarily replaces the header buttons.
    # Keep the strip anchored while their interactive bounds are empty.
    if 'header_span' in state:
        first,last=state['header_span']
        desired=min(right-left,last-first)
        left=max(left,min((first+last-desired)/2,right-desired));right=left+desired
    width=max(100,right-left)
    default_icon=max(24*s,(width-52*s)/10-12*s)
    height=max(96*s,min(268*s,state['height']*s)) if state.get('height') is not None else default_icon+74*s
    top=r.height
    # Blender's overlapping tool header occupies part of the WINDOW region.
    # Anchor below its real lower edge, not the WINDOW region's upper edge.
    for region in context.area.regions:
        if region.type in {'HEADER','TOOL_HEADER'} and region.y-r.y>r.height/2:
            top=min(top,region.y-r.y)
    bottom=top-height;icon=max(24*s,height-74*s)
    tile=icon+12*s;columns=max(1,int((width-52*s+1e-5)//tile))
    items=refresh(context,state);maximum=max(0,len(items)-columns)
    state['scroll']=max(0,min(maximum,int(state['scroll'])))
    if not state['search_active'] and not state.get('family'):state['browse_scroll']=state['scroll']
    floating=[('auto_snap',(right-142*s,top-26*s,132*s,23*s))]
    if not PLUS and state['category']==PREFAB_CATEGORY and not state['search_active'] and not state.get('family'):
        stacked = width < 285*s
        preview_rect = (right-(142 if stacked else 277)*s,
                        top-(52 if stacked else 26)*s, 132*s, 23*s)
        floating.append(('prefab_previews', preview_rect))
    if state.get('family'):
        label=i18n.interface('Close variants')
        blf.size(0,11*s)
        floating.append(('close_variants',(left+4*s,top-26*s,blf.dimensions(0,label)[0]+34*s,23*s)))
    targets=[];cards=[]
    for column,(part,info) in enumerate(items[state['scroll']:state['scroll']+columns]):
        rect=(left+26*s+column*tile,top-icon-25*s,tile-4*s,icon+21*s)
        cards.append((part,info,rect));targets.append(('part:'+part,rect))
        if not PLUS and not info.get('is_preset'):
            targets.append(('weight:'+part, asset_weights.meter_bounds(rect[0],rect[1],rect[2],s)))
        has_variants = bool(info.get('variants')) and not state.get('family')
        size = min(21*s, (rect[2]-2*s)/2) if has_variants else 21*s
        if not PLUS:
            targets.append(('options:'+part, corner_button(rect, size, s, floating)))
        if has_variants:
            targets.append(('variants:'+part, corner_button(rect, size, s, floating, right=True)))
    row_y=bottom+11*s
    blf.size(0,11*s)
    widths=[]
    for label,names in (('Category: ',state['categories']),('Subcategory: ',state['groups'])):
        widths.append(min(width*(.30 if width<650*s else .38),max([blf.dimensions(0,i18n.interface(label+v))[0]+30*s for v in names] or [120*s])))
    search_x=left+20*s+sum(widths)
    targets.extend([('category',(left+8*s,row_y,widths[0],25*s)),
                    ('group',(left+14*s+widths[0],row_y,widths[1],25*s)),
                    ('search',(search_x,row_y,max(40*s,min(300*s,right-34*s-search_x)),25*s)),
                    ('close',(right-26*s,row_y,20*s,25*s)),
                    ('previous',(left+2*s,top-icon-20*s,22*s,icon)),
                    ('next',(right-24*s,top-icon-20*s,22*s,icon)),
                    ('resize',(left,bottom-3*s,width,10*s)),
                    ('scroll',(left+28*s,bottom+40*s,max(20,width-56*s),6*s))])
    targets.extend(floating)
    legend_height = 14*s if any(key.startswith('weight:') for key, _ in targets) else 0
    if legend_height:
        targets = [(key, (x, y-legend_height, w, h) if key=='resize' else (x,y,w,h))
                   for key,(x,y,w,h) in targets]
    state['legend_height'] = legend_height
    state.update(bounds=(left,bottom-legend_height,width,height+legend_height),targets=targets,cards=cards,maximum=maximum,columns=columns,scale=s)
    if state.get('search'):
        x,y,w,h=next(rect for action,rect in targets if action=='search')
        targets.append(('clear_search',(x+w-22*s,y,22*s,h)))
    if state.get('choice'):
        name=state['choice'];values=state['categories' if name=='category' else 'groups']
        anchor=next(rect for action,rect in targets if action==name)
        count=min(10,len(values),max(1,int((anchor[1]-14*s)/(26*s))))
        maximum=len(values)-count
        offset=state.get('choice_scroll')
        if offset is None:
            offset=values.index(state[name]) - count//2 if state[name] in values else 0
        state['choice_scroll']=max(0,min(offset,maximum))
        x,y,w,h=anchor;state['choice_bounds']=(x,y-count*26*s,w,count*26*s)
        gutter=16*s if maximum else 0
        for i,value in enumerate(values[state['choice_scroll']:state['choice_scroll']+count]):
            targets.append(('choose:'+value,(x,y-(i+1)*26*s,w-gutter,26*s)))
        if maximum:
            height=count*26*s
            thumb=min(height-2*s,max(14*s,height*count/len(values)))
            track=(x+w-gutter,y-height,gutter,height)
            top=y-(height-thumb)*state['choice_scroll']/maximum
            state['choice_max']=maximum
            targets.extend([('choice_track',track),('choice_thumb',(track[0],top-thumb,gutter,thumb))])
    return state

def inside(rect,x,y):
    a,b,w,h=rect;return a<=x<=a+w and b<=y<=b+h

def state_for(context):
    saved=settings()
    return _states.setdefault(key(context),dict(enabled=saved.get('enabled',False),
        height=saved.get('height') if saved.get('layout_version')==2 else None,
        category=saved.get('category',''),group=saved.get('group',''),scroll=0,hover='',search=''))

def draw():
    ctx=bpy.context
    if not ctx.area or not ctx.window or ctx.region.type!='WINDOW':return
    state=state_for(ctx)
    if not state or not state['enabled'] or not visible(ctx):return
    from . import menu_surface
    if ctx.area.as_pointer() in menu_surface._sessions:
        state['hover']='';cursor(ctx,state,False)
    state=geometry(ctx,state);s=state['scale'];x,y,w,h=state['bounds']
    shader=gpu.shader.from_builtin('UNIFORM_COLOR');art.theme(ctx)
    with paint.canvas(ctx):
        paint.rounded(shader,x,y,w,h,8*s,art.INK)
        for part,info,rect in state['cards']:
            px,py,pw,ph=rect
            hot=state.get('hover')=='part:'+part
            fill = art.HOVER if hot else art.SURFACE
            if not PLUS and not info.get('is_preset') and new_assets.is_new(part):
                edge = max(2, 2*s)
                paint.rounded(shader,px,py,pw,ph,5*s,new_assets.YELLOW)
                paint.rounded(shader,px+edge,py+edge,pw-2*edge,ph-2*edge,3*s,fill)
            else:
                paint.rounded(shader,px,py,pw,ph,5*s,fill)
            if info.get('is_preset'):
                from . import prefab_thumbnails
                thumbnail = prefab_thumbnails.get(info['name'], info['link'])
                if thumbnail is None:
                    size = min(24*s, pw-8*s, ph-24*s)
                    art.image(art.icon('package'), px+(pw-size)/2, py+(ph+18*s-size)/2, size, size)
                else:
                    art.image(thumbnail,px+4*s,py+21*s,pw-8*s,ph-24*s)
            else:
                art.image(preview(part),px+4*s,py+21*s,pw-8*s,ph-24*s)
            name=card_title(state,part,info)
            display_name = name if info.get('is_preset') else i18n.interface(str(name))
            paint.text(art.trim(display_name,pw-8*s,10*s),px+pw/2,py+8*s,10*s,art.TEXT,align='CENTER')
        state['legend_bounds'] = (asset_weights.draw_key(x+10*s,y+6*s,w-20*s,s,art.MUTED)
                                  if state.get('legend_height') else None)
        for action,rect in state['targets']:
            px,py,pw,ph=rect
            if action.startswith('part:'):continue
            if action.startswith('weight:'):
                asset_weights.draw_meter(px,py,pw,ph,s,action[7:])
            elif action in {'category','group'}:
                paint.rounded(shader,px,py,pw,ph,5*s,art.EDGE)
                paint.rounded(shader,px+s,py+s,pw-2*s,ph-2*s,4*s,art.SURFACE)
                searching=state.get('search_active',False)
                label=('All categories' if action=='category' else 'All subcategories') if searching else ('Category: ' if action=='category' else 'Subcategory: ')+state[action]
                paint.text(art.trim(i18n.interface(label),pw-24*s,11*s),px+7*s,py+8*s,11*s,art.MUTED if searching else art.TEXT)
                if not searching:paint.text('⌄',px+pw-14*s,py+8*s,12*s,art.TEXT)
            elif action=='search':
                focused=state.get('editing',False)
                paint.rounded(shader,px,py,pw,ph,5*s,art.ACCENT if focused else art.EDGE)
                paint.rounded(shader,px+s,py+s,pw-2*s,ph-2*s,4*s,art.SURFACE)
                value=state.get('search','')
                display=art.trim(value,pw-32*s,11*s) if value else i18n.interface('Search assets…')
                if focused and state.get('select_all') and value:
                    paint.rounded(shader,px+5*s,py+3*s,min(pw-30*s,blf.dimensions(0,display)[0]+4*s),ph-6*s,2*s,art.HOVER)
                paint.text(display,px+7*s,py+8*s,11*s,art.TEXT if value else art.MUTED)
                if focused and not state.get('select_all'):
                    blf.size(0,11*s);cx=px+7*s+min(pw-34*s,blf.dimensions(0,value[:state.get('caret',len(value))])[0])
                    paint.line(shader,(cx,py+4*s),(cx,py+ph-4*s),s,art.TEXT)
            elif action.startswith('options:'):
                if state.get('hover') == action:
                    paint.rounded(shader,px,py,pw,ph,3*s,art.HOVER)
                for offset in (-4,0,4):
                    cy=py+ph/2+offset*s
                    paint.line(shader,(px+pw/2-5*s,cy),(px+pw/2+5*s,cy),s,art.TEXT)
            elif action.startswith('variants:') or action=='close_variants':
                back=action=='close_variants'
                hot=state.get('hover')==action
                paint.rounded(shader,px,py,pw,ph,5*s,art.ACCENT if back else art.HOVER if hot else art.EDGE)
                for dx in (7,13):
                    paint.line(shader,(px+dx*s,py+6*s),(px+dx*s,py+ph-6*s),2*s,art.TEXT)
                if back:
                    paint.text(i18n.interface('Close variants'),px+22*s,py+7*s,11*s,art.TEXT)
            elif action in {'auto_snap','prefab_previews'}:
                if action=='prefab_previews':
                    from . import prefab_thumbnails
                    enabled=prefab_thumbnails.enabled()
                    label='Prefab Previews'
                else:
                    enabled=snapping()
                    label='Auto-snap'
                hot=state.get('hover')==action
                paint.rounded(shader,px,py,pw,ph,5*s,art.HOVER if hot else art.SURFACE)
                paint.text(art.trim(i18n.interface(label),pw-48*s,11*s),px+7*s,py+7*s,11*s,art.TEXT)
                tx=px+pw-37*s
                paint.rounded(shader,tx,py+4*s,30*s,15*s,7.5*s,art.ACCENT if enabled else art.EDGE)
                paint.disc(shader,tx+(22 if enabled else 8)*s,py+11.5*s,5.5*s,art.TEXT)
            elif action in {'previous','next','close','clear_search'}:
                paint.text({'previous':'‹','next':'›','close':'×','clear_search':'×'}[action],px+pw/2,py+ph/2-5*s,18*s,art.TEXT,align='CENTER')
            elif action=='resize':
                paint.line(shader,(px+pw/2-26*s,py+4*s),(px+pw/2+26*s,py+4*s),2*s,art.ACCENT)
            elif action=='scroll':
                paint.rounded(shader,px,py,pw,ph,3*s,art.SURFACE)
                fraction=state['columns']/max(state['columns'],len(state.get('items',[])))
                thumb=max(24*s,pw*fraction);position=(pw-thumb)*state['scroll']/max(1,state['maximum'])
                paint.rounded(shader,px+position,py,thumb,ph,3*s,art.ACCENT)
            elif action in {'choice_track','choice_thumb'}:
                is_thumb=action=='choice_thumb'
                if not is_thumb:paint.rounded(shader,px,py,pw,ph,0,art.SURFACE)
                inset=(3 if is_thumb else 4)*s
                color=art.TEXT if is_thumb and state.get('hover')==action else art.MUTED if is_thumb else art.EDGE
                paint.rounded(shader,px+inset,py,pw-2*inset,ph,4*s,color)
            elif action.startswith('choose:'):
                paint.rounded(shader,px,py,pw,ph,0,art.HOVER if state.get('hover')==action else art.SURFACE)
                paint.text(art.trim(i18n.interface(action[7:]),pw-12*s,11*s),px+6*s,py+8*s,11*s,art.TEXT)
        if not state['items']:
            empty = 'No local prefabs yet' if state['category']==PREFAB_CATEGORY and not state['search_active'] else 'No matching assets'
            paint.text(i18n.interface(empty),x+w/2,y+h/2,12*s,art.MUTED,align='CENTER')
        if state.get('hover') and not state.get('editing') and not state.get('choice') and time.monotonic()-state.get('hover_since',0)>.45:
            action=state['hover'];lines=[]
            if action.startswith('part:'):
                part=action[5:];info=next((info for p,info in state['items'] if p==part),{})
                lines=hints(part,info)
            elif action.startswith('weight:'):
                lines = asset_weights.lines(action[7:])
            elif action == 'impact_legend':
                lines = asset_weights.legend_lines()
            elif action.startswith('options:'):
                lines=[i18n.tooltip('Show more options')]
            elif action.startswith('variants:'):
                part=action.partition(':')[2]
                info=next((data for pid,data,_ in state['cards'] if pid==part),{})
                lines=[i18n.tooltip('Show variants')+' · '+str(title(part,info))]
            elif action=='close_variants':
                lines=[i18n.tooltip('Return to the previous asset row')]
            else:
                tip={'resize':'Drag to resize the asset row and icons', 'auto_snap':'Automatically snap new parts to the selected part. Shared with the other asset browsers.',
                     'prefab_previews':'Generate and display local prefab thumbnails in all asset browsers',
                     'search':'Search all categories together by name or part ID', 'category':'Clear search to browse a category' if state.get('search_active') else 'Choose a category',
                     'group':'Clear search to browse a subcategory' if state.get('search_active') else 'Show one subcategory at a time', 'previous':'Previous assets', 'next':'Next assets', 'scroll':'Drag to scroll sideways',
                     'close':'Hide the horizontal asset browser', 'clear_search':'Clear search'}.get(action)
                if tip:lines=[i18n.tooltip(tip)]
            if lines:
                tw=min(w-16*s,380*s);chars=max(12,int((tw-16*s)/(6*s)))
                lines=[line for raw in lines for line in textwrap.wrap(raw,chars)]
                th=(len(lines)*17+16)*s
                anchor=next((rect for key_,rect in state['targets'] if key_==action),(x,y,w,h))
                tx=max(x+8*s,min(anchor[0],x+w-tw-8*s));ty=max(8*s,y-th-6*s)
                paint.rounded(shader,tx,ty,tw,th,5*s,art.EDGE)
                paint.rounded(shader,tx+s,ty+s,tw-2*s,th-2*s,4*s,art.INK)
                for i,line in enumerate(lines):paint.text(line,tx+8*s,ty+th-(i+1)*17*s-2*s,11*s,art.TEXT)
                state['tooltip_lines']=lines

class ToggleStrip(bpy.types.Operator):
    bl_idname=PREFIX+'.asset_strip_toggle'
    bl_label='Horizontal Asset Browser'
    bl_description='Show or hide one row of assets under the topbar; drag its lower edge to resize'
    def execute(self,context):
        state=state_for(context)
        state['enabled']=not state['enabled'];state['choice']=None;save(state)
        if not state['enabled']:
            close_variants(state)
            cursor(context,state,False)
        context.area.tag_redraw()
        return {'FINISHED'}

class StripInput(bpy.types.Operator):
    bl_idname=PREFIX+'.asset_strip_input'
    bl_label='Asset Strip Input'
    bl_options={'INTERNAL'}
    @classmethod
    def poll(cls,ctx):
        if not ctx.window or not ctx.area or ctx.area.type!='VIEW_3D' or not ctx.region or ctx.region.type!='WINDOW':return False
        state=_states.get(key(ctx))
        from . import menu_surface
        return bool(state and state['enabled'] and visible(ctx) and ctx.area.as_pointer() not in menu_surface._sessions)
    def invoke(self,context,event):
        self.state=_states[key(context)];self.drag=None;self.menu_press=None
        if event.type == 'RIGHTMOUSE':
            bounds = self.state.get('bounds')
            if not bounds or not inside(bounds,event.mouse_x-context.region.x,event.mouse_y-context.region.y):
                return {'PASS_THROUGH'}
        result=self.handle(context,event)
        if self.menu_press or self.drag or self.state.get('choice') or self.state.get('editing'):
            context.window_manager.modal_handler_add(self);return {'RUNNING_MODAL'}
        return result
    def modal(self,context,event):
        if self.menu_press:
            if event.type in {'ESC','WINDOW_DEACTIVATE'}:
                return {'CANCELLED'}
            if event.type == self.menu_press[1] and event.value == 'RELEASE':
                return self.handle(context,event)
            return {'RUNNING_MODAL'}
        if event.type in {'ESC','RIGHTMOUSE'}:
            self.state['choice']=None;self.state['editing']=False;self.drag=None;cursor(context,self.state,False);context.area.tag_redraw();return {'CANCELLED'}
        result=self.handle(context,event)
        if self.menu_press or self.drag or self.state.get('choice') or self.state.get('editing'):return {'RUNNING_MODAL'}
        return {'FINISHED','PASS_THROUGH'} if result=={'PASS_THROUGH'} else {'FINISHED'}
    def handle(self,context,event):
        state=geometry(context,self.state)
        if state.get('editing') and event.value=='PRESS':
            value=state.get('search','');pos=state.get('caret',len(value));select=state.get('select_all',False)
            changed=False
            if event.type in {'RET','NUMPAD_ENTER','TAB'}:state['editing']=False
            elif event.ctrl and event.type=='A':state['select_all']=True
            elif event.ctrl and event.type=='C':
                if select:context.window_manager.clipboard=value
            elif event.type in {'LEFT_ARROW','RIGHT_ARROW','HOME','END'}:
                state['caret']=0 if event.type=='HOME' else len(value) if event.type=='END' else max(0,min(len(value),pos+(-1 if event.type=='LEFT_ARROW' else 1)))
                state['select_all']=False
            elif event.type in {'BACK_SPACE','DEL'}:
                if select:value='';pos=0
                elif event.type=='BACK_SPACE' and pos:value=value[:pos-1]+value[pos:];pos-=1
                elif event.type=='DEL':value=value[:pos]+value[pos+1:]
                changed=True
            else:
                text=context.window_manager.clipboard if event.ctrl and event.type=='V' else event.unicode if not event.ctrl and not event.alt else ''
                if text:
                    text=' '.join(text.splitlines())
                    if select:value='';pos=0
                    value=value[:pos]+text+value[pos:];pos+=len(text);changed=True
            if changed:
                state.update(search=value[:200],caret=min(pos,200),select_all=False,scroll=0)
            if event.type not in {'LEFTMOUSE','MOUSEMOVE','WHEELUPMOUSE','WHEELDOWNMOUSE'}:
                context.area.tag_redraw();return {'FINISHED'}
        # Keymaps can be evaluated with WINDOW context for a header event.
        # Region-relative event fields may belong to that header; use absolute
        # window coordinates so a menu click never places an asset underneath.
        x,y=event.mouse_x-context.region.x,event.mouse_y-context.region.y;s=state['scale']
        hit=next((action for action,rect in reversed(state['targets']) if inside(rect,x,y)),None)
        if (hit in (None, 'resize') and state.get('legend_height') and state.get('legend_bounds')
                and inside(state['legend_bounds'],x,y)):
            hit = 'impact_legend'
        if self.menu_press:
            part, button = self.menu_press
            self.menu_press = None
            action, _, hovered_part = (hit or '').partition(':')
            if hovered_part == part and (action == 'options' or
                    (button == 'RIGHTMOUSE' and action in {'part','weight','variants'})):
                show_options(context,state,part)
            return {'FINISHED'}
        if self.drag=='choice_thumb':
            if event.type=='MOUSEMOVE':
                self.choice_scroll_to(y)
            elif event.type=='LEFTMOUSE' and event.value=='RELEASE':
                self.drag=None
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        from . import toolbar_surface
        if not self.drag and toolbar_surface.over_header(context.area, event):
            cursor(context,state,False);hover(context,state,'')
            if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                state['editing'] = False
                state['choice'] = None
                context.area.tag_redraw()
            return {'PASS_THROUGH'}
        if event.type=='MOUSEMOVE':
            cursor(context,state,hit=='resize' or self.drag=='resize')
            if self.drag=='resize':state['height']=max(96,min(268,(state['bounds'][1]+state['bounds'][3]-y-state.get('legend_height',0))/s))
            elif self.drag=='scroll':self.scroll_to(x)
            else:
                if not hover(context,state,hit):return {'PASS_THROUGH'}
            context.area.tag_redraw();return {'RUNNING_MODAL'} if self.drag else {'PASS_THROUGH'}
        if event.type=='LEFTMOUSE' and event.value=='RELEASE' and self.drag:
            self.drag=None;cursor(context,state,hit=='resize');save(state);context.area.tag_redraw();return {'FINISHED'}
        if event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE'}:
            step=1 if event.type=='WHEELDOWNMOUSE' else -1
            if state.get('choice'):state['choice_scroll']=max(0,state.get('choice_scroll',0)+step)
            elif inside(state['bounds'],x,y):state['scroll']+=step*max(1,state['columns']//3)
            else:return {'PASS_THROUGH'}
            context.area.tag_redraw();return {'FINISHED'}
        if event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            if not PLUS and hit and hit.startswith(('part:', 'options:', 'variants:', 'weight:')):
                self.menu_press = (hit.partition(':')[2], event.type)
                return {'RUNNING_MODAL'}
            return {'PASS_THROUGH'}
        if event.type!='LEFTMOUSE' or event.value!='PRESS':return {'PASS_THROUGH'}
        state['editing']=hit=='search'
        if hit in {'choice_track','choice_thumb'}:
            thumb=dict(state['targets'])['choice_thumb']
            self.thumb_offset=thumb[1]+thumb[3]-y if hit=='choice_thumb' else thumb[3]/2
            self.drag='choice_thumb'
            self.choice_scroll_to(y)
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if state.get('choice') and not (hit or '').startswith('choose:'):
            state['choice']=None;context.area.tag_redraw();return {'FINISHED'}
        if not hit:return {'PASS_THROUGH'}
        cursor(context,state,hit=='resize')
        if hit.startswith('weight:') or hit == 'impact_legend':
            return {'FINISHED'}
        if hit.startswith('options:'):
            self.menu_press = (hit.partition(':')[2], event.type)
            return {'RUNNING_MODAL'}
        if hit.startswith('variants:'):
            part=hit.partition(':')[2]
            if not PLUS:
                new_assets.record_click(context,part)
            info=next(info for pid,info,_ in state['cards'] if pid==part)
            open_variants(state,part,info)
        elif hit=='close_variants':
            close_variants(state)
        elif hit.startswith('part:'):
            state['choice']=None
            place(context,hit[5:])
        elif hit=='search':
            close_variants(state)
            state.update(editing=True,select_all=True,caret=len(state.get('search','')))
        elif hit=='clear_search':
            close_variants(state)
            state.update(search='',scroll=0,editing=False)
        elif hit=='auto_snap':
            if not snapping(True):self.report({'WARNING'},'Could not save the Auto-snap setting')
        elif hit=='prefab_previews':
            prefs=context.preferences.addons[__package__].preferences
            prefs.bbe_prefab_previews=not prefs.bbe_prefab_previews
        elif hit in {'category','group'}:
            close_variants(state)
            if not state.get('search_active') and state['categories' if hit=='category' else 'groups']:state['choice']=hit;state['choice_scroll']=None
        elif hit.startswith('choose:'):
            state[state['choice']]=hit[7:];state['choice']=None;state['scroll']=0;save(state)
        elif hit=='close':
            close_variants(state)
            state['enabled']=False;save(state);cursor(context,state,False)
        elif hit in {'resize','scroll'}:
            self.drag=hit
            if hit=='scroll':self.scroll_to(x)
        elif hit in {'next','previous'}:state['scroll']+=(1 if hit=='next' else -1)*max(1,state['columns']-1)
        context.area.tag_redraw();return {'FINISHED'}
    def choice_scroll_to(self,y):
        state=self.state
        rects=dict(state['targets'])
        track=rects.get('choice_track')
        if not track:return
        travel=track[3]-rects['choice_thumb'][3]
        fraction=(track[1]+track[3]-y-self.thumb_offset)/travel
        state['choice_scroll']=round(max(0,min(1,fraction))*state['choice_max'])

    def scroll_to(self,x):
        state=self.state
        px,py,w,h=next(rect for action,rect in state['targets'] if action=='scroll')
        state['scroll']=round(max(0,min(1,(x-px)/w))*state['maximum'])

ToggleStrip.__name__=('BBEPLUS' if PLUS else 'BBE')+'_OT_asset_strip_toggle'
StripInput.__name__=('BBEPLUS' if PLUS else 'BBE')+'_OT_asset_strip_input'

@persistent
def reset(*_):
    global _catalogue_cache, _search_cache
    _catalogue_cache = (None, None, None)
    _search_cache = (None, None, ())
    for window in bpy.context.window_manager.windows:
        for (win,_),state in _states.items():
            if win==window.as_pointer() and state.get('resize_cursor'):window.cursor_set('DEFAULT')
    _states.clear()

def register():
    for cls in (ToggleStrip,StripInput):bpy.utils.register_class(cls)
    _handlers.append(bpy.types.SpaceView3D.draw_handler_add(draw,(),'WINDOW','POST_PIXEL'))
    config=bpy.context.window_manager.keyconfigs.addon
    if config:
        km=config.keymaps.new(name='3D View',space_type='VIEW_3D',region_type='WINDOW')
        for event in ('LEFTMOUSE','MOUSEMOVE','WHEELUPMOUSE','WHEELDOWNMOUSE'):
            kmi=km.keymap_items.new(StripInput.bl_idname,event,'ANY' if event=='MOUSEMOVE' else 'PRESS',head=True)
            _keymaps.append((km,kmi))
        if not PLUS:
            # Mode-specific context menus run before the generic 3D View keymap.
            mode_maps = {'Object Mode', 'Mesh'}
            default = bpy.context.window_manager.keyconfigs.default
            for keymap in default.keymaps:
                if keymap.space_type == 'EMPTY' and any(
                    item.idname in {'wm.call_menu', 'wm.call_panel'}
                    and getattr(item.properties, 'name', '').startswith('VIEW3D_')
                    and 'context_menu' in item.properties.name for item in keymap.keymap_items
                ):
                    mode_maps.add(keymap.name)
            for name in sorted(mode_maps):
                mode = config.keymaps.new(name=name, space_type='EMPTY', region_type='WINDOW')
                item = mode.keymap_items.new(StripInput.bl_idname, 'RIGHTMOUSE', 'PRESS', head=True)
                _keymaps.append((mode,item))
            item = km.keymap_items.new(StripInput.bl_idname,'RIGHTMOUSE','PRESS',head=True)
            _keymaps.append((km,item))
    bpy.app.handlers.load_pre.append(reset)

def unregister():
    reset()
    for km,kmi in _keymaps:km.keymap_items.remove(kmi)
    _keymaps.clear()
    for handler in _handlers:bpy.types.SpaceView3D.draw_handler_remove(handler,'WINDOW')
    _handlers.clear()
    if reset in bpy.app.handlers.load_pre:bpy.app.handlers.load_pre.remove(reset)
    for cls in (StripInput,ToggleStrip):bpy.utils.unregister_class(cls)

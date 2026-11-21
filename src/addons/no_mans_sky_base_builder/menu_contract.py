"""FuriousFurby shared presentation contract. No editor implementation.

Canonical source: BBE+ extension/menu_contract.py. tools/sync_menu_contract.py
copies this presentation and verifies both builders retain the same sections.
"""
FILES = (
 ('row',(('clear','Clear Build Scene...','eraser'),)),
 ('label','Standalone build files'),
 ('row',(('import','Import Build from File...','file-down'),)),
 ('row',(('json','Save Project JSON','save'),('ship','Save (.nmsship)','save'),('base','Save (.nmsbase)','save'))),
 ('label','Clipboard'),
 ('row',(('paste','Import','file-down'),('copy_all','Copy All','copy'),('copy_objects','Copy Objects','copy'))),
)

def files(layout, bindings, help_button):
    col=layout.column(align=True);col.operator_context='INVOKE_DEFAULT'
    for kind,items in FILES:
        if kind=='label':
            col.separator(factor=.35);col.label(text=items);continue
        row=col.row(align=True)
        for key,text,icon in items:
            identifier,properties=bindings[key]
            op=row.operator(identifier,text=text)
            for name,value in properties.items():setattr(op,name,value)
        if items[0][0]=='clear':help_button(row)

def decorate(root):
    def walk(n):
        yield n
        for c in n.children:yield from walk(c)
    icons={text:icon for kind,items in FILES if kind=='row' for _,text,icon in items}
    sections={'Standalone build files','Clipboard','Quick Access','Switch Proxy Quality','Operations','Logic Components','Local Prefab Library','Advanced save tools','Grouping'}
    for n in walk(root):
        text=n.options.get('text','')
        native={'GREASEPENCIL':'pencil-line','TRASH':'trash-2','FILE_REFRESH':'refresh-cw','PREFERENCES':'settings','QUESTION':'circle-help'}
        if n.options.get('icon') in native:n.options['outline']=native[n.options['icon']]
        identifier=n.options.get('identifier','')
        if identifier=='object.list_edit_operator':n.options['outline']='pencil-line'
        if identifier=='object.list_delete_operator':n.options['outline']='trash-2'
        if text=='Online Community Prefabs':n.options.update(primary=True,outline='globe')
        if text in icons:n.options['outline']=icons[text]
        if text in {'Save Project JSON','Save (.nmsship)','Save (.nmsbase)'}:n.options['font_size']=12
        if n.kind=='label' and text in sections:n.options['section']=True
        if n.kind=='row' and n.children and all(c.kind=='operator' and c.options.get('text') in icons for c in n.children):n.options['equal']=True
        # Keep real part/curve thumbnails and palette swatches untouched.
        if n.options.get('outline'):
            n.options['icon_tint']=icon_colour(n.options['outline'],identifier,text)
        elif not n.options.get('icon_value'):
            native_art={'IMPORT':'file-down','EXPORT':'upload','FILE_TICK':'save','FILE_FOLDER':'folder-open',
                'FILE_BACKUP':'folder-clock','ADD':'copy-plus','DUPLICATE':'copy','LINKED':'link','UNLINKED':'unlink',
                'COLOR':'palette','EYEDROPPER':'pipette','VIEWZOOM':'search','INFO':'info','ERROR':'info',
                'CHECKMARK':'check','RECOVER_LAST':'history','TRIA_LEFT':'chevron-left','TRIA_RIGHT':'chevron-right',
                'MOD_MIRROR':'flip-horizontal-2','MOD_ARRAY':'layers','SNAP_ON':'magnet','LIGHT':'sun',
                'EMPTY_ARROWS':'arrow-down-up','TRANSFORM_MOVE':'arrow-left-right','TRANSFORM_ORIGINS':'arrow-down-up','CURVE_BEZCURVE':'spline'}
            art=ACTION_ICONS.get(text) or native_art.get(n.options.get('icon'))
            if art:n.options.update(outline=art,icon_tint=icon_colour(art,identifier,text))
    return root

def icon_colour(art,identifier='',text=''):
    """Semantic action colours; importing and exporting stay distinguishable."""
    route=(identifier+' '+text).lower()
    if art in {'file-down','clipboard-paste','pipette'} or 'import' in route or 'paste' in route:return (.27,.88,.53)
    if art in {'save','upload','download','copy','copy-plus','copy-check'} or 'export' in route:return (.25,.76,1.)
    if art in {'folder-open','folder-clock','folder-cog','package','package-plus','package-open'}:return (1.,.76,.34)
    if art in {'trash-2','unlink','eraser'}:return (1.,.48,.53)
    if art in {'link','magnet','git-branch-plus','git-fork','cable','check','refresh-cw'}:return (.28,.85,.70)
    if art in {'sun','rocket','hammer','wrench'}:return (1.,.72,.30)
    import bpy
    return tuple(bpy.context.preferences.themes[0].user_interface.wcol_menu_item.text[:3])

# Native Blender sidebars retain native interaction and accessibility. Use the
# same action artwork and grouping as the graphical menu without theme edits.
ACTION_ICONS={
 'Duplicate Along Edge Path':'spline','Duplicate Along Axis':'layers','Align':'magnet','Clear Build Scene...':'eraser','Clear Build Scene':'eraser','Import Build from File...':'file-down','Save Project JSON':'save',
 'Save (.nmsship)':'save','Save (.nmsbase)':'save','Import':'file-down','Copy All':'copy','Copy Objects':'copy',
 'Place Cables':'cable','New Point':'git-branch-plus','Connect':'link','Divide':'git-fork','Disconnect':'unlink',
 'Repair Selected SRT Connections':'refresh-cw','Save As Prefab':'package-plus','Split Prefab to Parts':'ungroup','Get More Prefabs...':'globe',
 'Open Prefab Folder':'folder-open','Group':'group','Ungroup':'ungroup','Draw Smooth Curve':'pencil-line','Curve from Edges / Faces':'scan-line',
 'Connect Endpoints':'link','Duplicate Along Curve':'copy-plus','Workspace Settings':'settings','Back Up Now':'save'}

class NativeSkin:
    def __init__(self,layout):object.__setattr__(self,'_target',layout)
    def __setattr__(self,key,value):setattr(self._target,key,value)
    def __getattr__(self,key):
        value=getattr(self._target,key)
        if key in {'row','column','box','split','grid_flow','column_flow'}:
            return lambda *a,**kw:NativeSkin(value(*a,**kw))
        return value
    def operator(self,identifier,**kwargs):
        from . import menu_surface
        name=ACTION_ICONS.get(kwargs.get('text',''))
        if name:
            icon=menu_surface.outline_icon(name,tint=icon_colour(name,identifier,kwargs.get('text','')))
            if icon:kwargs.pop('icon',None);kwargs['icon_value']=icon
        return self._target.operator(identifier,**kwargs)
    def prop(self,data,key,**kwargs):
        if key in {'color_picker','bbeplus_color_source'}:
            from . import menu_surface
            return self.operator(menu_surface.PREFIX+'.pick_object_colour',text='Pick Colour from Object',
                                 icon_value=menu_surface.outline_icon('pipette',tint=icon_colour('pipette')))
        return self._target.prop(data,key,**kwargs)

class PanelSkin:
    def __init__(self,owner):
        self._owner=owner
        self.layout=NativeSkin(owner.layout)
    def __getattr__(self,key):return getattr(self._owner,key)

_sidebar_draws={}
def _panel_draw(original):
    def draw(owner,context):
        original(PanelSkin(owner),context)
    return draw

def skin_sidebars():
    import bpy
    pending=list(bpy.types.Panel.__subclasses__());seen=set()
    while pending:
        cls=pending.pop()
        if cls in seen:continue
        seen.add(cls);pending.extend(cls.__subclasses__())
        if not cls.__module__.startswith(__package__) or getattr(cls,'bl_region_type','')!='UI' or cls in _sidebar_draws:continue
        original=cls.__dict__.get('draw')
        if original is None:continue
        _sidebar_draws[cls]=original;cls.draw=_panel_draw(original)

def unskin_sidebars():
    for cls,draw in _sidebar_draws.items():cls.draw=draw
    _sidebar_draws.clear()

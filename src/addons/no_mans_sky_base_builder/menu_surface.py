"""Independent, on-demand GPU menus for the BBE+ tool header.

The existing draw functions supply the controls and conditions. This small
layout adapter skins those controls without duplicating the tools, changing
Blender's theme, embedding a browser or running an always-on redraw loop.
"""
from collections import OrderedDict
from functools import lru_cache
from types import SimpleNamespace
import math
import colorsys
import textwrap
import time

import bpy
import blf
import gpu
from bpy.app.handlers import persistent
from gpu_extras.batch import batch_for_shader

from . import curve_widgets as paint, i18n
from pathlib import Path

INK=(.09,.075,.12,1)
SURFACE=(.15,.12,.20,1)
HOVER=(.23,.17,.31,1)
EDGE=(.32,.25,.40,1)
TEXT=(.95,.92,.98,1)
MUTED=(.70,.65,.78,1)
ACCENT=(.72,.57,.94,1)
PRIMARY=(.49,.33,.75,1)
_sessions={}
PLUS=__package__.endswith('bbe_plus')
PREFIX='bbeplus' if PLUS else 'bbe'
_textures=OrderedDict()
_gradient=None


def gradient_box(x,y,w,h,radius,a,b):
    """Static two-tone surface; one cached shader, no animation or images."""
    global _gradient
    if _gradient is None:
        interface=gpu.types.GPUStageInterfaceInfo('bbe_menu_gradient_iface');interface.smooth('VEC2','pixel')
        info=gpu.types.GPUShaderCreateInfo();info.vertex_in(0,'VEC2','pos');info.vertex_out(interface)
        for kind,name in [('MAT4','ModelViewProjectionMatrix'),('VEC4','rect'),('VEC4','first'),('VEC4','last'),('FLOAT','radius')]:info.push_constant(kind,name)
        info.push_constant('BOOL','ui_region')
        info.fragment_out(0,'VEC4','fragColor')
        info.vertex_source('void main(){pixel=pos;gl_Position=ModelViewProjectionMatrix*vec4(pos,0,1);}')
        info.fragment_source('''void main(){
            vec2 q=abs(pixel-rect.xy-rect.zw*.5)-rect.zw*.5+vec2(radius);
            float d=length(max(q,vec2(0)))+min(max(q.x,q.y),0.0)-radius;
            if(d>1.0)discard;
            vec2 uv=(pixel-rect.xy)/rect.zw;
            vec4 c=mix(first,last,clamp((uv.x+1.0-uv.y)*.7,0.0,1.0));
            vec3 rgb=mix(c.rgb/12.92,pow((c.rgb+.055)/1.055,vec3(2.4)),step(vec3(.04045),c.rgb));
            fragColor=vec4(ui_region ? c.rgb : rgb,c.a*(1.0-smoothstep(-.7,.7,d)));
        }''')
        _gradient=gpu.shader.create_from_info(info)
    gpu.state.blend_set('ALPHA');_gradient.bind()
    _gradient.uniform_bool('ui_region',(bpy.context.region is not None and bpy.context.region.type=='UI',))
    _gradient.uniform_float('ModelViewProjectionMatrix',gpu.matrix.get_projection_matrix() @ gpu.matrix.get_model_view_matrix())
    for key,value in [('rect',(x,y,w,h)),('first',a),('last',b),('radius',radius)]:_gradient.uniform_float(key,value)
    batch_for_shader(_gradient,'TRIS',{'pos':((x-1,y-1),(x+2*w+3,y-1),(x-1,y+2*h+3))}).draw(_gradient)


def _luminance(rgb):
    linear = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in rgb[:3]]
    return sum(channel*weight for channel, weight in zip(linear, (.2126, .7152, .0722)))


@lru_cache(maxsize=128)
def primary_button_colors(accent, theme_text, hovered):
    # Make the small label legible across the whole gradient. Mid-tone accents
    # follow the theme's light/dark text preference; saturated hues are retained.
    lightness = _luminance(accent)
    white_text = lightness < .13 or (lightness < .40 and _luminance(theme_text) > .35)
    white, black = (1.,1.,1.,1.), (0.,0.,0.,1.)
    label, shade = (white, black) if white_text else (black, white)
    def passes(color):
        lum = _luminance(color)
        return (1.05/(lum+.05) if white_text else (lum+.05)/.05) >= 7.
    base = accent
    if not passes(base):
        low, high = 0., 1.
        for _ in range(10):
            mid = (low+high)/2
            if passes(paint.mix(accent, shade, mid)):
                high = mid
            else:
                low = mid
        base = paint.mix(accent, shade, high)
    first = base if hovered else paint.mix(base, shade, .055)
    return first, paint.mix(first, shade, .12), label


def use_theme(context):
    """Keep the chosen BBE+ theme colours, with our own geometry and styling."""
    global INK,SURFACE,HOVER,EDGE,TEXT,MUTED,ACCENT,PRIMARY
    ui=context.preferences.themes[0].user_interface
    rgba=lambda value:tuple(value[:3])+(1.,)
    mix=lambda a,b,t:tuple(a[i]*(1-t)+b[i]*t for i in range(4))
    INK=rgba(ui.wcol_menu_back.inner)
    TEXT=rgba(ui.wcol_menu_item.text)
    # Keep text readable even in themes whose menu text and background match.
    light=sum(INK[i]*v for i,v in enumerate((.2126,.7152,.0722)))>.5
    if abs(sum((TEXT[i]-INK[i])*v for i,v in enumerate((.2126,.7152,.0722))))<.4:
        TEXT=(.08,.08,.08,1.) if light else (.95,.95,.95,1.)
    PRIMARY=rgba(ui.wcol_menu_item.inner_sel)
    SURFACE=mix(INK,TEXT,.065);HOVER=mix(INK,PRIMARY,.45)
    EDGE=mix(INK,TEXT,.25);MUTED=mix(INK,TEXT,.72)
    ACCENT=mix(PRIMARY,TEXT,.35)


def outline_icon(name,tint=None):
    from . import menu_backend as workspace
    if tint is None:tint=tuple(bpy.context.preferences.themes[0].user_interface.wcol_menu_item.text[:3])
    key='menu-outline:'+name
    if key not in workspace._icons:
        path=Path(__file__).parent/'images/menu_outline'/(name+'.png')
        if not path.is_file():return 0
        workspace._icons.load(key,str(path),'IMAGE')
    if tint:
        tinted=key+repr(tint)
        source=workspace._icons[key]
        if not source.image_size[0]:return source.icon_id
        if tinted not in workspace._icons:
            preview=workspace._icons.new(tinted)
            preview.image_size=source.image_size
            values = _preview_pixels(source.image_pixels_float, tint)
            preview.image_pixels_float.foreach_set(values)
            # Native UILayout uses the small, premultiplied icon buffer.
            # Our viewport renderer reads the separate straight-alpha image.
            preview.icon_size=source.icon_size
            small = _preview_pixels(source.icon_pixels_float, tint, premultiply=True)
            preview.icon_pixels_float.foreach_set(small)
        return workspace._icons[tinted].icon_id
    return workspace._icons[key].icon_id


def _preview_pixels(source, tint=None, *, premultiply=False):
    import numpy as np
    pixels = np.empty(len(source), dtype=np.float32)
    source.foreach_get(pixels)
    if tint is not None:
        rgba = pixels.reshape(-1, 4)
        rgba[:, :3] = rgba[:, 3:4] * tint[:3] if premultiply else tint[:3]
    return pixels


def operation(identifier):
    namespace, name=identifier.split('.')
    return getattr(getattr(bpy.ops,namespace),name)


def enum_items(data, key, context):
    from . import menu_backend
    return menu_backend.enum_items(data,key,context)



class Layout:
    """A data-only subset of UILayout used by BBE+'s existing menu definitions."""
    bbe_translates_text = True

    def __init__(self, kind='column', parent=None, **options):
        self.kind=kind;self.parent=parent;self.children=[];self.options=options
        self.enabled=True;self.active=True;self.alert=False;self.alignment='EXPAND'
        self.scale_x=1.;self.scale_y=1.;self.ui_units_x=0
        # Native UILayout captures the invocation context when a child/button
        # is created. A later EXEC_DEFAULT on the parent must not retroactively
        # turn an earlier interactive endpoint picker into an execute-only call.
        self.operator_context=parent.inherited('operator_context','INVOKE_DEFAULT') if parent else None
        self.use_property_split=False;self.use_property_decorate=False
        if parent:parent.children.append(self)

    def child(self,kind,**kw):return Layout(kind,self,**kw)
    def row(self,**kw):return self.child('row',**kw)
    def column(self,**kw):return self.child('column',**kw)
    def column_flow(self,**kw):return self.column(**kw)
    def box(self):return self.child('box')
    def split(self,**kw):return self.child('row',**kw)
    def grid_flow(self,**kw):return self.child('grid',**kw)
    def separator(self,**kw):return self.child('gap',**kw)
    def progress(self,**kw):return self.label(text=kw.get('text',''))
    def template_ID(self,data,key,**kw):return self.prop(data,key,**kw)
    def separator_spacer(self):return self.separator()
    def context_pointer_set(self,*args):pass
    def label(self,**kw):return self.child('label',**kw)
    def operator(self,identifier,**kw):
        props=SimpleNamespace()
        self.child('operator',identifier=identifier,props=props,**kw)
        return props
    def prop(self,data,key,**kw):
        if kw.get('expand'):
            row=self.row()
            for value,label,_ in enum_items(data,key,bpy.context):row.prop_enum(data,key,value,text=label)
            return
        return self.child('prop',data=data,key=key,**kw)
    def prop_enum(self,data,key,value,**kw):return self.child('enum_value',data=data,key=key,value=value,**kw)
    def prop_menu_enum(self,data,key,**kw):return self.prop(data,key,**kw)
    def prop_with_menu(self,data,key,*,menu,**kw):
        # Preserve the repair-aware selector supplied by the backend. A plain
        # enum would lose disabled/missing-slot explanations and repair actions.
        return self.child('prop',data=data,key=key,choice_menu=menu,**kw)
    def prop_tabs_enum(self,data,key,**kw):return self.prop(data,key,expand=True,**kw)
    def prop_search(self,data,key,*args,**kw):return self.prop(data,key,**kw)
    def menu(self,identifier,**kw):return self.child('menu',identifier=identifier,**kw)
    def popover(self,panel,**kw):return self.child('panel',identifier=panel,**kw)
    def operator_menu_enum(self,identifier,property,**kw):return self.child('operator_enum',identifier=identifier,key=property,**kw)
    def operator_enum(self,identifier,property,**kw):return self.operator_menu_enum(identifier,property,**kw)
    def template_icon(self,icon_value,scale=1,**kw):return self.child('image',icon_value=icon_value,scale=scale)
    def list_window(self, offset_key, total, rows, row_height):
        offset = min(getattr(bpy.context.window_manager, offset_key), max(0, total - rows))
        box = self.child('listbox', total=total, offset=offset, rows=rows,
                         row_height=row_height, offset_key=offset_key)
        return box, offset

    def template_list(self,identifier,list_id,data,key,active_data,active_key,**kw):
        cls=bpy.types.UIList.bl_rna_get_subclass_py(identifier)
        if cls is None:raise ValueError('Unknown BBE+ list: '+identifier)
        import inspect
        rows=getattr(data,key)
        sidebar_filter = self.inherited('prefab_filter', None)
        if sidebar_filter:
            query, filtered = sidebar_filter(self, rows)
        else:
            self.prop(bpy.context.window_manager,PREFIX+'_prefab_search',text='Search')
            query=getattr(bpy.context.window_manager,PREFIX+'_prefab_search','').casefold().strip()
            filtered=[(index,item) for index,item in enumerate(rows) if not query or query in ' '.join(str(getattr(item,k,'')) for k in ('name','description','title')).casefold()]
        size=max(3,min(12,kw.get('rows',6)))
        box, start = self.list_window(PREFIX+'_prefab_offset', len(filtered), size, 26 if sidebar_filter else 34)
        for index,item in filtered[start:start+size]:
            args=(SimpleNamespace(layout_type='DEFAULT'),bpy.context,box.column(),data,item,0,active_data,active_key,index)
            cls.draw_item(*args[:len(inspect.signature(cls.draw_item).parameters)])
        if not filtered:box.label(text='No matching local prefabs.' if query else 'No local prefabs loaded.',icon='INFO')

    def inherited(self,name,default=None):
        node=self
        while node:
            value=getattr(node,name,None)
            if value is not None and not (name=='alignment' and value=='EXPAND'):return value
            node=node.parent
        return default

    def is_enabled(self):
        node=self
        while node:
            if not node.enabled or not node.active:return False
            node=node.parent
        return True


def draw_definition(key,context,*,prefab_filter=None):
    from . import menu_backend as workspace, bbe_chat
    root=Layout();root.operator_context='INVOKE_DEFAULT'
    root.prefab_filter = prefab_filter
    layout=i18n.localized_layout(root)
    if not PLUS:
        result=workspace.definition(root,layout,key,context)
        if key=='IO':
            from .build_timer import next_save_action
            compact_io(result, next_save_action(context.scene))
        return result
    if key=='SETTINGS':workspace.settings(layout,context)
    elif key=='CHAT':bbe_chat.VIEW3D_PT_bbeplus_chat.draw(SimpleNamespace(layout=layout),context)
    elif key=='BUILDERS':workspace.builder_menu(layout,context)
    elif key.startswith(('PANEL:','MENU:')):
        family,identifier=key.split(':',1)
        cls=(bpy.types.Panel if family=='PANEL' else bpy.types.Menu).bl_rna_get_subclass_py(identifier)
        if cls is None:raise ValueError('This menu is unavailable: '+identifier)
        cls.draw(SimpleNamespace(layout=layout),context)
    else:workspace.DRAW[key](layout,context)
    from . import menu_layout
    result=menu_layout.style(root,key)
    if key=='IO':compact_io(result)
    return result


def compact_io(root, next_action=''):
    """Tighter related controls, with category breaks and one title-row toggle."""
    def visit(n):
        if n.kind in {'operator','prop','enum_value','menu'}:n.options['height']=28
        if n.kind=='label':
            n.options['height']=26 if n.options.get('section') else 22
            if n.options.get('text')=='Build timer':n.options.update(height=16,font_size=10)
            if n.options.get('text','').endswith(' Selected:'):n.options['bottom_align']=True
        if n.kind=='gap':n.options['factor']=.3
        if n.kind=='operator':
            identifier=n.options.get('identifier','')
            if identifier=='bbe.optimizer_export' or (identifier=='bbeplus.export_save' and getattr(n.options['props'],'optimize',False)):
                n.options.update(primary=True,center=True,left_align=False)
            if not PLUS and identifier in {'object.nms_import_base_from_save','object.nms_export_base_to_save','bbe.optimizer_export'}:
                n.options['primary'] = identifier == next_action
                n.options['accent'] = (.055,.38,.16,1) if identifier == 'object.nms_import_base_from_save' else (.065,.29,.62,1)
            if identifier in {'bbe.io_add_minimal_corvette','bbeplus.minimal_corvette'}:
                n.options.update(secondary=True,center=True)
        n.children[:]=[c for c in n.children if c.children or c.kind not in {'row','column','box','grid'}]
        if n.kind=='prop' and n.options.get('key') in {'check_plugin_enabled','bbeplus_save_enabled'}:
            n.options.update(width=36)
            n.parent.options.pop('top_rule',None)
            n.parent.parent.options['top_rule']=True
        for c in n.children:visit(c)
    visit(root)


def leaf_text(node):
    opts=node.options
    if 'text' in opts:return str(opts['text'])
    if node.kind=='enum_value':
        return next((name for identifier,name,_ in enum_items(opts['data'],opts['key'],bpy.context)
                     if identifier==opts['value']),opts['value'])
    if node.kind in {'prop','enum_value'}:
        return i18n.interface(opts['data'].bl_rna.properties[opts['key']].name)
    if node.kind in {'operator','operator_enum'}:
        return i18n.interface(operation(opts['identifier']).get_rna_type().name)
    return ''


def natural_width(node):
    if 'width' in node.options:return node.options['width']
    if node.children:
        sizes=[natural_width(c) for c in node.children]
        return sum(sizes)+node.options.get('gap',5)*(len(sizes)-1) if node.kind=='row' else max(sizes,default=30)
    if node.kind=='gap':return 7
    if not leaf_text(node) and node.kind not in {'prop'}:return 26
    if node.kind=='prop':return 135
    blf.size(0,14)
    return max(45,min(280,blf.dimensions(0,leaf_text(node))[0]+38))


def layout_tree(root,width):
    """One geometry model for painting, click targets and scroll bounds."""
    leaves=[]
    def place(n,x,top,w,scale=1):
        scale*=n.scale_y
        decor=n.options.get('decor')
        if decor:
            start=len(leaves);n.options['decor']=None
            padding=3 if decor in {'segments','tiles','search'} else 0
            height=place(n,x+padding,top+padding,w-2*padding,1)+2*padding
            n.options['decor']=decor
            decoration=Layout('decoration',decor=decor)
            leaves.insert(start,(decoration,(x,top,w,height)))
            return height
        if n.options.get('top_rule'):
            n.options['top_rule']=False
            mark=Layout('rule');leaves.append((mark,(x,top+5,w,1)))
            height=place(n,x,top+12,w,1)+12
            n.options['top_rule']=True
            return height
        if n.children:
            if n.kind=='listbox':
                at=top
                overflow = n.options['total'] > n.options['rows']
                for child in n.children:at+=place(child,x,at,w-(16 if overflow else 0),scale)+2
                height=max(n.options.get('row_height',34)*n.options['rows'],at-top)
                mark=Layout('list_scroll',**n.options);leaves.append((mark,(x,top,w,height)))
                return height
            children=n.children
            if n.alignment in {'LEFT','CENTER','RIGHT'}:
                compact=min(w,natural_width(n))
                x+=(w-compact)*({'LEFT':0,'CENTER':.5,'RIGHT':1}[n.alignment]);w=compact
            if n.kind=='row':
                gap=n.options.get('gap',5);available=w-gap*(len(children)-1)
                if n.options.get('equal'):
                    widths=[available/len(children)]*len(children)
                elif 'factor' in n.options and len(children)==2:
                    widths=[available*n.options['factor'],available*(1-n.options['factor'])]
                else:
                    sizes=[natural_width(c) for c in children]
                    flexible=[i for i,c in enumerate(children) if sizes[i]>30]
                    total=sum(sizes)
                    widths=[s*available/max(1,total) for s in sizes]
                    if available>sum(sizes) and flexible:
                        widths=[s+(available-sum(sizes))/len(flexible) if i in flexible else s for i,s in enumerate(sizes)]
                bottom=0;spans=[]
                for c,cw in zip(children,widths):
                    first=len(leaves);ch=place(c,x,top,max(10,cw),scale)
                    spans.append((first,len(leaves),ch,c));bottom=max(bottom,ch);x+=cw+gap
                for first,last,ch,c in spans:
                    if ch<bottom and (c.kind=='label' or (c.children and all(n.kind=='label' for n in c.children))):
                        for index in range(first,last):
                            node,(lx,lt,lw,lh)=leaves[index];leaves[index]=(node,(lx,lt+(bottom-ch)*(1 if c.options.get('bottom_align') else .5),lw,lh))
                return bottom
            if n.kind=='grid':
                cols=max(1,n.options.get('columns',4));gap=n.options.get('gap',5);cw=(w-gap*(cols-1))/cols;used=0
                for begin in range(0,len(children),cols):
                    height=max(place(c,x+i*(cw+gap),top+used,cw,scale) for i,c in enumerate(children[begin:begin+cols]))
                    used+=height+gap
                return max(0,used-gap)
            used=0
            for c in children:
                used+=place(c,x,top+used,w,scale)+2
            return max(0,used-2)
        if n.kind in {'row','column','box','grid'}:return 0
        text=leaf_text(n)
        if n.kind=='gap':return 5*n.options.get('factor',1)
        height=34
        if n.kind=='label':
            height=24
            if len(text)*6.2>w:height*=math.ceil(len(text)*6.2/max(30,w))
            if n.options.get('section'):height=29
            if n.options.get('empty'):height=45
            if n.options.get('notice'):height+=12
        elif n.kind=='image':height=28*n.options.get('scale',1)
        elif n.options.get('shape_tile') or (n.kind=='operator' and n.options['identifier']=='bbeplus.curve_add'):height=76
        elif n.options.get('swatch') or (n.kind=='operator' and n.options['identifier']=='bbeplus.paint'):height=26
        elif n.options.get('tile') or (n.kind=='operator' and n.options['identifier']=='bbeplus.place' and n.options.get('icon_value')):height=53
        # Native controls may request tall rows; our icon tiles already own height.
        if height==34:height*=min(1.2,scale)
        height=n.options.get('height',height)
        leaves.append((n,(x,top,w,height)))
        return height
    height=place(root,0,0,width)
    # Labels in a vertical form share one field edge. Separate columns keep
    # their own width, and unlabeled selectors still occupy their whole row.
    fields={}
    for node,(x,top,w,h) in leaves:
        if node.kind=='prop' and leaf_text(node) and node.options['data'].bl_rna.properties[node.options['key']].type!='BOOLEAN':
            fields.setdefault((round(x,2),round(w,2)),[]).append((node,w))
    blf.size(0,13)
    for group in fields.values():
        edge=max(min(w*.43,max(62,blf.dimensions(0,leaf_text(node))[0]+14)) for node,w in group)
        for node,w in group:node.options['field_label_width']=edge
    return leaves,height


def preview_icon(value):
    import sys
    from . import menu_backend
    from . import icons
    # Look in the live owners first. Walking every module dictionary for each
    # new menu icon also walks part catalogs and mesh metadata on large builds.
    groups = [menu_backend._icons, icons.preview_collections.get('ui_icons')]
    root = sys.modules[__package__]
    groups.extend(getattr(root, 'preview_collections', {}).values())
    for module_name, attribute in (('curve_icons', '_collection'), ('styled_ui', '_previews'),
                                   ('workspace_controls', '_previews'), ('bbe_chat', '_badge_previews'),
                                   ('community_prefabs', '_icons'), ('prefab_thumbnails', '_collection'),
                                   ('tools.asset_browser_presentation', '_weight_icons')):
        module = sys.modules.get(f'{__package__}.{module_name}')
        groups.append(getattr(module, attribute, None))
    groups.append(icons.preview_collections.get('asset_icons'))
    for group in groups:
        if not group:
            continue
        for preview in group.values():
            if preview.icon_id == value:
                return preview
    previews=[menu_backend._icons]
    for name,module in tuple(sys.modules.items()):
        if (name==__package__ or name.startswith(__package__+'.')) and module:
            for entry in vars(module).values():
                if isinstance(entry,dict):previews.append(entry)
    def find(group,depth=0):
        for item in tuple(group.values()):
            if getattr(item,'icon_id',None)==value:return item
            if depth<2 and isinstance(item,dict):
                match=find(item,depth+1)
                if match is not None:return match
    for group in previews:
        if isinstance(group,dict):
            match=find(group)
            if match is not None:return match
    return None


def texture(value,white=False,tint=None,preview=None):
    if not value:return None
    key=(bpy.context.window.as_pointer(),value,white,tint)
    if key in _textures:
        _textures.move_to_end(key);return _textures[key]
    if preview is None:preview=preview_icon(value)
    if preview is None or not preview.image_size[0]:return None
    w,h=preview.image_size
    values = _preview_pixels(preview.image_pixels_float, tint or ((1, 1, 1) if white else None))
    result=gpu.types.GPUTexture((w,h),format='RGBA8',data=gpu.types.Buffer('FLOAT',len(values),values))
    _textures[key]=result
    if len(_textures)>100:_textures.popitem(last=False)
    return result


def draw_image(value,x,y,w,h,white=False,tint=None,preview=None):
    tex=texture(value,white,tint,preview)
    if tex is None:return False
    shader=gpu.shader.from_builtin('IMAGE')
    gpu.state.blend_set('ALPHA');shader.bind();shader.uniform_sampler('image',tex)
    batch_for_shader(shader,'TRI_FAN',{'pos':((x,y),(x+w,y),(x+w,y+h),(x,y+h)),
         'texCoord':((0,0),(1,0),(1,1),(0,1))}).draw(shader)
    return True


def inside(rect,x,y):
    a,b,w,h=rect;return a<=x<=a+w and b<=y<=b+h


def trim(text,width,size):
    blf.size(0,size)
    if blf.dimensions(0,text)[0]<=width:return text
    while text and blf.dimensions(0,text+'…')[0]>width:text=text[:-1]
    return text+'…' if text else ''


def numeric_value(node):
    data,key=node.options['data'],node.options['key'];value=getattr(data,key)
    if node.options.get('index',-1)>=0:value=value[node.options['index']]
    return math.degrees(value) if data.bl_rna.properties[key].subtype=='EULER' else value


def property_value(node,context):
    data,key=node.options['data'],node.options['key'];value=getattr(data,key)
    prop=data.bl_rna.properties[key]
    if prop.type=='ENUM':
        items = node.options.get('choices') or enum_items(data,key,context)
        return next((label for identifier,label,_ in items if identifier==value),str(value))
    if prop.type=='FLOAT' and node.options.get('index',-1)>=0:return f'{numeric_value(node):.3f}'.rstrip('0').rstrip('.')
    if prop.type=='FLOAT':return f'{value:.3f}'.rstrip('0').rstrip('.') if not prop.is_array else str(tuple(round(v,3) for v in value))
    if prop.type=='POINTER':return value.name if value else 'Choose…'
    return str(value)


def tooltip(node):
    o=node.options
    if o.get('tip'):return i18n.tooltip(o['tip'])
    try:
        if node.kind in {'prop','enum_value'}:return i18n.tooltip(o['data'].bl_rna.properties[o['key']].description) or leaf_text(node)
        if node.kind=='operator':
            if o['identifier']=='bbeplus.curve_add':
                from .curve_shapes import SHAPES
                return next((desc for key,_,desc in SHAPES if key==o['props'].kind),leaf_text(node))
            if o['identifier']=='bbeplus.place':
                from .library import catalogue
                return catalogue().get(o['props'].part,{}).get('name',leaf_text(node))
            description=operation(o['identifier']).get_rna_type().description
            return i18n.tooltip(description) if description and description!='(undocumented operator)' else leaf_text(node)
    except (AttributeError,ReferenceError):pass
    return leaf_text(node)


class MenuSurface:
    list_drag = None
    panel_drag = None
    menu_drag = None
    workspace_position = None

    def scrollbar_geometry(self, node, rect):
        x, y, w, h = self.list_viewport(rect)
        s = self.scale
        track = (x+w-12*s, y+2*s, 9*s, max(1,h-4*s))
        rows, total = node.options['rows'], node.options['total']
        last = total-rows
        height = min(track[3], max(20*s, track[3]*rows/total))
        top = track[1]+track[3]-(track[3]-height)*node.options['offset']/last
        return track, (track[0],top-height,track[2],height), last

    def grab_list(self, x, y):
        for node, geom in self.leaves:
            if node.kind != 'list_scroll' or node.options['total'] <= node.options['rows']:
                continue
            rect = self.rect(geom)
            track, thumb, last = self.scrollbar_geometry(node, rect)
            if inside(track,x,y) and self.visible_list_point(rect,y):
                grab = thumb[1]+thumb[3]-y if inside(thumb,x,y) else thumb[3]/2
                self.list_drag = (track[1]+track[3], track[3]-thumb[3], last, grab, node.options['offset_key'])
                return True
        return False

    def list_viewport(self, rect):
        x, y, w, h = rect
        bottom = max(y, (self.top-self.height+10)*self.scale)
        top = min(y+h, (self.top-48)*self.scale)
        return x, bottom, w, max(0, top-bottom)

    def visible_list_point(self, rect, y):
        _, bottom, _, height = self.list_viewport(rect)
        return bottom <= y <= bottom+height and height > 0

    def scroll_list_to(self, context, y):
        top, travel, last, grab, key = self.list_drag
        value = max(0,min(last,round((top-y-grab)*last/max(1,travel))))
        if getattr(context.window_manager,key) != value:
            setattr(context.window_manager,key,value)
            return True
        return False

    def invoke(self,context,event):
        if context.area is None or context.area.type!='VIEW_3D':return {'CANCELLED'}
        stop()
        return self.begin_surface(context, event, context.area.as_pointer())

    def begin_surface(self, context, event, key):
        self.area=context.area;self.window=context.window
        self.region=next(r for r in self.area.regions if r.type=='WINDOW')
        self.scale=max(.65,context.preferences.system.ui_scale*.88)
        self.anchor=((self.anchor_x if self.anchor_x>=0 else event.mouse_x)-self.region.x,(self.anchor_y if self.anchor_y>=0 else event.mouse_y)-self.region.y)
        self.key=key;self.stack=[];self.scroll=0;self.dropdown=None
        self.edit=None;self.hover=None;self.mouse=(-1,-1);self.drag=None;self.last_hover=0;self.message=''
        self.last_refresh=0
        self.number_drag=None
        self.shader=gpu.shader.from_builtin('UNIFORM_COLOR')
        self.rebuild(context)
        self.handler=bpy.types.SpaceView3D.draw_handler_add(self.draw_surface,(),'WINDOW','POST_PIXEL')
        self.timer=context.window_manager.event_timer_add(.35,window=self.window)
        _sessions[self.key]=self
        context.window_manager.modal_handler_add(getattr(self, 'modal_owner', self));self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def rebuild(self,context):
        from . import menu_backend as workspace
        use_theme(context)
        width={'HOME':420,'RECOVERY':440,'IO':500,'COLOR':420,'BUILDER':500,'CURVES':460,
               'BATCH':460,'PREFABS':480,'LOGIC':460,'LIGHTING':400,'CHAT':410,'SETTINGS':420,'WORKSPACE':510,
               'PANEL:VIEW3D_PT_bbe_shape_part_picker':310}.get(self.menu,440)
        right=self.region.width
        for panel in self.area.regions:
            if panel.type=='UI' and panel.width>1 and panel.x>self.region.x+self.region.width/2:
                right=min(right,panel.x-self.region.x)
        self.width=min(width,max(230,right/self.scale-24))
        with context.temp_override(window=self.window,area=self.area,region=self.region):
            self.root=draw_definition(self.menu,context)
            self.header_help=getattr(self.root,'header_help',None)
            self.header_count=getattr(self.root,'header_count',None)
            if self.header_help:self.header_help.can_click=True
            self.leaves,self.content_height=layout_tree(self.root,self.width-24)
            # Poll once per layout rebuild, never inside GPU drawing.
            for node,_ in self.leaves:
                node.can_click=node.is_enabled()
                if node.kind=='operator':
                    try:node.can_click &= operation(node.options['identifier']).poll()
                    except (RuntimeError,AttributeError):node.can_click=False
        ceiling=self.region.height/self.scale-8
        for header in self.area.regions:
            if header.type in {'HEADER','TOOL_HEADER'} and header.y>self.region.y+self.region.height/2:
                ceiling=min(ceiling,(header.y-self.region.y)/self.scale-8)
        self.height=min(self.content_height+68,max(100,ceiling-8))
        self.scroll=max(0,min(self.scroll,max(0,self.content_height-(self.height-68))))
        self.left=max(8,min(self.anchor[0]/self.scale-(self.width/2 if self.anchor_center else 0),right/self.scale-self.width-8))
        self.top=max(self.height+8,min(self.anchor[1]/self.scale,ceiling))
        self.title=next((label for key,label,_ in workspace.TOOLS if key==self.menu),
                        'Workspace Settings' if self.menu=='SETTINGS' else 'BBE+' if self.menu=='BUILDERS' else self.menu.split(':')[-1].replace('_',' '))
        if self.menu in {'NEW_SHAPE', 'WORKSPACE'}:
            left=next((p.width for p in self.area.regions if p.type=='TOOLS' and p.width>1),0)
            self.left=max(8,min((left/self.scale+right/self.scale-self.width)/2,right/self.scale-self.width-8))
            self.top=min(ceiling,(ceiling+self.height+8)/2)
            if self.menu == 'WORKSPACE':
                self.title = 'Workspace Settings'
            else:
                self.title = 'New Shape'
        if self.menu in {'WORKSPACE', 'SETTINGS'}:
            self.position_limits = (max(8, right/self.scale-self.width-8), ceiling)
            self.move_settings(*(self.workspace_position or (self.left, self.top)))
        if self.menu.startswith(('PANEL:','MENU:')):
            family,name=self.menu.split(':',1)
            cls=(bpy.types.Panel if family=='PANEL' else bpy.types.Menu).bl_rna_get_subclass_py(name)
            if cls:self.title=cls.bl_label
        # A timed refresh creates new nodes; retain the highlight at the same
        # physical pointer, rather than holding a stale node identity.
        self.hover=self.hit_test(*self.mouse)
        self.area.tag_redraw()

    def clamped_position(self, left, top):
        right, ceiling = self.position_limits
        return max(8, min(left, right)), min(ceiling, max(self.height+8, top))

    def move_settings(self, left, top):
        self.left, self.top = self.clamped_position(left, top)
        self.workspace_position = (self.left, self.top)

    def reorder_target(self):
        x, y = self.mouse
        for node, geometry in self.leaves:
            if node.kind != 'menu_grip':
                continue
            rx, ry, _, height = self.rect(geometry)
            row = (rx, ry-self.scale, (self.width-24)*self.scale, height+2*self.scale)
            if self.visible(self.rect(geometry)) and inside(row, x, y):
                return node.options['menu'], y < ry+height/2, row
        return None

    def settings_drag_event(self, context, event):
        x, y = self.mouse
        s = self.scale
        cancel = event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS'
        release = event.type == 'LEFTMOUSE' and event.value == 'RELEASE'
        if self.panel_drag:
            dx, dy, original = self.panel_drag
            if event.type == 'MOUSEMOVE' or release:
                self.move_settings(x/s-dx, y/s-dy)
            if cancel:
                self.move_settings(*original)
            if cancel or release:
                self.panel_drag = None
        elif self.menu_drag:
            if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
                limit = max(0, self.content_height-(self.height-68))
                self.scroll = max(0, min(limit, self.scroll + (42 if event.type == 'WHEELDOWNMOUSE' else -42)))
            if release:
                target = self.reorder_target()
                surface, source = self.menu_drag
                if target and target[0] != source:
                    bpy.ops.bbe.toolbar_menu(action='MOVE', surface=surface, menu=source,
                                             target=target[0], after=target[1])
                    self.rebuild(context)
            if cancel or release:
                self.menu_drag = None
        self.hover = self.hit_test(x, y)
        self.last_hover = time.monotonic()
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def hit_test(self,x,y):
        return next((n for n,r in reversed(self.leaves) if n.kind not in {'decoration','rule','label','image','list_scroll'} and self.visible(self.rect(r)) and inside(self.rect(r),x,y)),None)

    def rect(self,geometry):
        x,t,w,h=geometry;s=self.scale
        return ((self.left+12+x)*s,(self.top-52-t-h+self.scroll)*s,w*s,h*s)

    def visible(self,rect):
        return rect[1]>=((self.top-self.height+10)*self.scale) and rect[1]+rect[3]<=(self.top-48)*self.scale

    def draw_surface(self):
        context=bpy.context
        if context.area!=self.area or context.region!=self.region:return
        use_theme(context)
        s=self.scale
        with paint.canvas(context):
            x,y,w,h=self.left*s,(self.top-self.height)*s,self.width*s,self.height*s
            for pad,alpha in ((7,.08),(4,.12),(2,.16)):
                paint.rounded(self.shader,x-pad*s,y-(pad+3)*s,w+2*pad*s,h+(pad+3)*s,16*s,(0,0,0,alpha))
            paint.rounded(self.shader,x,y,w,h,13*s,EDGE)
            gradient_box(x+s,y+s,w-2*s,h-2*s,13*s,SURFACE,INK)
            from . import menu_backend as workspace
            symbol=next((symbol for key,_,symbol in workspace.TOOLS if key==self.menu),'settings' if self.menu=='SETTINGS' else 'extended_mark')
            paint.rounded(self.shader,x+12*s,y+h-39*s,29*s,29*s,8*s,SURFACE)
            header_icons=dict(HOME='box',RECOVERY='history',IO='arrow-down-up',COLOR='palette',BUILDER='hammer',CURVES='spline',BATCH='layers',PREFABS='package',LOGIC='cable',LIGHTING='sun',CHAT='messages-square',SETTINGS='settings',WORKSPACE='settings')
            header_icons['PANEL:VIEW3D_PT_bbe_shape_part_picker']='pipette'
            if self.stack:paint.text('‹',x+26*s,y+h-31*s,20*s,ACCENT,align='CENTER')
            else:draw_image(outline_icon(getattr(self,'header_icon',header_icons.get(self.menu,'box'))),x+17*s,y+h-34*s,19*s,19*s)
            paint.text(i18n.interface(self.title),x+50*s,y+h-30*s,15*s,TEXT)
            if self.header_count is not None:
                paint.text(i18n.interface('Part count')+'  '+self.header_count,x+w-48*s,y+h-29*s,11*s,MUTED,align='RIGHT')
            if self.menu in {'WORKSPACE', 'HOW_TO'}:
                paint.text('×', x+w-22*s, y+h-31*s, 20*s, TEXT, align='CENTER')
            elif self.header_help:
                draw_image(outline_icon('circle-help'),x+w-31*s,y+h-34*s,19*s,19*s)
            paint.line(self.shader,(x+12*s,y+h-45*s),(x+w-12*s,y+h-45*s),s,EDGE)
            for node,geometry in self.leaves:
                rect=self.rect(geometry)
                if self.visible(rect) or (node.kind == 'list_scroll' and self.list_viewport(rect)[3] > 4*s):
                    self.paint_node(node,rect)
            if self.content_height>self.height-68:
                fraction=(self.height-68)/self.content_height
                track=(self.height-68)*s
                pos=self.scroll/self.content_height*track
                paint.rounded(self.shader,x+w-5*s,y+h-40*s-pos-track*fraction,2*s,track*fraction,s,EDGE)
            if self.menu_drag:
                target = self.reorder_target()
                if target and target[0] != self.menu_drag[1]:
                    lx, ly, lw, lh = target[2]
                    line_y = ly if target[1] else ly+lh
                    paint.line(self.shader, (lx,line_y), (lx+lw,line_y), 2*s, ACCENT)
            if self.drag:
                paint.text('↕ '+self.drag[0],self.mouse[0]+10*s,self.mouse[1]+8*s,12*s,ACCENT)
            if self.dropdown:self.draw_dropdown()
            elif self.hover and self.hover.can_click and time.monotonic()-self.last_hover>.8:
                hint=tooltip(self.hover)
                if hint:
                    lines=textwrap.wrap(hint,48)
                    th=(len(lines)*17+16)*s;tw=min(330*s,max(len(line)*6.4*s for line in lines)+20*s)
                    tx=max(6*s,min(self.mouse[0]+16*s,self.region.width-tw-6*s))
                    ty=self.mouse[1]-th-20*s
                    if ty<6*s:ty=self.mouse[1]+24*s
                    ty=min(ty,self.region.height-th-6*s)
                    paint.rounded(self.shader,tx,ty,tw,th,8*s,EDGE)
                    paint.rounded(self.shader,tx+s,ty+s,tw-2*s,th-2*s,7*s,SURFACE)
                    for i,line in enumerate(lines):paint.text(line,tx+9*s,ty+th-(i+1)*17*s-1*s,12*s,TEXT)
            if self.message:paint.text(trim(self.message,w-24*s,11*s),x+12*s,y+7*s,11*s,ACCENT)

    def paint_node(self,node,rect):
        x,y,w,h=rect;s=self.scale;o=node.options;text=leaf_text(node)
        if node.kind=='decoration':
            if o['decor'] in {'segments','tiles'}:
                paint.rounded(self.shader,x,y,w,h,8*s,tuple(c*.68 for c in INK[:3])+(1,))
            elif o['decor']=='columns':paint.line(self.shader,(x+w*.54,y+4*s),(x+w*.54,y+h-4*s),.7*s,EDGE)
            elif o['decor']=='search':
                paint.rounded(self.shader,x,y,w,h,8*s,EDGE)
                paint.rounded(self.shader,x+s,y+s,w-2*s,h-2*s,7*s,tuple(c*.65 for c in INK[:3])+(1,))
            return
        if node.kind=='list_scroll':
            total=o['total'];count=o['rows']
            if total>count:
                track, thumb, _ = self.scrollbar_geometry(node, rect)
                paint.rounded(self.shader,*track,4*s,paint.mix(INK,TEXT,.22))
                paint.rounded(self.shader,*thumb,4*s,paint.mix(INK,TEXT,.78))
            return
        if node.kind=='rule':paint.line(self.shader,(x,y),(x+w,y),.7*s,EDGE);return
        enabled=node.can_click;color=TEXT if enabled else MUTED
        ancestor=node
        while ancestor:
            if ancestor.alert:color=(1,.40,.40,1);break
            ancestor=ancestor.parent
        hot=node is self.hover and enabled;primary=o.get('primary',False)
        if o.get('quiet'):color=MUTED
        pressed=bool(o.get('depress')) and not o.get('switch')
        if node.kind=='enum_value':pressed=getattr(o['data'],o['key'])==o['value']
        if o.get('secondary') and not hot:paint.rounded(self.shader,x,y,w,h,6*s,SURFACE)
        accent=o.get('accent',PRIMARY)
        if (hot or primary or pressed) and not (primary and enabled):
            paint.rounded(self.shader,x,y,w,h,6*s,HOVER if hot else SURFACE)
        if pressed and not primary:
            paint.rounded(self.shader,x,y,w,h,6*s,EDGE)
            paint.rounded(self.shader,x+s,y+s,w-2*s,h-2*s,5*s,HOVER)
        if primary and enabled:
            first, last, color = primary_button_colors(accent, TEXT, hot)
            gradient_box(x,y,w,h,7*s,first,last)
        if o.get('tile') and not hot and not pressed:paint.rounded(self.shader,x,y,w,h,7*s,SURFACE)
        if o.get('icon') in {'CHECKBOX_HLT','CHECKBOX_DEHLT'} and not text:
            on=o['icon']=='CHECKBOX_HLT';bx=x+(w-14*s)/2;by=y+(h-14*s)/2
            paint.rounded(self.shader,bx,by,14*s,14*s,3*s,PRIMARY if on else EDGE)
            if on:
                paint.line(self.shader,(bx+3*s,by+7*s),(bx+6*s,by+4*s),1.7*s,TEXT)
                paint.line(self.shader,(bx+6*s,by+4*s),(bx+13*s,by+10*s),1.7*s,TEXT)
            return
        if node.kind == 'menu_grip':
            for dx in (5, 10):
                for dy in (-5, 0, 5):
                    paint.disc(self.shader, x+dx*s, y+h/2+dy*s, 1.3*s, MUTED)
            paint.text(trim(text, w-22*s, 14*s), x+20*s, y+h/2-4*s, 14*s, color)
            return
        if o.get('arrow'):
            paint.text(o['arrow'],x+w/2,y+h/2-5*s,18*s,color,align='CENTER');return
        if o.get('switch'):
            on=bool(o.get('depress'))
            left = x+w-(34 if text else 30)*s
            paint.rounded(self.shader,left,y+h/2-8*s,30*s,16*s,8*s,PRIMARY if on else EDGE)
            paint.disc(self.shader,left+(22 if on else 8)*s,y+h/2,5*s,TEXT)
            paint.text(text,x+5*s,y+h/2-4*s,14*s,color);return
        if node.kind=='prop':
            prop=o['data'].bl_rna.properties[o['key']]
            if prop.type=='POINTER' and o['key'] in {'color_picker','bbeplus_color_source'}:
                draw_image(outline_icon('pipette'),x+5*s,y+h/2-9*s,18*s,18*s,tint=(.3,.9,.65))
                paint.text(i18n.interface('Pick Colour from Object'),x+30*s,y+h/2-4*s,14*s,color)
                return
            if prop.type=='BOOLEAN':
                on=bool(getattr(o['data'],o['key']))
                if o.get('checkbox'):
                    bx=x+w-19*s
                    paint.rounded(self.shader,bx,y+h/2-6*s,14*s,14*s,2*s,PRIMARY if on else EDGE)
                    if on:paint.text('✓',bx+6*s,y+h/2-4*s,13*s,TEXT,align='CENTER')
                    paint.text(trim(text,w-27*s,13*s),x+5*s,y+h/2-4*s,13*s,MUTED);return
                paint.rounded(self.shader,x+w-34*s,y+h/2-8*s,30*s,16*s,8*s,PRIMARY if on else EDGE)
                paint.disc(self.shader,x+w-(12 if on else 26)*s,y+h/2,5*s,TEXT)
                paint.text(trim(text,w-42*s,13*s),x+5*s,y+h/2-4*s,13*s,color);return
            label_width=min(w*.43,o.get('field_label_width',len(text)*6+10)*s) if text else 0
            if text:paint.text(trim(text,label_width-4*s,13*s),x+3*s,y+h/2-4*s,13*s,MUTED)
            fx=x+label_width;fw=w-label_width
            field=tuple(c*.65 for c in INK[:3])+(1,)
            if not o.get('search_field'):
                paint.rounded(self.shader,fx,y+2*s,fw,h-4*s,7*s,EDGE)
                paint.rounded(self.shader,fx+s,y+3*s,fw-2*s,h-6*s,6*s,field)
            if o.get('slider') and prop.type in {'INT','FLOAT'} and not prop.is_array:
                low,high=prop.soft_min,prop.soft_max
                if high>low and high-low<1e6:
                    fraction=max(0,min(1,(getattr(o['data'],o['key'])-low)/(high-low)))
                    paint.rounded(self.shader,fx,y+2*s,fw*fraction,h-4*s,6*s,HOVER)
            if self.edit and self.edit['node'] is node and hasattr(self, 'draw_edit_text'):
                self.draw_edit_text(fx, y, fw, h)
                return
            value=self.edit['text']+'|' if self.edit and self.edit['node'] is node else property_value(node,bpy.context)
            if not value and o.get('placeholder'):value=o['placeholder'];color=MUTED
            if prop.subtype=='PASSWORD':value='•'*len(value)
            paint.text(trim(value,fw-24*s,13*s),fx+7*s,y+h/2-4*s,13*s,color)
            if prop.type in {'ENUM','POINTER'}:paint.text('⌄',x+w-10*s,y+h/2-3*s,14*s,MUTED)
            return
        icon_value=outline_icon(o['outline']) if o.get('outline') else o.get('icon_value',0)
        if (o.get('tile') or o.get('shape_tile') or (node.kind=='operator' and o.get('identifier') in {'bbeplus.curve_add','bbeplus.place'})) and icon_value:
            sz=min(w-8*s,h-18*s,(60 if o['identifier']=='bbeplus.curve_add' else 44)*s)
            draw_image(icon_value,x+(w-sz)/2,y+h-sz-2*s,sz,sz)
            paint.text(trim(text,w-6*s,10*s),x+w/2,y+4*s,10*s,color,align='CENTER');return
        if o.get('material_finish') and icon_value:
            size = min(w, h) - 4*s
            draw_image(icon_value, x+(w-size)/2, y+(h-size)/2, size, size)
            return
        if (o.get('swatch') or (node.kind=='operator' and o.get('identifier')=='bbeplus.paint')) and icon_value:
            # The catalogue image is the authoritative dual swatch, in source order.
            
            if hot:paint.rounded(self.shader,x,y,w,h,4*s,ACCENT)
            draw_image(icon_value,x+3*s,y+4*s,w-6*s,h-8*s);return
        if node.kind=='image':draw_image(icon_value,x,y,h,h);return
        if node.kind=='label' and o.get('section'):
            paint.text(trim(text.upper(),w-8*s,10*s),x+3*s,y+5*s,10*s,MUTED);return
        if o.get('small'):
            paint.text(trim(text,w-30*s,11*s),x+22*s,y+h/2-4*s,11*s,ACCENT);return
        if o.get('identifier') == 'object.list_build_operator' and getattr(o['props'], 'prefab_only', False):
            from . import prefab_thumbnails, styled_ui
            preview = prefab_thumbnails.get(o['props'].part_id)
            size = min(h-2*s, 32*s)
            styled_ui.image(preview, x+2*s, y+(h-size)/2, size, size)
            left = size+7*s if preview else 5*s
            font = o.get('font_size', 14)*s
            paint.text(trim(text, w-left-3*s, font), x+left, y+h/2-4*s, font, color)
            return
        icon_tint = color if primary and enabled and o.get('outline') else o.get('icon_tint')
        if (primary or o.get('center')) and not o.get('left_align'):
            size=o.get('font_size',14)*s
            label=trim(text,w-40*s,size);blf.size(0,size)
            label_width=blf.dimensions(0,label)[0]
            has_icon=bool(icon_value and texture(icon_value))
            total=label_width+(23*s if has_icon else 0);start=x+(w-total)/2
            if has_icon:draw_image(icon_value,start,y+h/2-9*s,18*s,18*s,tint=icon_tint)
            paint.text(label,start+(23*s if has_icon else 0),y+h/2-4*s,size,color);return
        offset=5*s
        if icon_value and draw_image(icon_value,x+5*s,y+h/2-9*s,18*s,18*s,tint=icon_tint):offset=30*s
        elif o.get('icon') not in (None,'NONE','BLANK1'):
            # Native-only controls use their text, never an unrelated invented glyph.
            if not text:text={'QUESTION':'?','TRIA_UP':'↑','TRIA_DOWN':'↓','TRIA_LEFT':'‹','TRIA_RIGHT':'›',
                'CHECKBOX_HLT':'☑','CHECKBOX_DEHLT':'☐','PREFERENCES':'⚙','TRASH':'×','ADD':'+','REMOVE':'−'}.get(o['icon'],o['icon'].replace('_',' ').title())
        if node.kind=='label':
            if o.get('empty'):
                paint.rounded(self.shader,x,y,w,h,7*s,tuple(c*.8 for c in INK[:3])+(1,))
                paint.text(text,x+w/2,y+h/2-4*s,13*s,MUTED,align='CENTER');return
            if o.get('notice'):paint.rounded(self.shader,x,y,w,h,7*s,SURFACE)
            if node.inherited('alignment')=='RIGHT':
                size=9 if text==i18n.interface('Build timer') else 11
                paint.text(trim(text,w-10*s,size*s),x+w-5*s,y+h/2-3*s,size*s,MUTED,align='RIGHT');return
            lines=textwrap.wrap(text,max(3,int((w-offset)/max(1,5.5*s)))) or ['']
            for i,line in enumerate(lines):paint.text(line,x+offset,y+h-(i+1)*16*s+3*s,12*s,MUTED)
        else:
            if ((primary or o.get('center')) and not o.get('left_align')) or node.kind=='enum_value':
                # Primary and segmented actions share the reference's centered baseline.
                paint.text(trim(text,w-14*s,14*s),x+w/2,y+h/2-4*s,14*s,color,align='CENTER')
            else:
                size=o.get('font_size',14)*s
                paint.text(trim(text,w-offset-8*s,size),x+offset,y+h/2-4*s,size,color)
            if node.kind in {'menu','panel','operator_enum'}:paint.text('›',x+w-10*s,y+h/2-4*s,14*s,MUTED)

    def open_choices(self,node,items,callback):
        geometry=next(g for n,g in self.leaves if n is node)
        x,y,w,h=self.rect(geometry)
        if node.kind=='prop' and leaf_text(node):
            label=min(w*.43,node.options.get('field_label_width',62)*self.scale);x+=label;w-=label
        self.dropdown={'node':node,'items':items,'callback':callback,'offset':0,'anchor':(x,y,w,h)}
        self.area.tag_redraw()

    def choice_geometry(self):
        d=self.dropdown;s=self.scale
        x,y,w,h=d['anchor'];blf.size(0,13*s)
        width=min(360*s,self.region.width-16*s,max(w,max((blf.dimensions(0,v[1])[0] for v in d['items']),default=120*s)+24*s))
        below=y-16*s;above=self.region.height-y-h-16*s
        upward=below<min(len(d['items']),6)*31*s and above>below
        room=above if upward else below
        count=min(len(d['items']),max(1,int(room/(31*s))))
        left=max(8*s,min(x,self.region.width-width-8*s))
        top=y+h+count*31*s+5*s if upward else y-5*s
        return left,top,width,count

    def draw_dropdown(self):
        x,top,w,count=self.choice_geometry();s=self.scale;d=self.dropdown
        paint.rounded(self.shader,x-2*s,top-count*31*s-3*s,w+4*s,count*31*s+6*s,9*s,EDGE)
        paint.rounded(self.shader,x,top-count*31*s-1*s,w,count*31*s+2*s,8*s,INK)
        for i,item in enumerate(d['items'][d['offset']:d['offset']+count]):
            rect=(x,top-(i+1)*31*s,w,31*s)
            if inside(rect,*self.mouse):paint.rounded(self.shader,*rect,5*s,HOVER)
            elif d.get('selected') == item[0]:paint.rounded(self.shader,*rect,5*s,SURFACE)
            paint.text(trim(item[1],w-20*s,13*s),x+8*s,rect[1]+10*s,13*s,TEXT)
        if len(d['items'])>count:
            track=count*31*s;thumb=track*count/len(d['items']);offset=track*d['offset']/len(d['items'])
            paint.rounded(self.shader,x+w-5*s,top-offset-thumb,3*s,thumb,1.5*s,ACCENT)

    def set_property(self,node,value):
        data,key=node.options['data'],node.options['key']
        prop=data.bl_rna.properties[key]
        if prop.type=='INT':value=max(prop.hard_min,min(prop.hard_max,int(value)))
        elif prop.type=='FLOAT':value=max(prop.hard_min,min(prop.hard_max,float(value)))
        index=node.options.get('index',-1)
        if index>=0:
            if prop.subtype=='EULER':value=math.radians(value)
            getattr(data,key)[index]=value
        else:setattr(data,key,value)
        # Blender owns update callbacks (curve rebuilds, themes and save selection).
        # Discard captured controls immediately after the callback changes context.
        self.dropdown=None;self.edit=None;self.rebuild(bpy.context)
        from . import settings_memory
        settings_memory.flush()
        if self.number_drag is None:self.property_checkpoint(node)

    def property_checkpoint(self,node):
        # Parameter edits on a guide change real geometry; retain normal Undo.
        owner=getattr(node.options['data'],'id_data',None)
        if isinstance(owner,bpy.types.Object):
            with bpy.context.temp_override(window=self.window,area=self.area,region=self.region):
                bpy.ops.ed.undo_push(message='BBE+ '+leaf_text(node))

    def activate(self,node,context):
        o=node.options
        if not node.can_click:return {'RUNNING_MODAL'}
        if node.kind=='menu' and o['identifier'] in {'BBEPLUS_MT_recovery','BBE_MT_recovery'}:
            tree=draw_definition('MENU:'+o['identifier'],context)
            entries,_=layout_tree(tree,self.width-24)
            actions=[n for n,_ in entries if n.kind=='operator' and n.options['identifier']==PREFIX+'.open_recovery']
            items=[(str(i),leaf_text(n),'') for i,n in enumerate(actions)]
            def choose(value):
                if value is not None:
                    selected=actions[int(value)]
                    self.queue_operator(selected.options['identifier'],vars(selected.options['props']).copy(),'INVOKE_DEFAULT')
            self.open_choices(node,items or [(None,i18n.interface('No recovery copies yet'),'')],choose)
            self.dropdown['require_release'] = True
        elif node.kind in {'menu','panel'}:
            self.stack.append((self.menu,self.scroll));self.menu=('MENU:' if node.kind=='menu' else 'PANEL:')+o['identifier'];self.scroll=0;self.rebuild(context)
        elif node.kind=='enum_value':self.set_property(node,o['value'])
        elif node.kind=='prop':
            data,key=o['data'],o['key'];prop=data.bl_rna.properties[key]
            if o.get('choice_menu'):
                self.stack.append((self.menu,self.scroll));self.menu='MENU:'+o['choice_menu'];self.scroll=0;self.rebuild(context)
            elif prop.type=='BOOLEAN':
                self.set_property(node,not getattr(data,key))
                if _sessions.get(self.key) is not self:return {'FINISHED'}
            elif prop.type=='ENUM':self.open_choices(node,enum_items(data,key,context),lambda value:self.set_property(node,value))
            elif prop.type=='POINTER':
                if key in {'color_picker','bbeplus_color_source'}:
                    self.queue_operator(PREFIX+'.pick_object_colour',{},'INVOKE_DEFAULT')
                    return {'FINISHED'}
                values=list(context.scene.objects)
                self.open_choices(node,[(obj.name,obj.name,'') for obj in values],lambda value:self.set_property(node,bpy.data.objects.get(value)))
            elif prop.type in {'INT','FLOAT'} and (not prop.is_array or o.get('index',-1)>=0):
                self.number_drag={'node':node,'value':numeric_value(node),'origin':self.mouse,'moved':False}
            elif prop.type=='STRING':
                self.edit={'node':node,'text':str(getattr(data,key)),'replace':True}
            else:self.message='Use the sidebar for this compound property.'
        elif node.kind=='operator_enum':
            rna=operation(o['identifier']).get_rna_type().properties[o['key']]
            self.open_choices(node,[(v.identifier,v.name,v.description) for v in rna.enum_items],
                              lambda v:self.queue_operator(o['identifier'],{o['key']:v},'INVOKE_DEFAULT'))
        elif node.kind=='operator':
            identifier=o['identifier'];kwargs=vars(o['props']).copy()
            if identifier in {'object.nms_connect','bbeplus.connect'}:
                field='routing' if identifier=='object.nms_connect' else 'route'
                self.open_choices(node,[('CHAIN',i18n.interface('Chain (Series)'),i18n.tooltip('Source to first device, then device to device')),
                                        ('FAN',i18n.interface('Fan (Parallel)'),i18n.tooltip('Source directly to every device'))],
                                  lambda value:self.queue_operator(identifier,{**kwargs,field:value},'EXEC_DEFAULT'))
                return {'RUNNING_MODAL'}
            if identifier=='bbe.select_corvette':
                # A choice updates the current view; it is not a deferred tool
                # launch. Apply it and return to the parent in the same event.
                result=operation(identifier)('EXEC_DEFAULT',**kwargs)
                if 'FINISHED' in result and self.stack:self.menu,self.scroll=self.stack.pop()
                self.rebuild(context)
                return {'RUNNING_MODAL'}
            if identifier=='bbeplus.workspace_help':
                from .workspace import HELP
                title,lines=HELP.get(kwargs.get('topic'),HELP['HOME'])
                root=Layout()
                for line in lines:root.label(text=i18n.interface(line),icon='INFO')
                self.stack.append((self.menu,self.scroll));self.root=root;self.title=title;self.scroll=0
                self.leaves,self.content_height=layout_tree(root,self.width-24)
                for leaf,_ in self.leaves:leaf.can_click=False
                self.height=min(self.content_height+68,self.region.height/self.scale-20)
                self.top=max(self.top,self.height+8);self.help_open=True
                return {'RUNNING_MODAL'}
            if identifier=='bbeplus.layout':
                operation(identifier)('EXEC_DEFAULT',**kwargs);self.rebuild(context)
            else:
                mode='INVOKE_DEFAULT' if identifier in {'object.nms_connect','bbeplus.connect'} else node.inherited('operator_context','INVOKE_DEFAULT')
                keep=self.queue_operator(identifier,kwargs,mode)
                return {'RUNNING_MODAL'} if keep else {'FINISHED'}
        self.area.tag_redraw();return {'RUNNING_MODAL'}

    def queue_operator(self,identifier,kwargs,mode):
        window,area,region=self.window,self.area,self.region
        if identifier=='bbe.start_cable_connection':
            kwargs.update(launch_x=round(self.mouse[0]+region.x),launch_y=round(self.mouse[1]+region.y),launch_ready=True)
        if identifier=='bbeplus.wire':
            kwargs.update(launch_x=int(self.mouse[0]+region.x),launch_y=int(self.mouse[1]+region.y))
        op=operation(identifier)
        cls=bpy.types.Operator.bl_rna_get_subclass_py(op.get_rna_type().identifier)
        # Immediate edits stay open; dialogs and viewport tools take over input.
        keep=bool(cls and not hasattr(cls,'modal') and
                  (mode.startswith('EXEC') or not hasattr(cls,'invoke')))
        if identifier in {'object.nms_connect','bbeplus.connect'}:keep=False
        # These execute-only launchers open Curve Suite indirectly. Its modal
        # tools must receive the next viewport event, just like cable placement.
        if identifier.split('.')[-1] in {'duplicate_axis','duplicate_edge_path','align_geometry','start_shape','shape_assets','curve_add','curve_draw','curve_from_surface','curve_array','curve_studio','nms_duplicate_along_curve'}:
            keep=False
        if not keep:self.finish()
        def run():
            if not any(w==window for w in bpy.context.window_manager.windows):return
            if not any(a==area for a in window.screen.areas):return
            try:
                with bpy.context.temp_override(window=window,area=area,region=region):
                    op=operation(identifier)
                    if op.poll():
                        result=op('EXEC_DEFAULT' if mode.startswith('EXEC') else 'INVOKE_DEFAULT',**kwargs)
                        cls=bpy.types.Operator.bl_rna_get_subclass_py(op.get_rna_type().identifier)
                        # Timer-dispatched, immediately finished operators do not
                        # get Blender's button-event Undo checkpoint automatically.
                        if result=={'FINISHED'} and 'UNDO' in getattr(cls, 'bl_options', ()):
                            bpy.ops.ed.undo_push(message=cls.bl_label)
                        if keep and _sessions.get(self.key) is self:
                            if 'RUNNING_MODAL' in result:self.finish()
                            else:
                                self.rebuild(bpy.context);self.area.tag_redraw()
            except Exception as error:
                if PLUS:
                    from . import release_tools
                    release_tools.note(str(error))
                print('Builder menu action:',identifier,error)
        bpy.app.timers.register(run,first_interval=.01)
        return keep

    def modal(self,context,event):
        try:return self.handle_event(context,event)
        except Exception as error:
            self.finish()
            self.report({'ERROR'},'BBE+ menu: '+str(error))
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

    def handle_event(self,context,event):
        if _sessions.get(self.key) is not self:return {'CANCELLED'}
        if context.window!=self.window:return {'PASS_THROUGH'}
        if event.type in {'WINDOW_DEACTIVATE'}:self.finish();return {'CANCELLED'}
        if event.type in {'MOUSEMOVE','LEFTMOUSE','RIGHTMOUSE','WHEELUPMOUSE','WHEELDOWNMOUSE'}:
            self.mouse=(event.mouse_x-self.region.x,event.mouse_y-self.region.y)
        x,y=self.mouse;s=self.scale
        if self.panel_drag or self.menu_drag:
            return self.settings_drag_event(context, event)
        if self.list_drag:
            if event.type=='MOUSEMOVE' and self.scroll_list_to(context,y):self.rebuild(context)
            if event.type in {'ESC','RIGHTMOUSE'} or (event.type=='LEFTMOUSE' and event.value=='RELEASE'):self.list_drag=None
            return {'RUNNING_MODAL'}
        if (event.type=='LEFTMOUSE' and event.value=='PRESS' and not (self.dropdown or self.edit)
                and self.grab_list(x,y)):
            if self.scroll_list_to(context,y):self.rebuild(context)
            return {'RUNNING_MODAL'}
        if self.number_drag:
            drag=self.number_drag;node=drag['node'];data,key=node.options['data'],node.options['key']
            prop=data.bl_rna.properties[key]
            if event.type in {'ESC','RIGHTMOUSE'} and event.value=='PRESS':
                self.number_drag=None;self.set_property(node,drag['value']);return {'RUNNING_MODAL'}
            if event.type=='MOUSEMOVE' and (drag['moved'] or math.dist(drag['origin'],self.mouse)>4*s):
                drag['moved']=True
                step=1 if prop.type=='INT' else max(.01,abs(drag['value'])*.01)
                if node.options.get('slider') and 0<prop.soft_max-prop.soft_min<1e6:
                    step=(prop.soft_max-prop.soft_min)/(self.width*s)
                value=drag['value']+(x-drag['origin'][0])*step*(.1 if event.shift else 1)
                self.set_property(node,value)
            elif event.type=='LEFTMOUSE' and event.value=='RELEASE':
                self.number_drag=None
                if drag['moved']:self.property_checkpoint(node)
                else:self.edit={'node':node,'text':str(numeric_value(node)),'replace':True}
            self.area.tag_redraw();return {'RUNNING_MODAL'}
        if self.edit:
            if event.value=='PRESS':
                if event.type=='ESC':self.edit=None
                elif event.type in {'RET','NUMPAD_ENTER','TAB'}:
                    try:self.set_property(self.edit['node'],self.edit['text'])
                    except (ValueError,TypeError) as exc:self.message=str(exc);self.edit=None
                elif event.type=='BACK_SPACE':self.edit['text']='' if self.edit['replace'] else self.edit['text'][:-1];self.edit['replace']=False
                elif event.ctrl and event.type=='A':self.edit['replace']=True
                elif event.ctrl and event.type=='V':self.edit['text']=context.window_manager.clipboard;self.edit['replace']=False
                elif event.unicode and not event.ctrl:self.edit['text']=('' if self.edit['replace'] else self.edit['text'])+event.unicode;self.edit['replace']=False
                elif event.type=='LEFTMOUSE':
                    try:self.set_property(self.edit['node'],self.edit['text'])
                    except (ValueError,TypeError):self.edit=None
            self.area.tag_redraw();return {'RUNNING_MODAL'}
        if event.type in {'ESC','RIGHTMOUSE'} and event.value=='PRESS':
            if event.type=='RIGHTMOUSE' and not inside((self.left*s,(self.top-self.height)*s,self.width*s,self.height*s),x,y):
                self.finish();return {'FINISHED','PASS_THROUGH'}
            if self.dropdown:self.dropdown=None;self.area.tag_redraw();return {'RUNNING_MODAL'}
            if self.stack:self.menu,self.scroll=self.stack.pop();self.help_open=False;self.rebuild(context);return {'RUNNING_MODAL'}
            self.finish();return {'CANCELLED'}
        if event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE'} and not self.dropdown:
            listing=next((n for n,r in self.leaves if n.kind=='list_scroll' and inside(self.rect(r),x,y) and self.visible_list_point(self.rect(r),y)),None)
            if listing:
                step=-1 if event.type=='WHEELUPMOUSE' else 1
                offset=max(0,min(listing.options['total']-listing.options['rows'],listing.options['offset']+step))
                if offset != listing.options['offset']:
                    setattr(context.window_manager,listing.options['offset_key'],offset)
                    self.rebuild(context);return {'RUNNING_MODAL'}
        if event.ctrl and event.type in {'Z','Y'} and event.value=='PRESS':
            self.finish();return {'PASS_THROUGH'}
        if self.dropdown:
            d=self.dropdown;left,top,w,count=self.choice_geometry()
            if event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE'}:
                d['offset']=max(0,min(len(d['items'])-count,d['offset']+(-1 if event.type=='WHEELUPMOUSE' else 1)))
            if event.type == 'LEFTMOUSE' and event.value in {'PRESS', 'RELEASE'}:
                index = math.floor((top-y)/(31*s))
                item = d['items'][index+d['offset']] if left <= x <= left+w and 0 <= index < count else None
                if event.value == 'PRESS' and item is None:
                    self.dropdown = None
                elif event.value == 'PRESS' and d.get('require_release'):
                    d['pressed_item'] = item
                elif item and (event.value == 'PRESS' or d.pop('pressed_item', None) == item):
                    self.dropdown = None
                    d['callback'](item[0])
                    if _sessions.get(self.key) is not self:return {'FINISHED'}
                elif event.value == 'RELEASE':
                    d.pop('pressed_item', None)
            self.area.tag_redraw();return {'RUNNING_MODAL'}
        if event.type=='TIMER':
            if time.monotonic()-self.last_refresh<.30:return {'PASS_THROUGH'}
            self.last_refresh=time.monotonic()
            if self.menu in {'RECOVERY','IO','HOME','CHAT'} and not getattr(self,'help_open',False):self.rebuild(context)
            elif self.hover:self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        panel=(self.left*s,(self.top-self.height)*s,self.width*s,self.height*s)
        if event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE'} and inside(panel,x,y):
            self.scroll=max(0,min(max(0,self.content_height-(self.height-68)),self.scroll+(-42 if event.type=='WHEELUPMOUSE' else 42)))
            self.hover=self.hit_test(x,y);self.last_hover=time.monotonic()
            self.area.tag_redraw();return {'RUNNING_MODAL'}
        hit=self.hit_test(x,y)
        if event.type == 'LEFTMOUSE':
            # Blender puts a dialog's confirmation button under the pointer. Open it after release.
            identifier = hit.options.get('identifier') if hit else None
            opens_dialog = identifier == 'object.nms_group_objects' or (
                self.menu == 'MENU:BBE_MT_recovery' and identifier == 'bbe.open_recovery')
            target = hit if opens_dialog else None
            if event.value == 'PRESS' and target:
                self.pressed_dialog_button = target
                return {'RUNNING_MODAL'}
            if event.value == 'RELEASE' and getattr(self, 'pressed_dialog_button', None):
                pressed, self.pressed_dialog_button = self.pressed_dialog_button, None
                if target is pressed:
                    return self.activate(target, context)
                return {'RUNNING_MODAL'}
        if self.menu=='SETTINGS' and hit is None:
            hit=next((n for n,r in self.leaves if n.kind=='label' and self.visible(self.rect(r)) and inside(self.rect(r),x,y)),None)
        if event.type=='MOUSEMOVE':
            if self.hover is not hit:self.hover=hit;self.last_hover=time.monotonic();self.area.tag_redraw()
            if self.drag:self.area.tag_redraw()
            if not inside(panel,x,y) and not self.drag:return {'PASS_THROUGH'}
        if event.type=='LEFTMOUSE' and event.value=='PRESS':
            if not inside(panel,x,y):
                from . import toolbar_surface
                top_menu=self.stack[0][0] if self.stack else self.menu
                same=any(n.kind=='operator' and getattr(n.options.get('props'),'menu',None)==top_menu and inside(rect,event.mouse_x,event.mouse_y)
                         for n,rect in toolbar_surface._bounds.get((self.window.as_pointer(),self.area.as_pointer(),'TOOL_HEADER'),()))
                self.finish()
                return {'FINISHED'} if same else {'PASS_THROUGH'}
            if y>(self.top-45)*s:
                if self.menu in {'WORKSPACE', 'HOW_TO'} and x > (self.left+self.width-38)*s:
                    self.finish()
                    return {'FINISHED'}
                if not PLUS and self.menu in {'WORKSPACE', 'SETTINGS', 'HOW_TO'}:
                    self.panel_drag = (x/s-self.left, y/s-self.top, (self.left,self.top))
                    return {'RUNNING_MODAL'}
                if x>(self.left+self.width-34)*s and self.header_help:
                    if getattr(self,'help_open',False) and self.stack:
                        self.menu,self.scroll=self.stack.pop();self.help_open=False;self.rebuild(context)
                    else:return self.activate(self.header_help,context)
                    return {'RUNNING_MODAL'}
                if self.stack:self.menu,self.scroll=self.stack.pop();self.help_open=False;self.rebuild(context)
            elif hit and hit.kind == 'menu_grip':
                self.menu_drag = (hit.options['surface'], hit.options['menu'])
                return {'RUNNING_MODAL'}
            elif PLUS and self.menu=='SETTINGS' and hit and hit.kind=='label':
                from . import menu_backend as workspace
                labels=workspace.SIDE_LABELS if workspace.support.prefs().workspace_tab=='SIDE' else {k:l for k,l,_ in workspace.TOOLS}
                key=next((key for key,label in labels.items() if i18n.interface(label)==leaf_text(hit)),None)
                if key:self.drag=(key,self.mouse)
            elif hit:return self.activate(hit,context)
        if event.type=='LEFTMOUSE' and event.value=='RELEASE' and self.drag:
            from . import menu_backend as workspace,workspace_support
            source,start=self.drag;self.drag=None
            side=workspace_support.prefs().workspace_tab=='SIDE'
            names=workspace.SIDE_LABELS if side else {k:l for k,l,_ in workspace.TOOLS}
            labels=[(n,self.rect(r)) for n,r in self.leaves if n.kind=='label' and any(i18n.interface(label)==leaf_text(n) for label in names.values())]
            if labels and math.dist(start,self.mouse)>5*s:
                target=min(labels,key=lambda item:abs(item[1][1]+item[1][3]/2-y))[0]
                dest=next(key for key,label in names.items() if i18n.interface(label)==leaf_text(target))
                order=workspace.sidebar_order() if side else workspace.menu_order();position=order.index(dest);order.remove(source);order.insert(position,source)
                workspace_support.set_list('sidebar_order' if side else 'toolbar_order',order)
                if side:workspace.apply_sidebar_order()
                self.rebuild(context)
            self.area.tag_redraw()
        return {'PASS_THROUGH'} if event.type=='MOUSEMOVE' else {'RUNNING_MODAL'}

    def finish(self):
        _sessions.pop(self.key,None)
        if getattr(self,'handler',None):
            bpy.types.SpaceView3D.draw_handler_remove(self.handler,'WINDOW');self.handler=None
        if getattr(self,'timer',None):
            try:bpy.context.window_manager.event_timer_remove(self.timer)
            except (ReferenceError,RuntimeError):pass
            self.timer=None
        self.dropdown=None;self.edit=None;self.number_drag=None;self.root=None;self.leaves=[]
        try:self.area.tag_redraw()
        except ReferenceError:pass

    def cancel(self,context):self.finish()


@persistent
def stop(*_):
    for session in tuple(_sessions.values()):
        try:session.finish()
        except (ReferenceError,RuntimeError):pass
    _sessions.clear()



class BBEPLUS_OT_custom_menu(MenuSurface, bpy.types.Operator):
    bl_idname=PREFIX+'.custom_menu'
    bl_label='BBE+ Tool Menu'
    bl_description='Open the compact BBE+ graphical tool menu'
    bl_options={'INTERNAL'}
    menu:bpy.props.StringProperty(default='HOME')
    anchor_x:bpy.props.IntProperty(default=-1)
    anchor_y:bpy.props.IntProperty(default=-1)
    anchor_center:bpy.props.BoolProperty(default=False)


BBEPLUS_OT_custom_menu.__name__ = ('BBEPLUS' if PLUS else 'BBE')+'_OT_custom_menu'

class MenuLauncher(bpy.types.Operator):
    bl_idname=PREFIX+'.open_menu'
    bl_label='Builder Menu'
    bl_description='Open this tool menu'
    bl_options={'INTERNAL'}
    menu:bpy.props.StringProperty(default='HOME')
    from_arrow:bpy.props.BoolProperty(default=False)
    def invoke(self,context,event):
        window,area=context.window,context.area
        region=next((r for r in area.regions if r.type=='WINDOW'),None)
        from . import toolbar_surface
        anchor_menu='SHAPES' if self.menu=='NEW_SHAPE' else self.menu
        rect=next((rect for node,rect in toolbar_surface._bounds.get((window.as_pointer(),area.as_pointer(),'TOOL_HEADER'),[])
                   if node.kind=='operator' and getattr(node.options['props'],'menu',None)==anchor_menu),None)
        x=round(rect[0]+rect[2]/2) if rect else area.x+area.width//2
        headers=[r for r in area.regions if r.type=='TOOL_HEADER' and r.height>1]
        y=round(rect[1]-3) if rect else (headers[0].y-3 if headers else area.y+area.height-30)
        key=self.menu
        def run():
            if window not in bpy.context.window_manager.windows[:] or area not in window.screen.areas[:]:return
            with bpy.context.temp_override(window=window,area=area,region=region):
                getattr(getattr(bpy.ops,PREFIX),'custom_menu')('INVOKE_DEFAULT',menu=key,anchor_x=x,anchor_y=y,anchor_center=True)
        bpy.app.timers.register(run,first_interval=.01)
        return {'FINISHED'}

MenuLauncher.__name__=('BBEPLUS' if PLUS else 'BBE')+'_OT_open_menu'

class PickObjectColour(bpy.types.Operator):
    bl_idname=PREFIX+'.pick_object_colour'
    bl_label='Pick Colour from Object'
    bl_description='Click a part in the viewport to copy its palette and colour to the selected parts. Esc cancels'
    bl_options={'UNDO','BLOCKING'}

    @classmethod
    def poll(cls,context):
        return context.area and context.area.type=='VIEW_3D' and context.mode=='OBJECT'

    def invoke(self,context,event):
        self.area=context.area;self.window=context.window
        self.region=next(r for r in self.area.regions if r.type=='WINDOW')
        self.window.cursor_modal_set('EYEDROPPER')
        self.area.header_text_set(i18n.interface('Pick Colour: click a part. Esc cancels.'))
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self,context):
        self.window.cursor_modal_restore();self.area.header_text_set(None)
        self.area.tag_redraw()

    def modal(self,context,event):
        if event.type in {'ESC','RIGHTMOUSE'}:
            self.cancel(context);return {'CANCELLED'}
        if event.type=='LEFTMOUSE' and event.value=='PRESS':
            from bpy_extras.view3d_utils import region_2d_to_origin_3d,region_2d_to_vector_3d
            xy=(event.mouse_x-self.region.x,event.mouse_y-self.region.y)
            if not (0<=xy[0]<self.region.width and 0<=xy[1]<self.region.height):return {'RUNNING_MODAL'}
            rv3d=self.area.spaces.active.region_3d
            origin=region_2d_to_origin_3d(self.region,rv3d,xy)
            direction=region_2d_to_vector_3d(self.region,rv3d,xy)
            from .viewport_cutaway import scene_pick
            hit,location,normal,index,obj,matrix=scene_pick(context.scene,context.evaluated_depsgraph_get(),origin,direction)
            if not hit or not any(k in obj for k in ('ObjectID','UserData','dup_UserData','bbeplus_part_json')):
                self.report({'INFO'},'Click a coloured build part');return {'RUNNING_MODAL'}
            if PLUS:context.scene.bbeplus_color_source=obj.original
            else:context.scene.nms_main.color_picker=obj.original
            self.cancel(context);return {'FINISHED'}
        return {'PASS_THROUGH'} if event.type in {'MIDDLEMOUSE','WHEELUPMOUSE','WHEELDOWNMOUSE','MOUSEMOVE'} else {'RUNNING_MODAL'}

PickObjectColour.__name__=('BBEPLUS' if PLUS else 'BBE')+'_OT_pick_object_colour'

def toolbar_button(layout,key,label,**art):
    row=layout.row(align=True)
    row.operator(PREFIX+'.open_menu',text=label,emboss=False,**art).menu=key
    if label:
        arrow=row.row(align=True);arrow.scale_x=.55
        op=arrow.operator(PREFIX+'.open_menu',text='',emboss=False,icon='DOWNARROW_HLT')
        op.menu=key;op.from_arrow=True


def register():
    setattr(bpy.types.WindowManager,PREFIX+'_prefab_offset',bpy.props.IntProperty(default=0,min=0))
    setattr(bpy.types.WindowManager,PREFIX+'_prefab_search',bpy.props.StringProperty(name='Search Local Prefabs',update=lambda self,ctx:setattr(self,PREFIX+'_prefab_offset',0)))
    from . import menu_backend
    if not PLUS and menu_backend._icons is None:menu_backend._icons=bpy.utils.previews.new()
    bpy.utils.register_class(BBEPLUS_OT_custom_menu)
    bpy.utils.register_class(MenuLauncher)
    bpy.utils.register_class(PickObjectColour)
    from . import toolbar_surface
    toolbar_surface.register()
    if not PLUS:
        from . import sidebar_builder
        sidebar_builder.register()
    from . import asset_strip
    asset_strip.register()
    from . import menu_contract
    bpy.app.timers.register(menu_contract.skin_sidebars,first_interval=.2)
    for handlers in (bpy.app.handlers.load_pre,bpy.app.handlers.undo_pre,bpy.app.handlers.redo_pre):handlers.append(stop)


def unregister():
    if not PLUS:
        from . import sidebar_builder
        sidebar_builder.unregister()
    from . import toolbar_surface
    from . import asset_strip
    asset_strip.unregister()
    toolbar_surface.unregister()
    from . import menu_contract
    if bpy.app.timers.is_registered(menu_contract.skin_sidebars):bpy.app.timers.unregister(menu_contract.skin_sidebars)
    menu_contract.unskin_sidebars()
    stop();_textures.clear()
    for key in ('_prefab_search','_prefab_offset'):
        if hasattr(bpy.types.WindowManager,PREFIX+key):delattr(bpy.types.WindowManager,PREFIX+key)
    for handlers in (bpy.app.handlers.load_pre,bpy.app.handlers.undo_pre,bpy.app.handlers.redo_pre):
        if stop in handlers:handlers.remove(stop)
    bpy.utils.unregister_class(MenuLauncher)
    bpy.utils.unregister_class(PickObjectColour)
    bpy.utils.unregister_class(BBEPLUS_OT_custom_menu)
    from . import menu_backend
    menu_backend.cleanup()

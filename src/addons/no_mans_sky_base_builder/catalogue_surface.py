"""FuriousFurby catalogue cards with independent thumbnail and download targets."""
import math
import time
import bpy, gpu, blf
from gpu_extras.batch import batch_for_shader
from . import community_prefabs as data, styled_ui as art, curve_widgets as paint, i18n, menu_surface as menu_art

PLUS=__package__.endswith('bbe_plus')
PREFIX='bbeplus' if PLUS else 'bbe'
_sessions=[]
_state={'grid_height':None,'scroll':0}

# Native HAND_POINT supplies its own bitmap size and hotspot. Here the first
# fingertip pixel is the click coordinate, in the same region as the title.
def link_pointer_batch(shader):
    rows = (
        '     ##',
        '    #..#',
        '    #..#',
        '    #..#',
        '    #..#',
        '    #..###',
        '    #..#..###',
        '    #..#..#..##',
        ' ## #..#..#..#.#',
        '#..##..........#',
        ' #..#..........#',
        '  #............#',
        '   #...........#',
        '    #..........#',
        '     #........#',
        '      #.......#',
        '      #......#',
        '      ########',
    )
    vertices, colors = [], []
    for row, pixels in enumerate(rows):
        for column, pixel in enumerate(pixels):
            if pixel == ' ':
                continue
            x, y = column-5, -row
            vertices.extend(((x,y), (x+1,y), (x+1,y+1), (x,y), (x+1,y+1), (x,y+1)))
            color = (1,1,1,1) if pixel == '.' else (.025,.025,.025,1)
            colors.extend([color]*6)
    return batch_for_shader(shader, 'TRIS', {'pos':vertices, 'color':colors})


def inside(rect,x,y):
    a,b,w,h=rect;return a<=x<=a+w and b<=y<=b+h

def action(name):return getattr(getattr(bpy.ops,PREFIX),'prefab_catalogue_'+name)

class CatalogueSurface(bpy.types.Operator):
    bl_idname=PREFIX+'.prefab_catalogue_window'
    bl_label='Online Community Prefabs'
    bl_description='Browse community prefabs with large images; drag the bottom grip to resize'
    bl_options={'INTERNAL','BLOCKING'}
    anchor_x:bpy.props.IntProperty(default=-1,options={'SKIP_SAVE'})
    anchor_y:bpy.props.IntProperty(default=-1,options={'SKIP_SAVE'})

    def invoke(self,context,event):
        if not context.area or context.area.type!='VIEW_3D':return {'CANCELLED'}
        cancel_all()
        self.window=context.window;self.area=context.area;self.scene=context.scene;self.workspace=context.workspace
        self.region=next(r for r in self.area.regions if r.type=='WINDOW')
        self.tab_offset=0
        self.scale=max(.65,context.preferences.system.ui_scale*.88)
        self.left_limit=0
        self.right=self.region.width
        for panel in self.area.regions:
            if panel.type=='TOOLS' and panel.width>1 and self.area.spaces.active.show_region_toolbar:self.left_limit=panel.width
            if panel.type=='UI' and panel.width>1 and self.area.spaces.active.show_region_ui:
                self.right=min(self.right,panel.x-self.region.x)
        self.width=min(540*self.scale,max(220,self.right-self.left_limit-16))
        ax=self.anchor_x if self.anchor_x>=0 else event.mouse_x
        ay=self.anchor_y if self.anchor_y>=0 else event.mouse_y
        self.left=max(self.left_limit+8,min(ax-self.region.x-self.width*.55,self.right-self.width-8))
        self.top=self.region.height-64*self.scale
        self.preferred_height=_state['grid_height'];self.active_cursor=None;self.scroll=_state['scroll'];self.preview=None
        self.query=getattr(context.window_manager,PREFIX+'_catalogue_query','')
        self.edit=False;self.select_all=False;self.hover=None;self.mouse=(-1,-1);self.drag=None;self.moving=None
        self.pointer_batch=None
        self.closed=False;self.signature=tuple(e['id'] for e in data._items)
        self.since=time.monotonic();self.targets=[];self.shader=gpu.shader.from_builtin('UNIFORM_COLOR')
        self.reflow()
        self.handler=bpy.types.SpaceView3D.draw_handler_add(self.draw_canvas,(),'WINDOW','POST_PIXEL')
        self.timer=context.window_manager.event_timer_add(.15,window=self.window)
        _sessions.append(self);context.window_manager.modal_handler_add(self)
        if not data._busy:
            data._source_cache=(0,[])
            data._start(context,data.search,data._source,self.query,data._offset if data._open else 0)
        self.area.tag_redraw();return {'RUNNING_MODAL'}

    def reflow(self):
        s=self.scale;self.cell=(self.width-36*s)/2;self.thumb=self.cell*.66;self.pitch=self.thumb+28*s
        self.by_id={source['id']:source for source in data._sources}
        self.community=self.by_id.get(data._source)
        # Keep the image itself at Discord's 48-unit server size at normal UI scale.
        self.tab_size=48*max(.75,bpy.context.preferences.system.ui_scale)/s+6
        self.extra=(self.tab_size+34)*s if data._sources else 0
        fixed=140*s+self.extra
        ceiling=self.region.height-64*s
        desired=(self.preferred_height*s if self.preferred_height is not None else 2*self.pitch)
        minimum=min(self.pitch,max(32*s,ceiling-fixed-8))
        self.top=max(min(ceiling,fixed+minimum+8),min(self.top,ceiling))
        self.grid_height=max(minimum,min(desired,self.top-fixed-8))
        self.height=fixed+self.grid_height
        visible_rows=max(1,math.floor(self.grid_height/self.pitch+1e-6))
        self.scroll=max(0,min(self.scroll,max(0,math.ceil(len(data._items)/2)-visible_rows)))
        self.targets=[]
        def add(key,x,y,w,h):
            rect=(self.left+x*s,self.top-(y+h)*s,w*s,h*s);self.targets.append((key,rect));return rect
        add('close',self.width/s-35,11,24,24)
        add('upload',self.width/s-70,11,24,24)
        add('move',14,8,self.width/s-95,32)
        add('query',12,51,self.width/s-108,30)
        add('search',self.width/s-89,51,77,30)
        if self.extra:
            span=self.width/s-24
            step=self.tab_size+4
            overflow=len(data._sources)>int(span//step)
            self.tab_count=max(1,int((span-(52 if overflow else 0))//step))
            self.tab_offset=max(0,min(self.tab_offset,len(data._sources)-self.tab_count))
            if overflow:
                add('tabs_previous',12,86,23,self.tab_size)
                add('tabs_next',self.width/s-35,86,23,self.tab_size)
            for j,item in enumerate(data._sources[self.tab_offset:self.tab_offset+self.tab_count]):
                add('source:'+item['id'],12+(26 if overflow else 0)+j*step,86,self.tab_size,self.tab_size)
            if self.community:
                name=self.community.get('serverName') or self.community['name']
                channel=self.community.get('channelName') or self.community['name']
                self.channel_text=art.trim('#'+channel,self.width*.43,11*s)
                available=self.width-34*s-blf.dimensions(0,self.channel_text)[0]
                self.server_text=art.trim(name,available,14*s)
                title_width=blf.dimensions(0,self.server_text)[0]/s+4
                add('server_title',12,90+self.tab_size,title_width,23)
        self.grid_top=self.top-104*s-self.extra
        self.cards=[]
        self.grid_bottom=self.grid_top-self.grid_height
        def card_hit(key,rect):
            x,y,w,h=rect
            bottom=max(y,self.grid_bottom)
            top=min(y+h,self.grid_top)
            if top>bottom:self.targets.append((key,(x,bottom,w,top-bottom)))
        for index in range(self.scroll*2,min(len(data._items),(self.scroll+math.ceil(self.grid_height/self.pitch))*2)):
            row,col=divmod(index-self.scroll*2,2)
            x=self.left+12*s+col*(self.cell+12*s);y=self.grid_top-row*self.pitch-self.thumb
            rect=(x,y,self.cell,self.thumb);self.cards.append((index,rect))
            card_hit('image:'+str(index),rect)
            card_hit('download:'+str(index),(x+self.cell-32*s,y+self.thumb-32*s,28*s,28*s))
        bottom=self.top-self.height
        self.targets.extend([('previous',(self.left+12*s,bottom+7*s,65*s,23*s)),
                             ('grip',(self.left+82*s,bottom+2*s,max(20*s,self.width-164*s),30*s)),
                             ('next',(self.left+self.width-77*s,bottom+7*s,65*s,23*s))])

    def label(self,text,x,y,size=12,color=None):
        paint.text(i18n.interface(text),x,y,size*self.scale,color or art.TEXT)

    def badge(self,text,x,y,maxwidth):
        s=self.scale;text=art.trim(text,maxwidth-12*s,11*s);blf.size(0,11*s);w=blf.dimensions(0,text)[0]+12*s
        paint.rounded(self.shader,x,y,w,21*s,4*s,(.035,.025,.05,.82))
        self.label(text,x+6*s,y+6*s,11,(1,1,1,1))

    def draw_canvas(self):
        if self.closed or bpy.context.area!=self.area or bpy.context.region!=self.region:return
        art.theme(bpy.context)
        self.reflow();s=self.scale;bottom=self.top-self.height
        with paint.canvas(bpy.context):
            art.panel(self.shader,self.left,bottom,self.width,self.height,s)
            self.label('Online Community Prefabs',self.left+15*s,self.top-29*s,15)
            for key,rect in self.targets:
                x,y,w,h=rect
                if key in {'query','search'}:
                    paint.rounded(self.shader,x,y,w,h,6*s,art.PRIMARY if key=='search' else art.EDGE)
                    if key=='query':paint.rounded(self.shader,x+s,y+s,w-2*s,h-2*s,5*s,art.INK)
                elif self.hover==key and key not in {'move','grip','server_title'} and not key.startswith(('image:','download:')):
                    paint.rounded(self.shader,x,y,w,h,5*s,art.HOVER)
                if key=='query':
                    value=self.query+('|' if self.edit else '')
                    if self.select_all:paint.rounded(self.shader,x+4*s,y+3*s,w-8*s,h-6*s,3*s,art.HOVER)
                    self.label(art.trim(value or 'Search prefabs',w-16*s,12*s),x+8*s,y+10*s,12,art.TEXT if value else art.MUTED)
                elif key=='search':self.label('Search',x+12*s,y+10*s)
                elif key in {'upload','close'}:menu_art.draw_image(menu_art.outline_icon('upload' if key=='upload' else 'x'),x+3*s,y+3*s,18*s,18*s)
                elif key in {'previous','next'}:
                    enabled=data._offset>0 if key=='previous' else data._offset+len(data._items)<data._total
                    self.label('‹ Previous' if key=='previous' else 'Next ›',x+3*s,y+7*s,11,art.TEXT if enabled else art.MUTED)
                elif key=='grip':
                    for dy in (12,17):
                        paint.line(self.shader,(x+w/2-24*s,y+dy*s),(x+w/2+24*s,y+dy*s),2*s,
                                   art.ACCENT if self.active_cursor=='SCROLL_Y' else art.MUTED)
                elif key.startswith('source:'):
                    entry=self.by_id[key[7:]]
                    border=art.ACCENT if entry['id']==data._source else art.HOVER if self.hover==key else art.EDGE
                    paint.rounded(self.shader,x,y,w,h,7*s,border)
                    paint.rounded(self.shader,x+2*s,y+2*s,w-4*s,h-4*s,5*s,art.SURFACE)
                    icon_key=data.server_icon_key(entry)
                    thumb=data._icons.get(icon_key) if icon_key and data._icons else None
                    if not art.image(thumb,x+3*s,y+3*s,w-6*s,h-6*s):
                        initials=''.join(word[0] for word in (entry.get('serverName') or entry['name']).split()[:2]).upper()
                        paint.text(initials,x+w/2,y+h/2-6*s,16*s,art.TEXT,align='CENTER')
                elif key in {'tabs_previous','tabs_next'}:
                    self.label('‹' if key=='tabs_previous' else '›',x+6*s,y+9*s,16)
                elif key=='server_title':
                    linked=bool(data.invite_link(self.community))
                    self.label(self.server_text,x+2*s,y+5*s,14,art.ACCENT if linked else art.TEXT)
                    if linked:
                        paint.line(self.shader,(x+2*s,y+2*s),(x+w-2*s,y+2*s),s,art.ACCENT)
                    self.label(self.channel_text,x+w+8*s,y+5*s,11,art.MUTED)
            self.label(art.trim(data._status,self.width-28*s,11*s),self.left+14*s,self.grid_top+7*s,11,art.MUTED)
            self.draw_cards()
            if self.preview is None and self.hover and self.hover.startswith('source:') and time.monotonic()-self.since>.45:
                entry=self.by_id.get(self.hover[7:])
                if entry:
                    tip=(entry.get('serverName') or entry['name'])+' · #'+(entry.get('channelName') or entry['name'])
                    width=min(self.width-24*s,blf.dimensions(0,tip)[0]+24*s)
                    self.badge(tip,min(self.mouse[0],self.left+self.width-width-12*s),self.top-80*s,width)
            if self.preview is not None:self.draw_preview()
            elif self.active_cursor == 'LINK':
                if self.pointer_batch is None:
                    self.pointer_shader = gpu.shader.from_builtin('FLAT_COLOR')
                    self.pointer_batch = link_pointer_batch(self.pointer_shader)
                with gpu.matrix.push_pop():
                    gpu.matrix.translate((*self.mouse, 0))
                    self.pointer_shader.bind()
                    self.pointer_batch.draw(self.pointer_shader)

    def draw_cards(self):
        s=self.scale
        previous=gpu.state.scissor_get()
        vx,vy,_,_=gpu.state.viewport_get()
        gpu.state.scissor_test_set(True)
        gpu.state.scissor_set(int(vx+self.left),int(vy+self.grid_bottom),int(self.width),max(1,math.ceil(self.grid_height)))
        try:
            for index,rect in self.cards:
                x,y,w,h=rect;entry=data._items[index]
                paint.rounded(self.shader,x-1,y-1,w+2,h+2,5*s,art.ACCENT if self.hover=='image:'+str(index) else art.EDGE)
                thumb=data._icons.get(entry['id']) if data._icons else None
                if not art.image(thumb,x,y,w,h,cover=True):
                    paint.rounded(self.shader,x,y,w,h,4*s,art.SURFACE);self.label('No thumbnail' if not entry.get('thumbnail') else 'Loading image…',x+12*s,y+h/2,12,art.MUTED)
                self.badge(entry['author'],x+5*s,y+h-27*s,w-43*s)
                self.badge(str(entry['count'])+' parts',x+5*s,y+5*s,w-10*s)
                dx,dy=x+w-32*s,y+h-32*s
                paint.rounded(self.shader,dx,dy,28*s,28*s,5*s,art.PRIMARY if self.hover=='download:'+str(index) else (.035,.025,.05,.85))
                menu_art.draw_image(menu_art.outline_icon('download',tint=(1,1,1)),dx+5*s,dy+5*s,18*s,18*s)
                self.label(art.trim(entry['title'],w-4*s,12*s),x+2*s,y-18*s,12)
        finally:
            gpu.state.scissor_set(*previous)
            if previous[2]<=0 or previous[3]<=0:gpu.state.scissor_test_set(False)

    def set_cursor(self, cursor):
        if cursor == self.active_cursor:
            return
        if self.active_cursor is not None:
            self.window.cursor_modal_restore()
        if cursor is not None:
            self.window.cursor_modal_set('NONE' if cursor == 'LINK' else cursor)
        self.active_cursor = cursor

    def update_hover(self):
        key = next((key for key, rect in reversed(self.targets) if inside(rect, *self.mouse)), None)
        if key != self.hover:
            self.since = time.monotonic()
        self.hover = key
        cursor = None
        if self.preview is None and self.moving is None:
            if self.drag is not None or key == 'grip':
                cursor = 'SCROLL_Y'
            elif key == 'server_title' and self.community and data.invite_link(self.community):
                cursor = 'LINK'
        self.set_cursor(cursor)

    def draw_preview(self):
        s=self.scale;entry=data._items[self.preview]
        w=min(self.right-self.left_limit-24,900*s);h=min(self.region.height-24,680*s)
        x=self.left_limit+(self.right-self.left_limit-w)/2;y=(self.region.height-h)/2
        paint.rounded(self.shader,0,0,self.region.width,self.region.height,0,(0,0,0,.62))
        art.panel(self.shader,x,y,w,h,s)
        self.label(art.trim(entry['title'],w-65*s,14*s),x+15*s,y+h-28*s,14)
        self.preview_close=(x+w-34*s,y+h-34*s,24*s,24*s)
        menu_art.draw_image(menu_art.outline_icon('x'),x+w-31*s,y+h-31*s,18*s,18*s)
        thumb=data._icons.get(entry['id']) if data._icons else None
        art.image(thumb,x+12*s,y+34*s,w-24*s,h-82*s)
        self.label('Esc or click outside the image to return',x+15*s,y+13*s,11,art.MUTED)
        self.preview_image=(x+12*s,y+34*s,w-24*s,h-82*s)

    def search(self,offset,source=None):
        self.preview=None;self.scroll=0
        setattr(bpy.context.window_manager,PREFIX+'_catalogue_query',self.query)
        data._start(bpy.context,data.search,source or data._source,self.query,offset)

    def close(self):
        if self.closed:return
        self.set_cursor(None)
        self.closed=True;_state.update(grid_height=self.preferred_height,scroll=self.scroll)
        bpy.types.SpaceView3D.draw_handler_remove(self.handler,'WINDOW')
        bpy.context.window_manager.event_timer_remove(self.timer)
        if self in _sessions:_sessions.remove(self)
        try:self.area.tag_redraw()
        except ReferenceError:pass

    def modal(self,context,event):
        try:return self.handle_event(context,event)
        except Exception as error:
            self.close();self.report({'ERROR'},'Catalogue: '+str(error))
            import traceback;traceback.print_exc()
            return {'CANCELLED'}

    def handle_event(self,context,event):
        if self.closed:return {'FINISHED'}
        if context.scene!=self.scene or context.workspace!=self.workspace:self.close();return {'CANCELLED'}
        x,y=event.mouse_x-self.region.x,event.mouse_y-self.region.y
        if event.type in {'MOUSEMOVE', 'LEFTMOUSE', 'RIGHTMOUSE'}:
            self.mouse = (x, y)
        if event.type=='WINDOW_DEACTIVATE':self.close();return {'CANCELLED'}
        if event.type in {'ESC','RIGHTMOUSE'} and event.value=='PRESS':
            if self.preview is not None:self.preview=None
            elif self.edit:self.edit=False;self.select_all=False
            else:self.close();return {'CANCELLED'}
            self.update_hover()
            self.area.tag_redraw();return {'RUNNING_MODAL'}
        if event.type=='TIMER':
            signature=tuple(e['id'] for e in data._items)
            if signature!=self.signature:self.signature=signature;self.scroll=0;self.preview=None
            self.update_hover()
            self.area.tag_redraw();return {'RUNNING_MODAL'}
        if self.edit and event.value=='PRESS':
            if event.type in {'RET','NUMPAD_ENTER'}:self.edit=False;self.search(0)
            elif event.ctrl and event.type=='A':self.select_all=True
            elif event.ctrl and event.type=='V':self.query=('' if self.select_all else self.query)+context.window_manager.clipboard[:180];self.select_all=False
            elif event.type=='BACK_SPACE':self.query='' if self.select_all else self.query[:-1];self.select_all=False
            elif event.unicode and not event.ctrl:self.query=('' if self.select_all else self.query)+event.unicode;self.select_all=False
            self.query=self.query[:180]
        if event.type=='MOUSEMOVE':
            if self.drag:
                self.preferred_height=(self.drag[1]+self.drag[0]-y)/self.scale
                self.reflow()
                self.preferred_height=self.grid_height/self.scale
            if self.moving:self.left=max(self.left_limit+8,min(self.moving[2]+x-self.moving[0],self.right-self.width-8));self.top=self.moving[3]+y-self.moving[1]
        if event.type=='LEFTMOUSE' and event.value=='RELEASE':
            self.drag=None;self.moving=None
        if event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE'} and self.preview is None:
            self.scroll+=-1 if event.type=='WHEELUPMOUSE' else 1
        if event.type=='LEFTMOUSE' and event.value=='PRESS':
            if self.preview is not None:
                if inside(self.preview_close,x,y) or not inside(self.preview_image,x,y):self.preview=None
            else:
                key=next((key for key,rect in reversed(self.targets) if inside(rect,x,y)),None)
                self.edit=key=='query';self.select_all=False
                if key=='close':self.close();return {'FINISHED'}
                elif key=='grip':self.drag=(y,self.grid_height)
                elif key=='move':self.moving=(x,y,self.left,self.top)
                elif key=='search' and not data._busy:self.search(0)
                elif key=='previous' and data._offset and not data._busy:self.search(max(0,data._offset-data.PAGE))
                elif key=='next' and data._offset+len(data._items)<data._total and not data._busy:self.search(data._offset+data.PAGE)
                elif key=='tabs_previous':self.tab_offset-=self.tab_count
                elif key=='tabs_next':self.tab_offset+=self.tab_count
                elif key=='server_title' and self.community and data.invite_link(self.community):
                    bpy.ops.wm.url_open(url=data.invite_link(self.community))
                elif key and key.startswith('source:') and not data._busy:
                    self.hover=None
                    self.search(0,key[7:])
                elif key and key.startswith('image:'):self.preview=int(key[6:])
                elif key and key.startswith('download:') and not data._busy:action('download')('EXEC_DEFAULT',entry=data._items[int(key[9:])]['id'])
                elif key=='upload':
                    self.close()
                    with context.temp_override(window=self.window,area=self.area,region=self.region):action('upload')('INVOKE_DEFAULT')
                    return {'FINISHED'}
                elif key is None and not inside((self.left,self.top-self.height,self.width,self.height),x,y):self.close();return {'CANCELLED'}
        self.reflow();self.update_hover();self.area.tag_redraw();return {'RUNNING_MODAL'}

class OpenCatalogue(bpy.types.Operator):
    bl_idname=PREFIX+'.prefab_catalogue_open'
    bl_label='Online Community Prefabs'
    bl_description='Open the searchable community catalogue; thumbnails load only when opened'
    bl_options={'INTERNAL'}
    def invoke(self,context,event):
        window,area=context.window,context.area
        region=next((r for r in area.regions if r.type=='WINDOW'),None)
        x,y=event.mouse_x,event.mouse_y
        def run():
            if window not in bpy.context.window_manager.windows[:] or area not in window.screen.areas[:]:return
            with bpy.context.temp_override(window=window,area=area,region=region):action('window')('INVOKE_DEFAULT',anchor_x=x,anchor_y=y)
        bpy.app.timers.register(run,first_interval=.02)
        return {'FINISHED'}

@bpy.app.handlers.persistent
def cancel_all(*_):
    for session in list(_sessions):session.close()

CatalogueSurface.__name__=PREFIX.upper()+'_OT_prefab_catalogue_window'
OpenCatalogue.__name__=PREFIX.upper()+'_OT_prefab_catalogue_open'

def register():
    for cls in (CatalogueSurface,OpenCatalogue):bpy.utils.register_class(cls)
    bpy.app.handlers.load_pre.append(cancel_all)

def unregister():
    cancel_all()
    if cancel_all in bpy.app.handlers.load_pre:bpy.app.handlers.load_pre.remove(cancel_all)
    for cls in (OpenCatalogue,CatalogueSurface):bpy.utils.unregister_class(cls)
    art.clear()

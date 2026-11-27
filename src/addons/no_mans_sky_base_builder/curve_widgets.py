"""Curve-only viewport widgets; deliberately independent of cable targets."""
from contextlib import contextmanager
import math
import bpy
import blf
import gpu
from . import i18n
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

INK = (.055, .035, .09, .98)
EDGE = (.27, .17, .39, 1)
PURPLE = (.62, .34, .96, 1)
CYAN = (.34, .82, .87, 1)
TEXT = (.94, .91, 1, 1)
MUTED = (.61, .56, .7, 1)
_round_shader = None
_round_batch = None

def mix(a,b,t):return tuple(a[i]*(1-t)+b[i]*t for i in range(4))

def update_theme(context):
    global INK,EDGE,PURPLE,CYAN,TEXT,MUTED,HEADER,BUTTON,HOVER,TRACK,SELECTED
    ui=context.preferences.themes[0].user_interface
    rgba=lambda c:(*c[:3],1)
    INK=rgba(ui.wcol_box.inner);TEXT=rgba(ui.wcol_regular.text)
    PURPLE=rgba(ui.wcol_tool.inner_sel)
    # Selected controls can be dark; the active slider item supplies a clear accent.
    if sum(abs(PURPLE[i]-INK[i]) for i in range(3))<.25:PURPLE=rgba(ui.wcol_numslider.item)
    EDGE=mix(INK,TEXT,.25);MUTED=mix(INK,TEXT,.67)
    CYAN=mix(PURPLE,TEXT,.45);HEADER=mix(INK,PURPLE,.25)
    BUTTON=rgba(ui.wcol_regular.inner);HOVER=mix(BUTTON,PURPLE,.4)
    TRACK=mix(INK,TEXT,.2);SELECTED=rgba(ui.wcol_regular.text_sel)



def rounded_shader():
    global _round_shader, _round_batch
    if _round_shader is None:
        interface = gpu.types.GPUStageInterfaceInfo('bbe_curve_round_iface')
        interface.smooth('VEC2', 'pixel')
        info = gpu.types.GPUShaderCreateInfo()
        info.vertex_in(0, 'VEC2', 'pos')
        info.vertex_out(interface)
        info.push_constant('MAT4', 'ModelViewProjectionMatrix')
        info.push_constant('VEC4', 'rect')
        info.push_constant('VEC4', 'fill')
        info.push_constant('FLOAT', 'radius')
        info.push_constant('BOOL', 'ui_region')
        info.fragment_out(0, 'VEC4', 'fragColor')
        info.vertex_source('''void main() {
            pixel = rect.xy - vec2(1.0) + pos * (2.0 * rect.zw + vec2(4.0));
            gl_Position = ModelViewProjectionMatrix * vec4(pixel, 0.0, 1.0);
        }''')
        info.fragment_source('''void main() {
            vec2 q=abs(pixel-rect.xy-rect.zw*0.5)-rect.zw*0.5+vec2(radius);
            float d=length(max(q,vec2(0.0)))+min(max(q.x,q.y),0.0)-radius;
            if (d>1.0) discard;
            vec3 rgb=mix(fill.rgb/12.92,pow((fill.rgb+0.055)/1.055,vec3(2.4)),step(vec3(0.04045),fill.rgb));
            fragColor=vec4(ui_region ? fill.rgb : rgb,fill.a*(1.0-smoothstep(-0.7,0.7,d)));
        }''')
        _round_shader = gpu.shader.create_from_info(info)
        _round_batch = batch_for_shader(_round_shader, 'TRIS', {'pos': ((0, 0), (1, 0), (0, 1))})
    return _round_shader


@contextmanager
def canvas(context):
    previous = gpu.state.blend_get()
    depth = gpu.state.depth_test_get()
    mask = gpu.state.depth_mask_get()
    with gpu.matrix.push_pop(), gpu.matrix.push_pop_projection():
        gpu.matrix.load_matrix(Matrix.Identity(4))
        gpu.matrix.load_projection_matrix(Matrix(((2/context.region.width, 0, 0, -1),
            (0, 2/context.region.height, 0, -1), (0, 0, -1, 0), (0, 0, 0, 1))))
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')
        gpu.state.depth_mask_set(False)
        try:
            yield
        finally:
            gpu.state.blend_set(previous)
            gpu.state.depth_test_set(depth)
            gpu.state.depth_mask_set(mask)


def polygon(shader, points, color):
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float('color', color)
    center = tuple(sum(p[i] for p in points)/len(points) for i in range(2))
    vertices = []
    for i, point in enumerate(points):
        vertices.extend((center, point, points[(i+1)%len(points)]))
    batch_for_shader(shader, 'TRIS', {'pos': vertices}).draw(shader)


def rounded(shader, x, y, w, h, radius, color):
    if w <= 0 or h <= 0:
        return
    # A single distance-field surface avoids seams between rounded fan triangles.
    shader=rounded_shader()
    # Font drawing can change blend state between adjacent controls.
    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float('ModelViewProjectionMatrix',gpu.matrix.get_projection_matrix() @ gpu.matrix.get_model_view_matrix())
    shader.uniform_float('rect',(x,y,w,h))
    shader.uniform_float('fill',color)
    shader.uniform_bool('ui_region',(bpy.context.region is not None and bpy.context.region.type=='UI',))
    shader.uniform_float('radius',min(radius,w/2,h/2))
    # One oversized triangle has no interior edge for driver antialiasing to expose.
    _round_batch.draw(shader)


def disc(shader, x, y, r, color):
    rounded(shader,x-r,y-r,2*r,2*r,r,color)


def line(shader, a, b, width, color):
    a, b = Vector(a), Vector(b)
    d = b-a
    if d.length < .01:
        return
    n = Vector((-d.y, d.x)).normalized()*width/2
    polygon(shader, [a+n, b+n, b-n, a-n], color)


def text(value, x, y, size, color=None, align='LEFT'):
    if color is None:color=TEXT
    blf.size(0, size)
    blf.color(0, *color)
    left = x
    if align in {'RIGHT', 'CENTER'}:
        width, _ = blf.dimensions(0, value)
        left -= width if align == 'RIGHT' else width / 2
    blf.position(0, left, y, 0)
    blf.draw(0, value)


class BBE_GT_curve_widget(bpy.types.Gizmo):
    bl_idname = 'BBE_GT_curve_widget'
    __slots__ = ('width', 'height', 'label', 'subtitle', 'style', 'fraction', 'upper_fraction',
                 'value', 'children', 'lines', 'scale', 'enabled', '_shader')

    def setup(self):
        self.width, self.height, self.scale = 100, 28, 1
        self.label = self.subtitle = self.value = ''
        self.style = 'BUTTON'
        self.fraction = 0
        self.enabled = False
        self.children = ()
        self.lines = ()
        self._shader = gpu.shader.from_builtin('UNIFORM_COLOR')

    def draw(self, context):
        # Only the card paints, so hover widgets cannot cover labels/tracks.
        if self.style not in {'CARD','STUDIO_CARD'}:
            return
        update_theme(context)
        with canvas(context):
            x, y = self.matrix_basis.translation[:2]
            s = self.scale
            rounded(self._shader, x-4*s, y-7*s, self.width+8*s, self.height+8*s, 17*s, (0, 0, 0, .2))
            rounded(self._shader, x, y, self.width, self.height, 14*s, EDGE)
            rounded(self._shader, x+s, y+s, self.width-2*s, self.height-2*s, 13*s, INK)
            for child in self.children:
                if not child.hide:
                    child.paint(self._shader,studio=self.style=='STUDIO_CARD')
            for dx, dy, label, color in self.lines:
                text(i18n.interface(label), x+dx, y+dy, 10*s, color)

    def paint(self, shader, *, studio=False):
        x, y = self.matrix_basis.translation[:2]
        w, h, s = self.width, self.height, self.scale
        hot = self.is_highlight or self.is_modal
        if self.style in {'HEADER','SHAPE_HEADER','AXIS_HEADER','EDGE_HEADER'}:
            if studio:
                line(shader,(x,y),(x+w,y),s,EDGE)
            else:rounded(shader, x, y, w, h, 10*s, HEADER)
            if self.style=='AXIS_HEADER':
                origin=(x+23*s,y+19*s)
                for dx,dy in ((13,0),(-8,-7),(0,13)):
                    tip=(origin[0]+dx*s,origin[1]+dy*s)
                    line(shader,origin,tip,2*s,CYAN)
                    disc(shader,*tip,2*s,CYAN)
            elif self.style=='EDGE_HEADER':
                points=[(x+dx*s,y+dy*s) for dx,dy in ((13,14),(22,25),(34,25))]
                for a,b in zip(points,points[1:]):line(shader,a,b,2*s,CYAN)
                for pt in points:disc(shader,*pt,2.5*s,CYAN)
            elif self.style=='SHAPE_HEADER':
                from . import menu_surface, shapes
                menu_surface.draw_image(shapes.preview_icon('STUDIO'),x+10*s,y+5*s,30*s,30*s)
            else:
                # A small Bezier flourish establishes a curve-specific visual language.
                path = [(x+14*s+i*22*s/20, y+18*s+math.sin(i/20*math.pi*2)*6*s) for i in range(21)]
                for a, b in zip(path, path[1:]):line(shader, a, b, 1.5*s, CYAN)
                disc(shader, *path[0], 2*s, PURPLE)
                disc(shader, *path[-1], 2*s, PURPLE)
            text(i18n.interface(self.label), x+47*s, y+26*s, 13*s)
            text(self.subtitle, x+47*s, y+10*s, 10*s, MUTED)
            for dx in (0, 4):
                for dy in (0, 4, 8):disc(shader, x+w-(13+dx)*s, y+20*s+dy*s, .8*s, MUTED)
        elif self.style=='ASSET_PREVIEW':
            from . import icons,menu_surface
            rounded(shader,x,y,w,h,7*s,HOVER if hot else HEADER)
            preview=icons.get_asset_icons_pcoll().get(self.label)
            size=min(w,h)-4*s
            if preview:menu_surface.draw_image(preview.icon_id,x+(w-size)/2,y+(h-size)/2,size,size,preview=preview)
        elif self.style in {'STUDIO_LINK','STUDIO_ACTIVE','STUDIO_PART'}:
            from . import menu_surface
            part=self.style=='STUDIO_PART'
            icon='pipette' if part else {'Dimensions':'scan','Deform':'spline','Pieces':'layers',
                 'New shape…':'package-plus','Done':'check','‹  Home':'chevron-left',
                 'Advanced…':'settings-2','Move shape':'navigation','Rotate':'rotate-ccw',
                 'Scale':'scan','Move pieces':'navigation','Rotate pieces':'rotate-ccw'}.get(self.label)
            if hot or self.style=='STUDIO_ACTIVE' or part:
                rounded(shader,x,y,w,h,6*s,HOVER if hot else HEADER)
            if icon:
                menu_surface.draw_image(menu_surface.outline_icon(icon),x+6*s,y+(h-16*s)/2,16*s,16*s)
            label=self.label if part else i18n.interface('Home' if self.label=='‹  Home' else self.label)
            offset=26*s
            text(menu_surface.trim(label,w-offset-4*s,11*s),x+offset,y+(h-10*s)/2,11*s,TEXT)
        elif self.style == 'FACE_PREVIEW':
            from . import menu_surface, shapes
            rounded(shader,x,y,w,h,7*s,HOVER if hot else BUTTON)
            icon=31*s
            menu_surface.draw_image(shapes.preview_icon(self.subtitle),x+(w-icon)/2,y+h-icon-3*s,icon,icon)
            text(i18n.interface(self.label),x+w/2,y+7*s,11*s,TEXT,'CENTER')
        elif self.style in {'PART_FACE','FACE_STEP'}:
            rounded(shader,x,y,w,h,8*s,CYAN if hot else EDGE)
            rounded(shader,x+s,y+s,w-2*s,h-2*s,7*s,HOVER if hot else BUTTON)
            cy=y+h/2
            if self.style=='FACE_STEP':
                cx=x+w/2
                dx=(-4 if self.value=='LEFT' else 4)*s
                tip=(cx+dx,cy)
                line(shader,(cx-dx,cy+8*s),tip,3*s,TEXT)
                line(shader,tip,(cx-dx,cy-8*s),3*s,TEXT)
            else:
                # A solid face and its outward normal distinguish part orientation from the shell mask.
                cx=x+23*s
                def pt(dx,dy):return cx+dx*s,cy+dy*s
                top,left,right,mid=pt(0,14),pt(-12,8),pt(12,8),pt(0,2)
                bottom,lower_left,lower_right=pt(0,-13),pt(-12,-7),pt(12,-7)
                polygon(shader,[mid,right,lower_right,bottom],CYAN)
                for a,b in ((top,left),(top,right),(left,mid),(right,mid),(left,lower_left),
                            (lower_left,bottom),(mid,bottom),(right,lower_right),(lower_right,bottom)):
                    line(shader,a,b,1.5*s,TEXT)
                line(shader,pt(7,-2),pt(18,3),2.3*s,TEXT)
                polygon(shader,[pt(19,4),pt(12,5),pt(15,-2)],TEXT)
                text(i18n.interface(self.label),x+49*s,cy+2*s,13*s,TEXT)
                text(self.value,x+49*s,cy-12*s,10*s,MUTED)
        elif self.style == 'RANGE':
            text(i18n.interface(self.label),x+2*s,y+26*s,11*s,TEXT)
            text(self.value,x+w-2*s,y+26*s,11*s,MUTED,'RIGHT')
            left,cy=x+6*s,y+10*s
            width=w-12*s
            lo,hi=left+width*self.fraction,left+width*self.upper_fraction
            rounded(shader,left,cy-2*s,width,4*s,2*s,TRACK)
            rounded(shader,lo,cy-2*s,max(1,hi-lo),4*s,2*s,CYAN)
            for at in (lo,hi):
                rounded(shader,at-4*s,cy-7*s,8*s,14*s,3*s,TEXT)
        elif self.style == 'SLIDER':
            if hot:rounded(shader, x-4*s, y, w+8*s, h, 7*s, HOVER)
            text(i18n.interface(self.label), x+2*s, y+26*s, 11*s, TEXT if hot else MUTED)
            rounded(shader, x+w-66*s, y+21*s, 66*s, 19*s, 6*s, HEADER)
            text(self.value, x+w-8*s, y+26*s, 11*s, TEXT, 'RIGHT')
            left, right, cy = x+6*s, x+w-6*s, y+10*s
            rounded(shader, left, cy-2*s, right-left, 4*s, 2*s, TRACK)
            end = left+(right-left)*max(0, min(1, self.fraction))
            rounded(shader, left, cy-2*s, end-left, 4*s, 2*s, PURPLE)
            if hot:disc(shader, end, cy, 9*s, (*PURPLE[:3],.17))
            disc(shader, end, cy, 5*s, CYAN if hot else CYAN)
            disc(shader, end, cy, 2*s, INK)
        elif self.style == 'SWITCH':
            if hot:rounded(shader, x, y, w, h, 7*s, HOVER)
            text(i18n.interface(self.label), x+9*s, y+(h-10*s)/2, 11*s)
            text(i18n.interface(self.value or ('On' if self.enabled else 'Off')), x+w-59*s, y+(h-10*s)/2, 10*s, TEXT, 'RIGHT')
            left, cy = x+w-49*s, y+h/2
            rounded(shader, left, cy-9*s, 40*s, 18*s, 9*s, PURPLE if self.enabled else TRACK)
            disc(shader, left+(31 if self.enabled else 9)*s, cy, 7*s, CYAN if self.enabled else MUTED)
        elif self.style == 'NAV':
            rounded(shader,x,y,w,h,9*s,CYAN)
            rounded(shader,x+s,y+s,w-2*s,h-2*s,8*s,mix(HEADER,PURPLE,.55 if hot else .3))
            rounded(shader,x+7*s,y+7*s,4*s,h-14*s,2*s,CYAN)
            text(i18n.interface(self.label),x+23*s,y+(h-12*s)/2,12*s,TEXT)
            cx,cy=x+w-21*s,y+h/2
            line(shader,(cx-5*s,cy-5*s),(cx,cy),2*s,CYAN)
            line(shader,(cx,cy),(cx-5*s,cy+5*s),2*s,CYAN)
        elif studio:
            if hot or self.style=='PRIMARY':
                rounded(shader,x,y,w,h,6*s,HOVER if hot else HEADER)
            text(i18n.interface(self.label),x+w/2,y+(h-10*s)/2,11*s,TEXT,'CENTER')
        else:
            primary = self.style == 'PRIMARY' or self.enabled
            border = PURPLE if primary else EDGE
            fill = mix(BUTTON,PURPLE,.6) if primary else BUTTON
            if hot:fill = HOVER
            rounded(shader, x, y, w, h, 7*s, border)
            rounded(shader, x+s, y+s, w-2*s, h-2*s, 6*s, fill)
            text(i18n.interface(self.label), x+w/2, y+(h-10*s)/2, 11*s, TEXT, 'CENTER')

    def draw_select(self, context, select_id):pass

    def test_select(self, context, location):
        x, y = self.matrix_basis.translation[:2]
        return 0 if x <= location[0] <= x+self.width and y <= location[1] <= y+self.height else -1


class BBE_GT_curve_point(bpy.types.Gizmo):
    bl_idname = 'BBE_GT_curve_point'
    __slots__ = ('chosen', 'handle', 'stem', 'scale', '_shader')

    def setup(self):
        self.chosen = self.handle = False
        self.stem = None
        self.scale = 1
        self._shader = gpu.shader.from_builtin('UNIFORM_COLOR')

    def draw(self, context):
        x, y = self.matrix_basis.translation[:2]
        s = self.scale
        hot = self.is_highlight or self.is_modal
        update_theme(context)
        with canvas(context):
            if self.handle:
                if self.stem is not None:line(self._shader, self.stem, (x, y), s, (*CYAN[:3],.65))
                disc(self._shader, x, y, 5*s, INK)
                disc(self._shader, x, y, (4 if hot else 3)*s, TEXT if hot else CYAN)
            else:
                r = (6 if self.chosen or hot else 4.5)*s
                diamond = lambda size:[(x, y+size), (x+size, y), (x, y-size), (x-size, y)]
                polygon(self._shader, diamond(r+1.5*s), INK)
                polygon(self._shader, diamond(r), TEXT if self.chosen or hot else PURPLE)
                polygon(self._shader, diamond(max(1, r-2*s)), HEADER)

    def draw_select(self, context, select_id):pass

    def test_select(self, context, location):
        # Generous hit area without a large on-screen target.
        return 0 if (Vector(location)-Vector(self.matrix_basis.translation[:2])).length <= 9*self.scale else -1


CLASSES = (BBE_GT_curve_widget, BBE_GT_curve_point)

def register():
    for cls in CLASSES:bpy.utils.register_class(cls)

def unregister():
    global _round_shader, _round_batch
    for cls in reversed(CLASSES):bpy.utils.unregister_class(cls)
    _round_batch=None
    _round_shader=None

"""FuriousFurby shared graphical surfaces for the independent menus."""
from pathlib import Path
from array import array
from collections import OrderedDict
import bpy, blf, gpu
import bpy.utils.previews
from gpu_extras.batch import batch_for_shader
from . import curve_widgets as paint
INK=(.0902,.0784,.1176,1);SURFACE=(.1451,.1255,.1843,1)
EDGE=(.3373,.2627,.4078,1);HOVER=(.20,.1686,.2588,1)
TEXT=(.9451,.9294,.9686,1);MUTED=(.7137,.6627,.7843,1)
ACCENT=(.7216,.6039,.9608,1);PRIMARY=(.502,.3451,.7686,1)
_gradient=None
_previews=None
_textures=OrderedDict()

def preview(path):
    global _previews
    if _previews is None:_previews=bpy.utils.previews.new()
    path=Path(path);key=str(path)
    if not path.is_file():return None
    if key not in _previews:_previews.load(key,key,'IMAGE')
    return _previews[key]

def icon(name):return preview(Path(__file__).parent/'images/menu_outline'/(name+'.png'))

def image(value,x,y,w,h,cover=False):
    if value is None or not value.image_size[0]:return False
    iw,ih=value.image_size;key=(bpy.context.window.as_pointer(),value.icon_id,iw,ih)
    if key not in _textures:
        pixels = array('f', [0.0]) * (iw*ih*4)
        value.image_pixels_float.foreach_get(pixels)
        _textures[key]=gpu.types.GPUTexture((iw,ih),format='RGBA8',data=gpu.types.Buffer('FLOAT',len(pixels),pixels))
    _textures.move_to_end(key)
    if len(_textures)>48:_textures.popitem(last=False)
    u=v=0.;uw=vh=1.
    if cover:
        if iw/ih>w/h:uw=(w/h)/(iw/ih);u=(1-uw)/2
        else:vh=(iw/ih)/(w/h);v=(1-vh)/2
    else:
        scale=min(w/iw,h/ih);nw,nh=iw*scale,ih*scale;x+=(w-nw)/2;y+=(h-nh)/2;w,h=nw,nh
    shader=gpu.shader.from_builtin('IMAGE');gpu.state.blend_set('ALPHA');shader.bind();shader.uniform_sampler('image',_textures[key])
    batch_for_shader(shader,'TRI_FAN',{'pos':((x,y),(x+w,y),(x+w,y+h),(x,y+h)),
      'texCoord':((u,v),(u+uw,v),(u+uw,v+vh),(u,v+vh))}).draw(shader)
    return True

def trim(text,width,size):
    blf.size(0,size)
    if blf.dimensions(0,text)[0]<=width:return text
    while text and blf.dimensions(0,text+'…')[0]>width:text=text[:-1]
    return text+'…' if text else ''

def theme(context):
    global INK,SURFACE,EDGE,HOVER,TEXT,MUTED,ACCENT,PRIMARY
    from . import menu_surface as m
    m.use_theme(context)
    INK,SURFACE,EDGE,HOVER,TEXT,MUTED,ACCENT,PRIMARY=(m.INK,m.SURFACE,m.EDGE,m.HOVER,m.TEXT,m.MUTED,m.ACCENT,m.PRIMARY)


def panel(shader,x,y,w,h,s=1):
    for pad,alpha in ((7,.08),(4,.12),(2,.16)):
        paint.rounded(shader,x-pad*s,y-(pad+3)*s,w+2*pad*s,h+(pad+3)*s,16*s,(0,0,0,alpha))
    paint.rounded(shader,x,y,w,h,13*s,EDGE)
    gradient_box(x+s,y+s,w-2*s,h-2*s,13*s,paint.mix(INK,TEXT,.035),INK)

def clear():
    global _previews,_gradient
    _textures.clear();_gradient=None
    if _previews is not None:bpy.utils.previews.remove(_previews);_previews=None


def gradient_box(x,y,w,h,radius,a,b):
    """Static two-tone surface; one cached shader, no animation or images."""
    global _gradient
    if _gradient is None:
        interface=gpu.types.GPUStageInterfaceInfo('bbe_menu_gradient_iface');interface.smooth('VEC2','pixel')
        info=gpu.types.GPUShaderCreateInfo();info.vertex_in(0,'VEC2','pos');info.vertex_out(interface)
        for kind,name in [('MAT4','ModelViewProjectionMatrix'),('VEC4','rect'),('VEC4','first'),('VEC4','last'),('FLOAT','radius')]:info.push_constant(kind,name)
        info.fragment_out(0,'VEC4','fragColor')
        info.vertex_source('void main(){pixel=pos;gl_Position=ModelViewProjectionMatrix*vec4(pos,0,1);}')
        info.fragment_source('''void main(){
            vec2 q=abs(pixel-rect.xy-rect.zw*.5)-rect.zw*.5+vec2(radius);
            float d=length(max(q,vec2(0)))+min(max(q.x,q.y),0.0)-radius;
            if(d>1.0)discard;
            vec2 uv=(pixel-rect.xy)/rect.zw;
            vec4 c=mix(first,last,clamp((uv.x+1.0-uv.y)*.7,0.0,1.0));
            vec3 rgb=mix(c.rgb/12.92,pow((c.rgb+.055)/1.055,vec3(2.4)),step(vec3(.04045),c.rgb));
            fragColor=vec4(rgb,c.a*(1.0-smoothstep(-.7,.7,d)));
        }''')
        _gradient=gpu.shader.create_from_info(info)
    gpu.state.blend_set('ALPHA');_gradient.bind()
    _gradient.uniform_float('ModelViewProjectionMatrix',gpu.matrix.get_projection_matrix() @ gpu.matrix.get_model_view_matrix())
    for key,value in [('rect',(x,y,w,h)),('first',a),('last',b),('radius',radius)]:_gradient.uniform_float(key,value)
    batch_for_shader(_gradient,'TRIS',{'pos':((x-1,y-1),(x+2*w+3,y-1),(x-1,y+2*h+3))}).draw(_gradient)

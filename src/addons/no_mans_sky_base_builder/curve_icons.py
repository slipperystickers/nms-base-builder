"""Colored shape silhouettes, generated once; no asset-pack dependency."""
import math
import bpy
import bpy.utils.previews
from .curve_shapes import SHAPES
_collection=None
_color=None

def shape_path(kind):
    points=[]
    for i in range(97):
        t=i/96
        a=t*math.tau
        if kind=='CIRCLE':x,y=math.cos(a),math.sin(a)
        elif kind=='ELLIPSE':x,y=math.cos(a),.55*math.sin(a)
        elif kind=='HALF':x,y=math.cos(t*math.pi),math.sin(t*math.pi)-.5
        elif kind=='ARC':x,y=math.cos(t*2.2),math.sin(t*2.2)
        elif kind=='SPIRAL':x,y=(.08+.92*t)*math.cos(a*2.3),(.08+.92*t)*math.sin(a*2.3)
        elif kind=='HELIX':x,y=.7*math.cos(a*2.5),1.6*t-.8+.22*math.sin(a*2.5)
        elif kind=='WAVE':x,y=t*2-1,.6*math.sin(a*1.5)
        else:x,y=t*2-1,t*1.2-.6
        points.append((x,y))
    return points

def icon_id(kind,context):
    global _collection,_color
    color=(.25,.8,1.)
    if _collection is None:_collection=bpy.utils.previews.new()
    if color!=_color:
        _color=color
        for key,_,_ in SHAPES:
            if key=='FREE':continue
            path=shape_path(key);low=[min(p[j] for p in path) for j in (0,1)];high=[max(p[j] for p in path) for j in (0,1)]
            scale=44/max(high[j]-low[j] for j in (0,1))
            path=[(32+(x-(low[0]+high[0])/2)*scale,32+(y-(low[1]+high[1])/2)*scale) for x,y in path]
            alpha=[0.0]*4096
            for x,y in path:
                for iy in range(max(0,int(y)-3),min(64,int(y)+4)):
                    for ix in range(max(0,int(x)-3),min(64,int(x)+4)):
                        a=max(0,min(1,2.2-math.hypot(ix+.5-x,iy+.5-y)))
                        n=iy*64+ix;alpha[n]=max(alpha[n],a)
            tint={'CIRCLE':(.35,.8,1.),'ELLIPSE':(.4,.9,.65),'HALF':(1.,.72,.25),
                  'ARC':(1.,.55,.3),'SPIRAL':(.7,.5,1.),'HELIX':(.95,.45,.7),
                  'WAVE':(.25,.85,.85)}.get(key,color)
            pixels=[v for a in alpha for v in (*(c*a for c in tint),a)]
            preview=_collection.get(key) or _collection.new(key)
            preview.image_size=(64,64);preview.image_pixels_float=pixels
            preview.icon_size=(64,64);preview.icon_pixels_float=pixels
    return _collection[kind].icon_id

def unregister():
    global _collection,_color
    if _collection is not None:bpy.utils.previews.remove(_collection)
    _collection=None;_color=None

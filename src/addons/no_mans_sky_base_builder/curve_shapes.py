"""Parametric Bezier guides. No Blender state or exported game objects."""
import math

SHAPES = [('CIRCLE', 'Circle', 'Closed circular path'),
          ('HALF', 'Half Circle', 'A semicircular path'),
          ('ARC', 'Arc', 'Adjustable sweep angle'),
          ('ELLIPSE', 'Ellipse', 'Independent horizontal and vertical radii'),
          ('HELIX', 'Corkscrew', 'A helix with adjustable turns and height'),
          ('SPIRAL', 'Spiral', 'A flat spiral with start and end radii'),
          ('WAVE', 'Wave', 'An adjustable sine wave'),
          ('LINE', 'Line', 'A straight starting path'),
          ('FREE', 'Drawn Curve', 'A smooth path through your points')]


def shape_points(kind, radius=4, width=2, height=8, turns=2, sweep=120, count=17):
    closed = kind in {'CIRCLE', 'ELLIPSE'}
    count = max(4 if closed else 2, int(count))
    if kind in {'HELIX','SPIRAL','WAVE'}:
        count = max(count, math.ceil(abs(turns)*8)+1)
    angle = (math.tau if closed else math.pi if kind == 'HALF' else
             math.radians(sweep) if kind == 'ARC' else math.tau * turns)
    divisor = count if closed else count - 1
    result = []
    for i in range(count):
        t = i / divisor
        a = angle * t
        if kind == 'LINE':
            co, tangent = (width*t, 0, 0), (width, 0, 0)
        elif kind == 'WAVE':
            co = (width*t, radius*math.sin(a), 0)
            tangent = (width, radius*angle*math.cos(a), 0)
        else:
            r = radius + (width-radius)*t if kind == 'SPIRAL' else radius
            dr = width-radius if kind == 'SPIRAL' else 0
            ry = width if kind == 'ELLIPSE' else r
            co = (r*math.cos(a), ry*math.sin(a), height*t if kind == 'HELIX' else 0)
            tangent = (dr*math.cos(a)-r*angle*math.sin(a),
                       (dr*math.sin(a) if kind != 'ELLIPSE' else 0)+ry*angle*math.cos(a),
                       height if kind == 'HELIX' else 0)
        factor = 1 / divisor / 3
        if kind in {'CIRCLE', 'ELLIPSE', 'HALF', 'ARC'} and abs(angle) > 1e-9:
            factor = 4/3 * math.tan(angle/divisor/4) / angle
        handle = tuple(v*factor for v in tangent)
        result.append((co, tuple(c-h for c,h in zip(co,handle)), tuple(c+h for c,h in zip(co,handle))))
    return result, closed


def resample_offsets(offsets, count, closed=False):
    if not offsets:
        return [(0,0,0)]*count
    if len(offsets) == count:
        return offsets
    result=[]
    for i in range(count):
        x=i*(len(offsets) if closed else len(offsets)-1)/(count if closed else max(1,count-1))
        a=min(int(x),len(offsets)-1);b=(a+1)%len(offsets) if closed else min(a+1,len(offsets)-1)
        f=x-a
        result.append(tuple((1-f)*u+f*v for u,v in zip(offsets[a],offsets[b])))
    return result

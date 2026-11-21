"""Layouts of rigid native parts. Coordinates are local to the shape controller."""
from math import ceil, cos, pi, sin, sqrt, tau
from mathutils import Vector

OUTLINES = (
    ('RECTANGLE', 'Rectangle'), ('TRIANGLE', 'Triangle'), ('CIRCLE', 'Circle'),
    ('PENTAGON', 'Pentagon'), ('HEXAGON', 'Hexagon'), ('OCTAGON', 'Octagon'),
    ('ELLIPSE', 'Ellipse'), ('POLYGON', 'Custom polygon'),
)
SHELLS = (
    ('SPHERE', 'Sphere'), ('CYLINDER', 'Cylinder'), ('PYRAMID', 'Pyramid'),
    ('CONE', 'Cone'), ('BOX', 'Box'), ('OBLATE', 'Oblate spheroid'),
    ('PRISM', 'Custom prism'), ('TORUS', 'Torus'), ('DOME', 'Dome'),
    ('CAPSULE', 'Capsule'), ('ELLIPSOID', 'Ellipsoid'), ('PROLATE', 'Prolate spheroid'),
    ('WEDGE', 'Triangular prism'), ('SUPERELLIPSOID', 'Rounded box'), ('SPINDLE', 'Spindle'),
)
LABELS = dict(OUTLINES + SHELLS)
POLAR = {'SPHERE','OBLATE','PROLATE','ELLIPSOID','DOME','SPINDLE','CAPSULE'}
FACETED = {'BOX', 'PYRAMID', 'WEDGE', 'PRISM', 'CYLINDER', 'CONE'}
MAX_PARTS = 4096
Z = Vector((0, 0, 1))


def ring(kind, count, width, depth):
    if kind in {'RECTANGLE', 'BOX', 'PYRAMID'}:
        return [Vector((x*width/2, y*depth/2, 0)) for x, y in
                ((-1,-1), (1,-1), (1,1), (-1,1))]
    points = [(cos(pi/2 + tau*i/count), sin(pi/2 + tau*i/count)) for i in range(count)]
    xmin, xmax = min(x for x,y in points), max(x for x,y in points)
    ymin, ymax = min(y for x,y in points), max(y for x,y in points)
    return [Vector(((x-xmin)/(xmax-xmin)*width-width/2,
                    (y-ymin)/(ymax-ymin)*depth-depth/2, 0)) for x,y in points]


def placements(s, footprint, groups=None, *, refined=True):
    """Return (outer face centre, tangent, normal, uniform scale) for each part."""
    w, d, h = s.width, s.depth, s.height
    kind = s.outline if s.dimension == 'D2' else s.shell
    detail = s.detail
    fw, fh = footprint[:2]
    thickness = footprint[2] if len(footprint) > 2 else 0.
    protected = s.fit and (s.dimension == 'D2' and getattr(s, 'filled_2d', False) or
                           s.dimension == 'D3' and kind in FACETED and getattr(s, 'preserve_edges', False))
    shell_planes = []
    pitch = max(w, d, h if s.dimension == 'D3' else 0) / (2*detail)
    result = []
    group = "Outline"

    def add(position, along, normal, scale):
        if s.dimension=='D2' and len(result)>=getattr(s,'part_limit',MAX_PARTS):
            raise ValueError('This layout exceeds the 2D part limit. Raise the limit or enable fitted scaling.')
        if len(result) >= MAX_PARTS:
            raise ValueError(f'This shape exceeds {MAX_PARTS:,} parts. Increase Piece scale with Fill gaps on, or adjust the proportions.')
        if groups is not None:groups.append(group)
        result.append((position, along.normalized(), normal.normalized(), scale if s.fit else 1.0))

    def face(corners, row_limit=None):
        # Tile a convex face in non-overlapping courses. Uniform tiles in
        # each course have exactly the width of its span. For narrow residual
        # courses, choose the nearest whole count to avoid tiny filler pieces.
        origin = corners[0]
        u = (corners[1]-origin).normalized()
        normal = u.cross(corners[-1]-origin).normalized()
        v = normal.cross(u)
        poly = [((p-origin).dot(u), (p-origin).dot(v)) for p in corners]
        low, high = min(y for x,y in poly), max(y for x,y in poly)
        span = max(x for x,y in poly)-min(x for x,y in poly)
        cols = max(1, round(span/pitch))
        rows = max(1, round((high-low)/(span/cols*fh/fw)))
        constrained=row_limit is not None and ceil((high-low)/(span/cols*fh/fw)-1e-6)>row_limit
        if row_limit is not None:
            rows=min(rows,row_limit)
        step = (high-low)/rows
        rectangular = len(poly)==4 and all(abs(y-low)<1e-5 or abs(y-high)<1e-5 for x,y in poly)
        if protected:
            from .shape_fit import bounded_tiles
            for x,y,scale,relief,ux,uy in bounded_tiles(poly, pitch, fw, fh, thickness,
                    shell_planes, origin, u, v, normal, row_limit, rounded_wall=kind=='CONE' and group=='Wall'):
                add(origin+u*x+v*y+normal*relief, u*ux+v*uy, normal, scale)
            return
        if s.fit and refined and not constrained:
            from .shape_fit import fitted_tiles
            # A sloping quadrilateral is not a rectangle in this basis.
            xmin,xmax=min(x for x,y in poly),max(x for x,y in poly)
            rect=rectangular and all(min(abs(x-xmin),abs(x-xmax))<1e-5 for x,y in poly)
            for x,y,scale,relief,*axis in fitted_tiles(poly,pitch,fw,fh,rect):
                tangent=u*axis[0]+v*axis[1] if axis else u
                add(origin+u*x+v*y+normal*relief,tangent,normal,scale)
            return
        for j in range(rows):
            y = low+(j+.5)*step
            # Cover the whole course, including the wider edge of a triangle
            # or cap. Sampling just the middle leaves openings beside seams.
            y0_band,y1_band=y-step/2,y+step/2
            hits=[x for x,py in poly if y0_band-1e-7<=py<=y1_band+1e-7]
            for (x0,y0),(x1,y1) in zip(poly, poly[1:]+poly[:1]):
                if abs(y1-y0)<1e-8:continue
                for bound in (y0_band,y1_band):
                    if min(y0,y1)<=bound<=max(y0,y1):
                        hits.append(x0+(x1-x0)*(bound-y0)/(y1-y0))
            if len(hits)<2:
                continue
            left, right = min(hits), max(hits)
            width = right-left
            n = cols if rectangular else max(1, round(width/(step*fw/fh)))
            # Cover the course in both dimensions. Distribute any necessary
            # overlap between rows; a sub-millimetre relief avoids coplanar faces.
            # A narrow join covers the bevel of the default cuboid floor tile.
            scale = max(width/n/fw,step/fh)*1.012
            relief = (j%2)*min(step, width/n)*.0005 if s.fit and scale*fh>step*1.0001 else 0
            for i in range(n):
                dx = (left+right)/2 if n==1 else left+scale*fw/2+i*(width-scale*fw)/(n-1)
                seam = (i%2)*min(step,width/n)*.00025 if s.fit and scale*fw>width/n*1.0001 else 0
                add(origin+u*dx+v*y+normal*(relief+seam), u, normal, scale)

    if s.dimension == 'D2':
        n = {'TRIANGLE':3,'PENTAGON':5,'HEXAGON':6,'OCTAGON':8,'POLYGON':s.sides}.get(kind, max(12,round(8*detail)))
        budget=getattr(s,'part_limit',MAX_PARTS)
        if kind in {'CIRCLE','ELLIPSE'}:
            if getattr(s,'rim_layout',False):
                n=min(256,max(n,round(20+1.0*s.edge_quality)))
            else:n=min(256,max(n,24*2**s.edge_detail)) if getattr(s,'planar',False) else min(n,max(3,budget))
        vertices = ring(kind,n,w,d)
        if getattr(s, 'filled_2d', False):
            group = 'Fill'
            if getattr(s,'planar',False):
                from .shape_planar import fill,outlined_fill
                cells=(outlined_fill(vertices,pitch,footprint,s.edge_quality,budget) if getattr(s,'rim_layout',False)
                       else fill(vertices,pitch,footprint,s.edge_detail,budget))
                for pos,tangent,scale in cells:
                    add(pos,tangent,Z,scale)
                return result
            face(vertices)
            return result
        if len(vertices)>budget:
            raise ValueError(f'This outline needs at least {len(vertices)} parts, one per edge.')
        counts=[1 if kind in {'CIRCLE','ELLIPSE'} else max(1,ceil((b-a).length/pitch-1e-6))
                for a,b in zip(vertices,vertices[1:]+vertices[:1])]
        total=sum(counts)
        if total>budget:
            weights=[(n-1)*(budget-len(counts))/(total-len(counts)) for n in counts]
            counts=[1+int(w) for w in weights]
            for index in sorted(range(len(counts)),key=lambda i:weights[i]%1,reverse=True)[:budget-sum(counts)]:
                counts[index]+=1
        for edge_index,(a,b) in enumerate(zip(vertices, vertices[1:]+vertices[:1])):
            chord = b-a
            count = counts[edge_index]
            normal = chord.cross(Z).normalized()
            scale=chord.length/count/fw
            # Keep the long outside edge on the polygon. The tiny step is
            # confined to joins where rigid flat rectangles overlap inside.
            relief=(edge_index%2 if edge_index<len(vertices)-1 else 2)*min(scale*fh,.8)*.001
            for i in range(count):
                center=a+chord*((i+.5)/count)
                if s.flat:
                    center-=normal*((scale if s.fit else 1)*fh/2)
                    add(center+Z*relief,chord,Z,scale)
                else:
                    add(center,chord,normal,scale)
        return result

    if kind in {'BOX','PYRAMID','PRISM','WEDGE','CYLINDER','CONE'}:
        n = s.sides if kind=='PRISM' else 3 if kind=='WEDGE' else max(12,round(detail*8))
        base = [p-Z*h/2 for p in ring(kind,n,w,d)]
        top = [p+Z*h for p in base]
        pointed = kind in {'PYRAMID','CONE'}
        if protected:
            shell_planes = [(base[0], -Z)]
            if not pointed:
                shell_planes.append((top[0], Z))
            for i, a in enumerate(base):
                b = base[(i+1) % len(base)]
                end = Z*h/2 if pointed else top[i]
                shell_planes.append((a, (b-a).cross(end-a).normalized()))
        group="Bottom"
        face(list(reversed(base)))
        if not pointed:
            group="Top"
            face(top)
        # Very high side counts make narrow facets. Share the remaining
        # budget across their full-height courses after both caps are tiled.
        row_limit=max(1,(MAX_PARTS-len(result))//len(base)) if kind=='PRISM' else None
        for i,a in enumerate(base):
            group="Wall" if kind in {"CONE","CYLINDER"} else f"Side {i+1}"
            b=base[(i+1)%len(base)]
            face([a,b,Z*h/2] if pointed else [a,b,top[(i+1)%len(top)],top[i]],row_limit)
        return result

    if kind in POLAR:
        # Equal-distance latitude courses keep the joint height stable on an
        # elongated or flattened shell. Close each pole with one horizontal
        # tile, so no fan of rectangular pieces intersects at a single point.
        def coords(t):
            lat=(t if kind=='DOME' else 2*t-1)*pi/2
            radius=cos(lat)
            z=sin(lat)
            if kind=='DOME':z=2*z-1
            if kind=='SPINDLE':radius=radius**1.8
            if kind=='CAPSULE':
                if t<.25:radius,z=sin(t*tau),-.5-.5*cos(t*tau)
                elif t>.75:radius,z=cos((t-.75)*tau),.5+.5*sin((t-.75)*tau)
                else:radius,z=1,2*t-1
            return radius,z
        def point(t,angle):
            radius,z=coords(t)
            return Vector((radius*cos(angle)*w/2,radius*sin(angle)*d/2,z*h/2))
        from bisect import bisect_right
        samples=128
        lengths=[0.]
        for i in range(samples):
            lengths.append(lengths[-1]+max((point((i+1)/samples,a)-point(i/samples,a)).length for a in (0,pi/2)))
        def at(distance):
            i=min(samples-1,max(0,bisect_right(lengths,distance)-1))
            return (i+(distance-lengths[i])/max(1e-8,lengths[i+1]-lengths[i]))/samples
        length=lengths[-1]
        pitch=max(min(w,d,h),max(w,d,h)*.4)/(detail*3)
        strength=s.pole_taper if s.fit else 0
        polar_span=min(pitch*(.38-.25*strength),length*.10)
        start=0 if kind=='DOME' else polar_span
        end=length-polar_span
        # Sample a density field along the physical arc. Shrinking both the
        # band height and target tile width keeps polar pieces proportional.
        arc=[start+(end-start)*i/samples for i in range(samples+1)]
        density=[0.]
        for a,b in zip(arc,arc[1:]):
            radius=coords(at((a+b)/2))[0]
            local_pitch=pitch*(1-strength*(1-sqrt(max(0,radius))))
            density.append(density[-1]+(b-a)/max(local_pitch,pitch*.2))
        bands=max(3,round(density[-1]))
        def boundary(index):
            value=density[-1]*index/bands
            i=min(samples-1,max(0,bisect_right(density,value)-1))
            return arc[i]+(arc[i+1]-arc[i])*(value-density[i])/(density[i+1]-density[i])
        for j in range(bands):
            low,high=boundary(j),boundary(j+1)
            t0,t1,tm=at(low),at(high),at((low+high)/2)
            # Approximate ellipse perimeter and choose a count that matches
            # panel width to the physical band height.
            radius=coords(tm)[0]
            group="Dome" if kind=="DOME" else "Upper" if tm>=.5 else "Lower"
            perimeter=pi/2*(3*(w+d)-sqrt((3*w+d)*(w+3*d)))*radius
            count=max(4,round(perimeter/((high-low)*fw/fh)))
            for i in range(count):
                a,b=tau*i/count,tau*(i+1)/count
                q=[point(t0,a),point(t0,b),point(t1,b),point(t1,a)]
                center=sum(q,Vector())/4
                u=(q[1]-q[0]+q[2]-q[3]).normalized()
                normal=u.cross(q[3]-q[0]+q[2]-q[1]).normalized()
                v=normal.cross(u)
                width=max(abs((p-center).dot(u)) for p in q)*2
                height=max(abs((p-center).dot(v)) for p in q)*2
                add(center,u,normal,max(width/fw,height/fh))
        for dist,side in ([(end,1)] if kind=='DOME' else [(start,-1),(end,1)]):
            group="Dome" if kind=="DOME" else "Upper" if side==1 else "Lower"
            radius,z=coords(at(dist))
            add(Vector((0,0,z*h/2)),Vector((1,0,0)),Z*side,max(w*radius/fw,d*radius/fh))
        if kind=='DOME':
            group='Bottom'
            face([p-Z*h/2 for p in reversed(ring('CIRCLE',max(16,round(detail*12)),w,d))])
        return result

    if kind == 'SUPERELLIPSOID':
        # Six continuous patches meet edge-to-edge. Evenly spaced spherical
        # cube samples avoid longitude convergence and oversized polar caps.
        dims=(w,d,h)
        def project(point):
            x,y,z=point
            unit=Vector((x*sqrt(max(0,1-(y*y+z*z)/2+y*y*z*z/3)),
                         y*sqrt(max(0,1-(z*z+x*x)/2+z*z*x*x/3)),
                         z*sqrt(max(0,1-(x*x+y*y)/2+x*x*y*y/3))))
            unit=Vector(tuple((-1 if k<0 else 1)*abs(k)**.65 for k in unit))
            return Vector(tuple(k*d/2 for k,d in zip(unit,dims)))
        # Subdivision across each patch follows the chosen tile's aspect ratio.
        # Faces share the same continuous surface even with different row counts.
        span=max(dims)/max(3,3*detail)
        for axis in range(3):
            a,b=(axis+1)%3,(axis+2)%3
            if dims[a]<dims[b]:
                a,b=b,a
            nx=max(2,round(dims[a]/span))
            ny=max(2,round(dims[b]/span*fw/fh))
            if 2*nx*ny>MAX_PARTS:
                raise ValueError('Increase Piece scale with Fill gaps on, or choose a wider-faced part for this shell.')
            for sign in (-1,1):
                group=("+" if sign>0 else "−")+"XYZ"[axis]
                for j in range(ny):
                    for i in range(nx):
                        q=[]
                        for di,dj in ((0,0),(1,0),(1,1),(0,1)):
                            p=Vector();p[axis]=sign;p[a]=2*(i+di)/nx-1;p[b]=2*(j+dj)/ny-1
                            q.append(project(p))
                        center=sum(q,Vector())/4
                        u=(q[1]-q[0]+q[2]-q[3]).normalized()
                        normal=u.cross(q[3]-q[0]+q[2]-q[1]).normalized()
                        if normal.dot(center)<0:
                            normal.negate()
                        v=normal.cross(u)
                        width=max(abs((p-center).dot(u)) for p in q)*2
                        height=max(abs((p-center).dot(v)) for p in q)*2
                        add(center,u,normal,max(width/fw,height/fh))
        return result

    rows = max(6,round(detail*6))
    def surface(t, angle):
        radius=1-s.tube_ratio+s.tube_ratio*cos(tau*t)
        elevation=sin(tau*t)
        x,y=radius*cos(angle),radius*sin(angle)
        return Vector((x*w/2,y*d/2,elevation*h/2))

    for j in range(rows):
        t0,t1=j/rows,(j+1)/rows
        mid=(t0+t1)/2
        circumference=sum((surface(mid,tau*(k+1)/32)-surface(mid,tau*k/32)).length for k in range(32))
        band=max((surface(t0,a)-surface(t1,a)).length for a in (0,pi/2))
        count=max(3,round(circumference/max(band*fw/fh,.0001)))
        for i in range(count):
            a,b=tau*i/count,tau*(i+1)/count
            group=f"Arc {min(3,int(4*(i+.5)/count))+1}"
            corners=[surface(t0,a),surface(t0,b),surface(t1,b),surface(t1,a)]
            center=sum(corners,Vector())/4
            u=((corners[1]-corners[0])+(corners[2]-corners[3])).normalized()
            normal=u.cross((corners[3]-corners[0])+(corners[2]-corners[1])).normalized()
            v=normal.cross(u)
            extent=lambda axis:max(abs((p-center).dot(axis)) for p in corners)*2
            add(center,u,normal,max(extent(u)/fw,extent(v)/fh))
    return result


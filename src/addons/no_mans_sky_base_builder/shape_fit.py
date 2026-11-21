"""Pack uniformly scaled rectangular part faces inside a convex polygon."""
from math import ceil, floor


def bounded_tiles(poly, pitch, fw, fh, thickness, shell, origin, u, v, normal, row_limit, *, rounded_wall=False):
    """Cover a convex face with rigid tiles and constrain both sides of each tile.

    Angular faces are split into sectors. Each sector's tiles follow its outside
    edge and may lap the neighbouring sector inside the face. The outside hull
    is shared, including around omitted faces.
    """
    from math import hypot
    edges = list(zip(poly, poly[1:] + poly[:1]))
    # Each inequality is ax + by + cz <= limit in the coordinates of this face.
    planes = []
    for (x,y),(xx,yy) in edges:
        length = hypot(xx-x, yy-y)
        if length <= 1e-10:
            continue
        a,b = (yy-y)/length,(x-xx)/length
        planes.append((a,b,0.,a*x+b*y))
    for point, outward in shell:
        a,b,c = outward.dot(u),outward.dot(v),outward.dot(normal)
        if c < -1e-6:  # Only inward extrusion can cross another shell plane.
            planes.append((a,b,c,outward.dot(point-origin)))

    def bounds(ux,uy):
        return [(a,b,c,limit,abs(a*ux+b*uy)*fw/2 + abs(b*ux-a*uy)*fh/2 + max(0.,-c)*thickness)
                for a,b,c,limit in planes]

    def clip(x,y,scale,z,ux,uy,limits,levels,sector=None):
        half_w,half_h = fw*scale/2,fh*scale/2
        if sector:
            for a,b,limit in sector:
                support = abs(a*ux+b*uy)*half_w + abs(b*ux-a*uy)*half_h
                if a*x+b*y-support >= limit-1e-8:
                    return
        available = scale
        for a,b,c,limit,support in limits:
            distance = limit-a*x-b*y-c*z
            if distance < -scale*support-1e-7:
                return
            if support > 1e-9:
                available = min(available, distance/support)
        if available >= scale*.985:
            yield x,y,max(0.,available),z,ux,uy
        elif levels:
            for dx in (-half_w/2,half_w/2):
                for dy in (-half_h/2,half_h/2):
                    yield from clip(x+ux*dx-uy*dy,y+uy*dx+ux*dy,scale/2,z,ux,uy,limits,levels-1,sector)
        elif available > scale*.12:
            yield x,y,available,z,ux,uy

    xmin,xmax = min(x for x,y in poly),max(x for x,y in poly)
    ymin,ymax = min(y for x,y in poly),max(y for x,y in poly)
    rect = len(poly)==4 and all(min(abs(x-xmin),abs(x-xmax))<1e-5 and
                                min(abs(y-ymin),abs(y-ymax))<1e-5 for x,y in poly)
    if rounded_wall:
        # A cone's longitudes are sampling seams. Let adjacent courses cross
        # them inside the shell, while keeping the base rim and silhouette.
        from mathutils import Vector
        inward = Vector((-normal.x,-normal.y,0)).normalized()
        supports = [(p,n,abs(n.dot(u))*fw/2+abs(n.dot(v))*fh/2+max(0.,-n.dot(normal))*thickness)
                    for p,n in shell]
        for x,y,scale,relief in fitted_tiles(poly,pitch,fw,fh,False):
            center=origin+u*x+v*y-normal*relief
            bottom=shell[0][0].z
            center.z=max(center.z,bottom+supports[0][2]*scale)
            inset=0.
            for p,n,support in supports[1:]:
                gain=-inward.dot(n)
                if gain>1e-7:
                    inset=max(inset,((center-p).dot(n)+support*scale)/gain)
            center+=inward*inset
            limit=min(((p-center).dot(n)/support for p,n,support in supports if support>1e-8),default=scale)
            if limit<=0:continue
            local=center-origin
            yield local.dot(u),local.dot(v),min(limit,scale),local.dot(normal),1.,0.
        return
    if rect and row_limit and (ymax-ymin)/row_limit > (xmax-xmin)*fh/fw:
        # On very high-sided prisms there may be fewer slots than perfectly
        # flush tiles. Recess the wider courses just enough to clear adjacent
        # facets. Parts can overlap inside this nearly circular rim.
        height=(ymax-ymin)/row_limit
        scale=height/fh
        for j in range(row_limit):
            x,y=(xmin+xmax)/2,ymin+(j+.5)*height
            center=origin+u*x+v*y
            z=0.
            for point,outward in shell:
                facing=normal.dot(outward)
                if facing<=1e-7:continue
                extent=(abs(outward.dot(u))*fw+abs(outward.dot(v))*fh)*scale/2
                z=min(z,(outward.dot(point-center)-extent)/facing)
            yield x,y,scale,z,1.,0.
        return
    if rect or len(poly)>8:
        # Rectangles and many-sided caps already have efficient boundary-aligned courses.
        cache = {}
        for x,y,scale,relief,*axis in fitted_tiles(poly,pitch,fw,fh,rect):
            direction = tuple(axis) if axis else (1.,0.)
            if direction not in cache:cache[direction] = bounds(*direction)
            yield from clip(x,y,scale,-relief,*direction,cache[direction],2)
        return

    if len(poly)==3:
        # Give each ridge one straight course. Place the regular horizontal
        # courses just behind it, so only the join overlaps inside the face.
        lengths=[hypot(xx-x,yy-y) for (x,y),(xx,yy) in edges]
        perimeter=sum(lengths)
        cx=sum(poly[i][0]*lengths[(i+1)%3] for i in range(3))/perimeter
        cy=sum(poly[i][1]*lengths[(i+1)%3] for i in range(3))/perimeter
        radius=(poly[1][0]-poly[0][0])*(poly[2][1]-poly[0][1])/perimeter
        band=min(radius*.48,pitch*.5)
        depths=[]
        for i,(((x,y),(xx,yy)),length) in enumerate(zip(edges,lengths)):
            ux,uy=(xx-x)/length,(yy-y)/length
            count=max(1,ceil(length*fh/(fw*band)-1e-7))
            width=length/count
            depth=width*fh/fw
            limits=bounds(ux,uy)
            z=-pitch*.0006*i
            inset=depth/2
            # A thick tile on a sloping face can pierce the base. Slide the
            # whole straight course inward together to clear that neighbour.
            for a,b,c,limit,support in limits:
                gain=a*uy-b*ux
                if gain>1e-7 and abs(a*x+b*y-limit)<1e-5 and abs(a*xx+b*yy-limit)<1e-5:
                    inset=max(inset,(support*width/fw+c*z)/gain)
            depths.append(inset+depth/2)
            for k in range(count):
                dx=(k+.5)*width
                yield from clip(x+ux*dx-uy*inset,y+uy*dx+ux*inset,
                                width/fw,z,ux,uy,limits,2)
        inset=min(depths)*.8
        ratio=max(0.,1-inset/radius)
        core=[(cx+(x-cx)*ratio,cy+(y-cy)*ratio) for x,y in poly]
        limits=bounds(1.,0.)
        for x,y,scale,relief in fitted_tiles(core,pitch,fw,fh,False):
            yield from clip(x,y,scale,-pitch*.002-relief,1.,0.,limits,1)
        return

    cx = sum(x for x,y in poly)/len(poly)
    cy = sum(y for x,y in poly)/len(poly)
    for i,((x,y),(xx,yy)) in enumerate(edges):
        length = hypot(xx-x,yy-y)
        ux,uy = (xx-x)/length,(yy-y)/length
        along = (cx-x)*ux + (cy-y)*uy
        altitude = (cy-y)*ux - (cx-x)*uy
        if altitude <= 1e-8:continue
        # Anchor a full course to the edge. Choose cell dimensions once; all
        # subdivisions still use the native part's original aspect ratio.
        cols = max(1,ceil(length/pitch-1e-6))
        tile_w = min(length/cols, altitude*fw/fh)
        tile_h = tile_w*fh/fw
        if tile_w<=1e-8:continue
        limits = bounds(ux,uy)
        sector = []
        for p,q in (((xx,yy),(cx,cy)),((cx,cy),(x,y))):
            a,b = q[1]-p[1],p[0]-q[0]
            sector.append((a,b,a*p[0]+b*p[1]))
        # Distinct, shallow recesses prevent coplanar overlaps between sectors.
        z = -pitch*.00045*i
        for j in range(ceil(altitude/tile_h-1e-8)):
            lo,hi = j*tile_h/altitude,min(1,(j+1)*tile_h/altitude)
            left = min(along*lo,along*hi)
            right = max(length+(along-length)*lo,length+(along-length)*hi)
            for k in range(floor(left/tile_w+1e-8),ceil(right/tile_w-1e-8)):
                dx,dy = (k+.5)*tile_w,(j+.5)*tile_h
                yield from clip(x+ux*dx-uy*dy,y+uy*dx+ux*dy,tile_w/fw,z,ux,uy,limits,2,sector)


def rim_and_core(poly,pitch,fw,fh):
    """A continuous row follows each outside edge. Offset edges bound the fill."""
    from math import hypot
    core=poly
    edges=list(zip(poly,poly[1:]+poly[:1]))
    rim=[]
    for edge,((x,y),(x1,y1)) in enumerate(edges):
        length=hypot(x1-x,y1-y);ux,uy=(x1-x)/length,(y1-y)/length
        nx,ny=-uy,ux
        n=max(1,ceil(length/pitch-1e-6))
        scale=length/(n*fw);depth=scale*fh
        # Acute corners or very deep panels need the general polygon fitter.
        for px,py in ((x+nx*depth,y+ny*depth),(x1+nx*depth,y1+ny*depth)):
            if any((b[0]-a[0])*(py-a[1])-(b[1]-a[1])*(px-a[0])<-.000001 for a,b in edges):
                return None
        for i in range(n):
            t=(i+.5)*length/n
            rim.append((x+ux*t+nx*depth/2,y+uy*t+ny*depth/2,scale,
                        (1+(edge%2 if edge<len(edges)-1 else 2))*min(depth,pitch)*.0004,ux,uy))
        cut=[]
        for a,b in zip(core,core[1:]+core[:1]):
            da=(a[0]-x)*nx+(a[1]-y)*ny-depth
            db=(b[0]-x)*nx+(b[1]-y)*ny-depth
            if da>=0:cut.append(a)
            if (da<0)!=(db<0):
                t=da/(da-db)
                cut.append((a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])))
        core=cut
    return rim,core


def core_tiles(outer,core,pitch,fw,fh):
    # Tile behind the rim. At this interior seam panels can extend underneath
    # the rim, provided every corner still lies inside the true outer contour.
    xmin,xmax=min(x for x,y in core),max(x for x,y in core)
    ymin,ymax=min(y for x,y in core),max(y for x,y in core)
    def planes(poly):
        return [(y-v,u-x,x,y) for (x,y),(u,v) in zip(poly,poly[1:]+poly[:1]) if abs(x-u)+abs(y-v)>1e-9]
    inside,outline=planes(core),planes(outer)
    def tile(x,y,scale,depth):
        a,b=fw*scale/2,fh*scale/2
        if any(dx*(x-px)+dy*(y-py)<-abs(dx)*a-abs(dy)*b for dx,dy,px,py in inside):return
        fit=min((dx*(x-px)+dy*(y-py))/(abs(dx)*a+abs(dy)*b) for dx,dy,px,py in outline)
        if fit>=1-1e-7:yield x,y,scale,0.
        elif depth:
            for sx in (-a/2,a/2):
                for sy in (-b/2,b/2):yield from tile(x+sx,y+sy,scale/2,depth-1)
        elif fit>.05:yield x,y,scale*fit,0.
    scale=pitch/fw
    nx=max(1,ceil((xmax-xmin)/pitch))
    ny=max(1,ceil((ymax-ymin)/(scale*fh)))
    for j in range(ny):
        for i in range(nx):
            yield from tile((xmin+xmax)/2+(i+.5-nx/2)*pitch,
                            (ymin+ymax)/2+(j+.5-ny/2)*scale*fh,scale,3)


def fitted_tiles(poly, pitch, fw, fh, rectangular):
    if len(poly)==3 and abs(poly[0][1]-poly[1][1])<1e-6:
        # Keep the first course on its base plane. Taper the height as well
        # as the width at the apex; adjacent facets cover their narrow joins.
        left,right=sorted((poly[0][0],poly[1][0]))
        apex,top=poly[2];bottom=poly[0][1];height=top-bottom
        level=0.
        while level<height-1e-8:
            remaining=1-level/height
            a=apex+(left-apex)*remaining;b=apex+(right-apex)*remaining
            # At most a small fraction of the remaining side is covered by one course.
            step=min(pitch*fh/fw,(b-a)*fh/fw,(height-level)*.35)
            if max((height-level)*fw/fh,b-a)<pitch*.07:step=height-level
            if step<=1e-9:break
            tile=step*fw/fh
            n=max(1,ceil((b-a)/tile-1e-7))
            for i in range(n):
                x=a+tile/2+(b-a-tile)*i/max(1,n-1)
                yield x,bottom+level+step/2,step/fh,(i%2)*step*.00035
            level+=step
        return
    if len(poly)>4:
        border=rim_and_core(poly,pitch,fw,fh)
        if border is not None:
            rim,core=border
            yield from rim
            if len(core)>=3:yield from core_tiles(poly,core,pitch,fw,fh)
            return
    xmin, xmax = min(x for x,y in poly), max(x for x,y in poly)
    ymin, ymax = min(y for x,y in poly), max(y for x,y in poly)
    width, height = xmax-xmin, ymax-ymin
    if min(width,height)<1e-6:return
    size = min(width/max(1,round(width/pitch))/fw, height/fh)
    tw, th = fw*size, fh*size
    nx, ny = max(1,ceil(width/tw-1e-6)), max(1,ceil(height/th-1e-6))
    if rectangular:
        # Anchor the outside edges. Spread any residual overlap across the interior.
        for j in range(ny):
            for i in range(nx):
                x=xmin+tw/2+(width-tw)*i/max(1,nx-1)
                y=ymin+th/2+(height-th)*j/max(1,ny-1)
                yield x,y,size,(i%2+2*(j%2))*min(tw,th)*.00015
        return
    # A convex polygon contains the rectangle common to both ends of a
    # horizontal band. Fill that span, then halve the height only in the
    # uncovered strips. Small pieces follow the rim without cutting the proxy.
    from functools import lru_cache
    edges=list(zip(poly,poly[1:]+poly[:1]))
    @lru_cache(None)
    def span(y):
        hits=[]
        for (x0,y0),(x1,y1) in edges:
            if abs(y1-y0)<1e-10:
                if abs(y-y0)<1e-7:hits.extend((x0,x1))
            elif min(y0,y1)-1e-7<=y<=max(y0,y1)+1e-7:
                t=max(0.,min(1.,(y-y0)/(y1-y0)))
                hits.append(x0+(x1-x0)*t)
        return (min(hits),max(hits)) if hits else (0.,0.)
    def course(bottom,top,left,right,levels):
        mid=(bottom+top)/2
        # Convexity guarantees the whole tile fits if both end spans contain it.
        lower,upper=span(bottom),span(top)
        a=max(left,lower[0],upper[0]);b=min(right,lower[1],upper[1])
        scale=(top-bottom)/fh
        step=fw*scale
        n=max(0,ceil((b-a)/step-1e-7)) if b-a>=step*.65 else 0
        if n:
            # Locate full-width tiles flush to one side. A single residual
            # strip is cheaper to fill than two narrow slivers.
            tile=min(step,b-a)
            for i in range(n):
                x=a+tile/2+(b-a-tile)*i/max(1,n-1)
                for j in range(2 if tile<step*.99999 else 1):
                    y=(bottom+tile*fh/fw/2 if j==0 else top-tile*fh/fw/2)
                    yield x,y,tile/fw,(i%2+2*j)*scale*.0004
            residual=((left,a),(b,right))
        else:
            residual=((left,right),)
            if not levels and b-a>step*.1:
                yield (a+b)/2,mid,(b-a)/fw,0.
        if levels:
            # Include polygon vertices inside the band at a turning point.
            extent=[lower,upper]+[(x,x) for x,y in poly if bottom<y<top]
            for lo,hi in residual:
                lo=max(lo,min(v[0] for v in extent));hi=min(hi,max(v[1] for v in extent))
                if hi-lo>step*.035:
                    yield from course(bottom,mid,lo,hi,levels-1)
                    yield from course(mid,top,lo,hi,levels-1)
    levels=2
    for j in range(ny):
        yield from course(ymin+height*j/ny,ymin+height*(j+1)/ny,xmin,xmax,levels)

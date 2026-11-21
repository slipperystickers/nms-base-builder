"""Fit usable native part faces to filled 2D presets."""
from heapq import heappop, heappush
from math import ceil, hypot, sqrt
from mathutils import Matrix, Vector


def face_profile(geometry, footprint, correction, depsgraph):
    """Sample the frontmost surface. Fit a continuous patch and use its dominant depth."""
    import numpy as np
    width,height,depth=footprint
    side=33
    dx,dy=width/side,height/side
    hits=np.full((side,side),-np.inf)
    for obj,relative in geometry:
        mesh=obj.evaluated_get(depsgraph)
        to_face=correction @ relative
        local=to_face.inverted_safe()
        direction=local.to_3x3() @ Vector((0,0,-1))
        for j in range(side):
            for i in range(side):
                origin=local @ Vector(((i+.5)*dx-width/2,(j+.5)*dy-height/2,depth+1))
                ok,p,_,_=mesh.ray_cast(origin,direction,depsgraph=depsgraph)
                if ok:hits[j,i]=max(hits[j,i],(to_face @ p).z)
    valid=np.isfinite(hits)
    if not valid.any():
        raise ValueError('No visible surface on this side. Choose another outside face.')
    # Largest continuous rectangle in the silhouette. Decorative feet and cutouts
    # would leave openings if they were counted as part of the repeatable area.
    heights=[0]*side
    best=0
    for j,row in enumerate(valid):
        stack=[]
        for i in range(side+1):
            if i<side:heights[i]=heights[i]+1 if row[i] else 0
            h=heights[i] if i<side else 0
            start=i
            while stack and stack[-1][1]>h:
                start,rows=stack.pop()
                area=rows*(i-start)
                if area>best:
                    best=area
                    left,right,bottom,top=start,i,j+1-rows,j+1
            if h and (not stack or stack[-1][1]<h):stack.append((start,h))
    patch=hits[bottom:top,left:right]
    # Ignore protruding rims when seating the broad surface. Select the most
    # common visible depth, with the median of that band as its actual plane.
    band=max(depth*.012,max(width,height)*.0001,1e-6)
    bins=np.rint((patch-patch.min())/band).astype(int)
    z=float(np.median(patch[bins==np.bincount(bins.ravel()).argmax()]))
    center=Vector(((left+right)*dx/2-width/2,(bottom+top)*dy/2-height/2,z))
    # Half a sample cell of seam overlap per side also covers small bevels.
    use_w=max(.5,right-left-.9)*dx
    use_h=max(.5,top-bottom-.9)*dy
    extents=(-width/2-center.x,width/2-center.x,-height/2-center.y,height/2-center.y)
    return (use_w,use_h,depth,*extents),Matrix.Translation(-center) @ correction


def clip(poly,axis,bound,sign):
    out=[]
    previous=poly[-1]
    before=(previous[axis]-bound)*sign
    for point in poly:
        after=(point[axis]-bound)*sign
        if (before<0)!=(after<0):
            t=before/(before-after)
            out.append(tuple(a+(b-a)*t for a,b in zip(previous,point)))
        if after>=0:out.append(point)
        previous,before=point,after
    return out


def outlined_fill(vertices,pitch,footprint,percent,budget):
    """Lay an edge-parallel band, then cover only the polygon inside that band."""
    fw,fh,_,left,right,bottom,top=footprint
    if min(fw/(right-left),fh/(top-bottom))<.87:
        # A deeply notched side cannot supply a continuous straight lip.
        # Fit its measured solid patch across the silhouette instead.
        yield from fill(vertices,pitch*2**((40-percent)/100),footprint,percent/20,budget)
        return
    poly=[(p.x,p.y) for p in vertices]
    cx=sum(x for x,y in poly)/len(poly)
    cy=sum(y for x,y in poly)/len(poly)
    edges=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1]
        length=hypot(dx,dy)
        ux,uy=dx/length,dy/length
        distance=(cy-a[1])*ux-(cx-a[0])*uy
        edges.append((ux,uy,length,distance))
    radius=min(e[3] for e in edges)
    # Profile the band from the face actually pointing up. Long thin faces need
    # a shallower band than square faces to avoid a dense, overlapping fringe.
    rim_pitch=pitch*2**((40-percent)/45)
    # Reserve enough slots for corner refinement when using a narrow side.
    perimeter=sum(e[2] for e in edges)
    rim_pitch=max(rim_pitch,perimeter*max(2.,fw/fh)/(budget*.20))
    fraction=min(.5,rim_pitch*fh/(fw*radius),
                 min(length*fh/(fw*dist) for _,_,length,dist in edges))
    core=[(x+(cx-x)*fraction,y+(cy-y)*fraction) for x,y in poly]
    planes=[(uy,-ux,uy*x-ux*y) for (x,y),(ux,uy,_,_) in zip(poly,edges)]
    tolerance=max(radius*.00015,radius*.019*2**(-percent/18))
    leaves={}
    queue=[]
    serial=0

    def fit(points,origin,ux,uy,border,level):
        xs,ys=zip(*points)
        x0,x1=min(xs),max(xs)
        y0,y1=min(ys),max(ys)
        if min(x1-x0,y1-y0)<1e-8:return None
        # Only the rim uses the actual outer side as its contact line. The
        # measured continuous patch still dictates interior pitch and overlap.
        smooth_lip=max(0.,-bottom-fh/2)<=fh*.02 and max(0.,top-fh/2)<=fh*.02
        low=bottom if border and y0<1e-7 and smooth_lip else -fh/2
        scale=max((x1-x0)/fw,(y1-y0)/(fh/2-low))
        ax,bx=x1-scale*fw/2,x0+scale*fw/2
        ay,by=y1-scale*fh/2,y0-scale*low
        x,y=(ax+bx)/2,(ay+by)/2
        outer=border and y0<1e-7
        if outer:y=by
        # Centre each tile on its own patch. Only use available slack to move
        # it inward if the physical proxy would cross a silhouette plane.
        for nx,ny,d in planes:
            along,across=nx*ux+ny*uy,ny*ux-nx*uy
            reach=max(along*left,along*right)+max(across*bottom,across*top)
            spill=nx*origin[0]+ny*origin[1]+along*x+across*y+scale*reach-d
            if spill>0:
                x=max(ax,min(bx,x-along*spill))
                if not outer:y=max(ay,min(by,y-across*spill))
        px,py=origin[0]+ux*x-uy*y,origin[1]+uy*x+ux*y
        excess=0.
        for nx,ny,d in planes:
            along,across=nx*ux+ny*uy,ny*ux-nx*uy
            reach=max(along*left,along*right)+max(across*bottom,across*top)
            excess=max(excess,nx*px+ny*py+scale*reach-d)
        return (excess,(px,py),scale,points,origin,ux,uy,border,level)

    def insert(cell):
        nonlocal serial
        if cell is None:return
        leaves[serial]=cell
        if cell[0]>tolerance and cell[-1]<12:heappush(queue,(-cell[0],serial))
        serial+=1

    def courses(patch,origin,ux,uy,rows,cols,border):
        local=[((x-origin[0])*ux+(y-origin[1])*uy,
                (y-origin[1])*ux-(x-origin[0])*uy) for x,y in patch]
        xs,ys=zip(*local)
        x0,x1=min(xs),max(xs)
        y0,y1=min(ys),max(ys)
        for j in range(rows):
            band=clip(local,1,y0+(y1-y0)*j/rows,1)
            if band:band=clip(band,1,y0+(y1-y0)*(j+1)/rows,-1)
            if not band:continue
            for i in range(cols):
                part=clip(band,0,x0+(x1-x0)*i/cols,1)
                if part:part=clip(part,0,x0+(x1-x0)*(i+1)/cols,-1)
                if part:insert(fit(part,origin,ux,uy,border,0))

    rim_counts=[max(1,round(length*fh/(fraction*distance*fw))) for _,_,length,distance in edges]
    remaining=budget-sum(rim_counts)
    if remaining<1:
        # An extremely thin face, high-sided preset or very small part budget
        # can leave no room for a complete rim and interior. Cover both together.
        yield from fill(vertices,pitch,footprint,percent/20,budget)
        return
    for i,((ux,uy,_,_),count) in enumerate(zip(edges,rim_counts)):
        j=(i+1)%len(poly)
        courses([poly[i],poly[j],core[j],core[i]],poly[i],ux,uy,1,count,True)

    xs,ys=zip(*core)
    width,height=max(xs)-min(xs),max(ys)-min(ys)
    cols,rows=width/pitch,height/(pitch*fh/fw)
    factor=min(1.,sqrt(remaining/max(cols*rows,1e-12)))
    cols=min(remaining,max(1,round(cols*factor)))
    rows=min(remaining//cols,max(1,round(rows*factor)))
    courses(core,(0,0),1,0,rows,cols,False)
    # Refine protrusions at corners and under the rim, largest first. Never
    # remove a covered patch unless all its children fit the remaining budget.
    while queue and len(leaves)<budget:
        _,key=heappop(queue)
        over,_,_,points,origin,ux,uy,border,level=leaves[key]
        xs,ys=zip(*points)
        mx,my=(min(xs)+max(xs))/2,(min(ys)+max(ys))/2
        children=[]
        for sx in (-1,1):
            half=clip(points,0,mx,sx)
            if not half:continue
            for sy in (-1,1):
                patch=clip(half,1,my,sy)
                child=fit(patch,origin,ux,uy,border,level+1) if patch else None
                if child:children.append(child)
        if (len(children)>1 and len(leaves)+len(children)-1<=budget and
                max(c[0] for c in children)<=over+1e-7):
            del leaves[key]
            for child in children:insert(child)
    for i,(_,pos,scale,_,_,ux,uy,border,_) in enumerate(leaves.values()):
        relief=-radius*.00012*((0 if border else 2)+(i*.61803398875)%1)
        yield Vector((*pos,relief)),Vector((ux,uy,0)),scale


def fill(vertices,pitch,footprint,detail,budget):
    """Cover the whole polygon first, then subdivide only cells crossing its boundary."""
    fw,fh=footprint[:2]
    poly=[(p.x,p.y) for p in vertices]
    xmin,xmax=min(x for x,y in poly),max(x for x,y in poly)
    ymin,ymax=min(y for x,y in poly),max(y for x,y in poly)
    width,height=xmax-xmin,ymax-ymin
    planes=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        ex,ey=b[0]-a[0],b[1]-a[1]
        length=hypot(ex,ey)
        nx,ny=ey/length,-ex/length
        planes.append((nx,ny,a[0]*nx+a[1]*ny))
    left,right,bottom,top=footprint[3:]
    ideal=(width/pitch,height/(pitch*fh/fw))
    factor=min(1.,sqrt(budget/max(1.,ideal[0]*ideal[1])))
    nx=min(budget,max(1,round(ideal[0]*factor)))
    ny=min(budget//nx,max(1,round(ideal[1]*factor)))
    leaves={}
    queue=[]
    serial=0
    tolerance=min(width,height,pitch)*.08/(2**detail)

    def tile(points,level):
        xs,ys=zip(*points)
        x,y=min(xs),min(ys)
        w,h=max(xs)-x,max(ys)-y
        if min(w,h)<1e-8:return None
        area=abs(sum((a[0]-x)*(b[1]-y)-(b[0]-x)*(a[1]-y)
                     for a,b in zip(points,points[1:]+points[:1])))/2
        if area<1e-12:return None
        mx,my=x+w/2,y+h/2
        efficient=min(max(w/fw,h/fh),max(w/fh,h/fw))
        max_scale=1.4*efficient
        radius=(hypot(max(abs(left),right),max(abs(bottom),top))+hypot(fw,fh)/2)*max_scale+hypot(w,h)
        nearby=[(nx,ny,d) for nx,ny,d in planes if d-nx*mx-ny*my<radius]
        # A boundary tile can rotate along the actual polygon edge. Slide its
        # spare width inward while keeping the entire clipped patch covered.
        directions=[(1.,0.),(0.,1.)]
        if w*h-area>w*h*1e-6:
            for a,b in zip(points,points[1:]+points[:1]):
                ex,ey=b[0]-a[0],b[1]-a[1]
                length=hypot(ex,ey)
                if abs(ex)>1e-8 and abs(ey)>1e-8:
                    directions.extend(((ex/length,ey/length),(-ey/length,ex/length)))
        best=None
        for ux,uy in directions:
            us=[px*ux+py*uy for px,py in points]
            vs=[py*ux-px*uy for px,py in points]
            u0,u1=min(us),max(us)
            v0,v1=min(vs),max(vs)
            scale=max((u1-u0)/fw,(v1-v0)/fh)
            if scale>max_scale:continue
            # Choose the valid centre nearest the shape origin (inside every preset).
            cu=max(u1-scale*fw/2,min(0.,u0+scale*fw/2))
            cv=max(v1-scale*fh/2,min(0.,v0+scale*fh/2))
            cx,cy=cu*ux-cv*uy,cu*uy+cv*ux
            over=0.
            for nx,ny,d in nearby:
                along,across=nx*ux+ny*uy,ny*ux-nx*uy
                support=max(along*left,along*right)+max(across*bottom,across*top)
                over=max(over,nx*cx+ny*cy+scale*support-d)
            score=over+.015*scale*max(fw,fh)
            if best is None or score<best[0]-1e-9:
                best=(score,cx,cy,scale,ux,uy,over)
        _,cx,cy,scale,ux,uy,over=best
        return (points,level,mx,my,cx,cy,scale,ux,uy,over)

    def insert(cell):
        nonlocal serial
        leaves[serial]=cell
        if cell[-1]>tolerance and cell[1]<detail:heappush(queue,(-cell[-1],serial))
        serial+=1

    for j in range(ny):
        band=clip(poly,1,ymin+height*j/ny,1)
        if not band:continue
        band=clip(band,1,ymin+height*(j+1)/ny,-1)
        if not band:continue
        for i in range(nx):
            points=clip(band,0,xmin+width*i/nx,1)
            if points:
                points=clip(points,0,xmin+width*(i+1)/nx,-1)
            if points:
                cell=tile(points,0)
                if cell:insert(cell)
    while queue and len(leaves)<budget:
        _,key=heappop(queue)
        points,level,cx,cy,*_=leaves[key]
        children=[]
        for direction in (-1,1):
            half=clip(points,0,cx,direction)
            if not half:continue
            for vertical in (-1,1):
                child=clip(half,1,cy,vertical)
                if child:
                    cell=tile(child,level+1)
                    if cell:children.append(cell)
        if (len(children)>1 and len(leaves)+len(children)-1<=budget and
                max(child[-1] for child in children)<=leaves[key][-1]+1e-7):
            del leaves[key]
            for cell in children:insert(cell)
    for index,(_,level,_,_,x,y,scale,ux,uy,_) in enumerate(leaves.values()):
        # Stagger overlapping joins slightly without lifting the visible fill.
        relief=-min(width,height)*.000025*((index%7)+level*.31+(index*.61803398875)%1)
        yield Vector((x,y,relief)),Vector((ux,uy,0)),scale

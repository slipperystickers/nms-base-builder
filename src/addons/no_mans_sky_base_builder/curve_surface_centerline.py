"""Boundary-derived center paths for broad, possibly hooked surface strips."""
import heapq
import math
import numpy as np
from mathutils import Vector


def centerline(segments, center, normal, direction, resolution=768):
    if not len(segments): return []
    origin=np.asarray(center);u=np.asarray(direction);v=np.cross(np.asarray(normal),u)
    edges=np.asarray(segments,dtype=float)-origin
    planar=np.stack((edges@u,edges@v),axis=-1)
    lo=planar.min(axis=(0,1));hi=planar.max(axis=(0,1))
    step=max(hi-lo)/resolution
    if step<1e-8:return []
    size=np.ceil((hi-lo)/step).astype(int)+5
    lo-=2*step
    mask=np.zeros((size[1],size[0]),dtype=bool)
    a,b=planar[:,0],planar[:,1]
    # Even/odd scan conversion handles concave patches and holes without
    # traversing or projecting their millions of interior triangles.
    for row in range(1,len(mask)-1):
        y=lo[1]+row*step
        use=(a[:,1]>y)!=(b[:,1]>y)
        aa,bb=a[use],b[use]
        x=np.sort(aa[:,0]+(y-aa[:,1])*(bb[:,0]-aa[:,0])/(bb[:,1]-aa[:,1]))
        for left,right in zip(x[::2],x[1::2]):
            first=max(1,int(math.ceil((left-lo[0])/step)))
            last=min(size[0]-2,int(math.floor((right-lo[0])/step)))
            mask[row,first:last+1]=True
    thin=mask.copy()
    # Vectorized Zhang-Suen thinning. Work is bounded by raster size, not by
    # mesh density, and the two passes preserve the strip's connectivity.
    for _ in range(int(min(size))+1):
        changed=False
        for phase in (0,1):
            p=thin[1:-1,1:-1]
            n=[thin[:-2,1:-1],thin[:-2,2:],thin[1:-1,2:],thin[2:,2:],
               thin[2:,1:-1],thin[2:,:-2],thin[1:-1,:-2],thin[:-2,:-2]]
            count=sum(q.astype(np.uint8) for q in n)
            transitions=sum((~n[i]&n[(i+1)%8]).astype(np.uint8) for i in range(8))
            remove=p&(count>=2)&(count<=6)&(transitions==1)
            if phase==0:remove &= ~(n[0]&n[2]&n[4]) & ~(n[2]&n[4]&n[6])
            else:remove &= ~(n[0]&n[2]&n[6]) & ~(n[0]&n[4]&n[6])
            if remove.any():p[remove]=False;changed=True
        if not changed:break
    pixels={tuple(p) for p in np.argwhere(thin)}
    if len(pixels)<2:return []
    def search(start):
        distances={start:0.};previous={};queue=[(0.,start)]
        while queue:
            dist,p=heapq.heappop(queue)
            if dist!=distances[p]:continue
            for dy,dx in ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)):
                q=(p[0]+dy,p[1]+dx)
                if q not in pixels:continue
                cost=dist+math.hypot(dx,dy)
                if cost<distances.get(q,float('inf')):
                    distances[q]=cost;previous[q]=p;heapq.heappush(queue,(cost,q))
        return max(distances,key=distances.get),previous,distances
    # Pick the largest component if tiny boundary defects made isolated pixels.
    remaining=pixels.copy();largest=set()
    while remaining:
        _,_,component=search(next(iter(remaining)))
        if len(component)>len(largest):largest=set(component)
        remaining.difference_update(component)
    pixels=largest
    start,_,_=search(next(iter(pixels)))
    end,previous,_=search(start)
    route=[end]
    while route[-1]!=start:route.append(previous[route[-1]])
    xy=np.asarray([(p[1],p[0]) for p in route],dtype=float)
    for reverse in (False,True):
        if reverse:xy=xy[::-1].copy()
        tangent=xy[0]-xy[min(12,len(xy)-1)]
        length=np.linalg.norm(tangent)
        if length:
            tangent/=length;tip=xy[0].copy()
            for _ in range(max(size)):
                trial=tip+tangent
                x,y=np.rint(trial).astype(int)
                if not (0<=y<size[1] and 0<=x<size[0] and mask[y,x]):break
                tip=trial
            xy=np.vstack((tip,xy))
    # Smooth raster stair steps, then sample a modest number of curve handles.
    for _ in range(3):xy[1:-1]=(xy[:-2]+2*xy[1:-1]+xy[2:])/4
    lengths=np.r_[0,np.cumsum(np.linalg.norm(np.diff(xy,axis=0),axis=1))]
    samples=np.linspace(0,lengths[-1],min(321,max(3,int(lengths[-1]/3))))
    xy=np.column_stack([np.interp(samples,lengths,xy[:,i]) for i in (0,1)])
    xy=lo+xy*step
    # Thinning preserves topology but its diagonal end branches are not a
    # metric medial axis. Center each cross section between the real borders.
    tangent_span=max(3,round(len(xy)*3/161))
    for _ in range(4):
        adjusted=xy.copy()
        for i,p in enumerate(xy):
            j=min(max(i,tangent_span+1),len(xy)-tangent_span-2) if len(xy)>2*tangent_span+3 else i
            tangent=xy[min(len(xy)-1,j+tangent_span)]-xy[max(0,j-tangent_span)]
            length=np.linalg.norm(tangent)
            if length<step:continue
            across=np.array([-tangent[1],tangent[0]])/length
            delta=b-a;offset=a-p
            denom=across[0]*delta[:,1]-across[1]*delta[:,0]
            valid=np.abs(denom)>1e-10
            t=np.zeros(len(a));r=t.copy()
            t[valid]=(offset[valid,0]*delta[valid,1]-offset[valid,1]*delta[valid,0])/denom[valid]
            r[valid]=(offset[valid,0]*across[1]-offset[valid,1]*across[0])/denom[valid]
            hits=np.sort(t[valid&(r>=0)&(r<=1)])
            lower=hits[hits<=step*.1];upper=hits[hits>=-step*.1]
            if len(lower) and len(upper) and upper[0]-lower[-1]<max(hi-lo)*.15:
                adjusted[i]=p+across*(lower[-1]+upper[0])/2
        xy=adjusted
    # Penalize changes in tangent, rather than repeatedly averaging raw raster
    # pixels. Boundary recentering can amplify one-pixel tangent noise into
    # alternating sideways offsets, especially around a wide rounded hook.
    n=len(xy)
    if n>4:
        second=np.diff(np.eye(n),n=2,axis=0)
        weights=np.ones(n);weights[[0,-1]]=1000.
        xy=np.linalg.solve(np.diag(weights)+12.*second.T@second,weights[:,None]*xy)
        # Smoothly interpolate the cleaned handles before surface projection.
        # These dense samples stay VECTOR-handled, so Blender cannot overshoot
        # the surface with unconstrained automatic Bezier handles.
        padded=np.vstack((2*xy[0]-xy[1],xy,2*xy[-1]-xy[-2]))
        t=np.arange(2,dtype=float)[:,None]/2
        samples=[]
        for i in range(n-1):
            p0,p1,p2,p3=padded[i:i+4]
            samples.extend(.5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t
                               +(-p0+3*p1-3*p2+p3)*t*t*t))
        xy=np.vstack((samples,xy[-1]))
    return [Vector(origin+u*p[0]+v*p[1]) for p in xy]

"""Transport rigid native parts over a deformed shape without remeshing them."""
from mathutils import Euler, Matrix, Vector


def dimensions(settings):
    return (settings.width,settings.depth,settings.height)


def map_points(points,s):
    import numpy as np
    axial=2 if s.dimension=='D3' else 1
    side=1 if axial==2 else 2
    span=s.height if axial==2 else s.depth
    out=points.copy()
    if not (s.pinch or s.twist or s.bend):return out
    position=out[:,axial].copy()
    fraction=position/span
    pinch=1-s.pinch*np.maximum(0.,1-(2*fraction)**2)**2
    x=out[:,0]*pinch
    y=out[:,side]*pinch
    angle=s.twist*fraction
    ca,sa=np.cos(angle),np.sin(angle)
    transverse=x*ca-y*sa
    out[:,side]=x*sa+y*ca
    if abs(s.bend)>1e-6:
        angle=s.bend*fraction
        radius=span/s.bend
        # Half-angle form stays accurate close to zero bend.
        out[:,0]=2*radius*np.sin(angle/2)**2+transverse*np.cos(angle)
        out[:,axial]=(radius-transverse)*np.sin(angle)
    else:
        out[:,0]=transverse
    return out



class Surface:
    """Rest surface sampled once per gesture. All pieces share one vectorized map."""
    def __init__(self,cells,dims,footprint,correction):
        import numpy as np
        self.dims=np.array(dims,dtype=float)
        self.points=np.array([tuple(c[0]) for c in cells]).reshape(-1,3)
        self.u=np.array([tuple(c[1]) for c in cells]).reshape(-1,3)
        self.n=np.array([tuple(c[2]) for c in cells]).reshape(-1,3)
        self.v=np.cross(self.n,self.u)
        self.scales=np.array([c[3] for c in cells])
        self.footprint=footprint
        self.protected=False
        self.fill_scale=None
        self.aspect=footprint[0]/footprint[1]
        self.correction=np.asarray(correction,dtype=float)

    def matrices(self,s):
        import numpy as np
        if not len(self.points):return np.empty((0,4,4))
        dims=np.array(dimensions(s))
        ratio=dims/self.dims
        if s.dimension=='D2':ratio[2]=1
        def deform(points):
            return map_points(points*ratio,s)

        count=len(self.points)
        matrices=np.zeros((count,4,4))
        matrices[:,3,3]=1.
        if (not s.twist and not s.bend and not s.pinch and np.all(ratio==1)):
            pos,u,v,n,scale=self.points,self.u,self.v,self.n,self.scales
        else:
            eps=max(min(self.dims)*.00001,1e-8)
            pos=deform(self.points)
            du=(deform(self.points+self.u*eps)-deform(self.points-self.u*eps))/(2*eps)
            dv=(deform(self.points+self.v*eps)-deform(self.points-self.v*eps))/(2*eps)
            def normalize(rows,fallback):
                norms=np.linalg.norm(rows,axis=1)[:,None]
                return np.where(norms>1e-8,rows/np.maximum(norms,1e-8),fallback)
            u=normalize(du,self.u)
            n=normalize(np.cross(du,dv),self.n)
            v=normalize(np.cross(n,u),self.v)
            scale=self.scales
            if self.protected:
                # Inscribe the rigid tile in its transported cell during a drag.
                # The area divided by each projected extent gives the clearance
                # between opposite sides, including shear from bend or twist.
                dot=lambda a,b: np.einsum('ij,ij->i',a,b)
                area=np.linalg.norm(np.cross(du,dv),axis=1)
                # Inverse of [du dv] in the local u,v frame, applied to the
                # four corners of a tile with the original width/height ratio.
                across_u=abs(dot(dv,v))+abs(dot(dv,u))/self.aspect
                across_v=abs(dot(du,u))+self.aspect*abs(dot(du,v))
                scale=self.scales*area/np.maximum(np.maximum(across_u,across_v),1e-9)
            elif s.fit or self.fill_scale is not None:
                # A twisted cell is a parallelogram. Fit the rigid tile around
                # both edges rather than losing coverage along the shear.
                dot=lambda a,b: np.einsum('ij,ij->i',a,b)
                def fit_width(x,y):
                    return np.maximum(abs(dot(du,x))+abs(dot(dv,x))/self.aspect,
                                      abs(dot(dv,y))+abs(dot(du,y))*self.aspect)
                stretch=fit_width(u,v)
                alt_v=normalize(dv,v);alt_u=normalize(np.cross(alt_v,n),u)
                other=fit_width(alt_u,alt_v)
                # Keep orientations continuous. Blend the two candidate frames
                # across the transition instead of flipping at equal cost.
                weight=np.clip(.5+(stretch-other)/(stretch+other+1e-8)*4,0,1)[:,None]
                u=normalize(u*(1-weight)+alt_u*weight,u)
                v=normalize(np.cross(n,u),v)
                scale=self.scales*np.maximum(fit_width(u,v),.001)
                if self.fill_scale is not None and (s.twist or s.bend or s.pinch):
                    # The tangent at the centre can underestimate a tile on a curved
                    # surface. Include the four transported corners in the fitted span.
                    half_w=self.scales*self.footprint[0]/2
                    half_h=self.scales*self.footprint[1]/2
                    for sign_u,sign_v in ((1,1),(1,-1),(-1,1),(-1,-1)):
                        corner=deform(self.points+self.u*(sign_u*half_w[:,None])+self.v*(sign_v*half_h[:,None]))-pos
                        scale=np.maximum(scale,2*abs(dot(corner,u))/self.footprint[0])
                        scale=np.maximum(scale,2*abs(dot(corner,v))/self.footprint[1])
        matrices[:,:3,0]=u*scale[:,None]
        matrices[:,:3,1]=v*scale[:,None]
        matrices[:,:3,2]=n*scale[:,None]
        matrices[:,:3,3]=pos
        local=Matrix.LocRotScale(Vector(s.offset),Euler(s.turn).to_quaternion(),Vector((s.size/(self.fill_scale or 1.),)*3))
        return matrices @ (np.asarray(local) @ self.correction)


def surface(root,s,footprint,correction,*,refined=None,reflow=False,planar=False,budgeted=False):
    from types import SimpleNamespace
    from . import shape_layout
    protected = s.fit and (s.filled_2d if s.dimension=='D2' else s.preserve_edges and s.shell in shape_layout.FACETED)
    dims=tuple(root.get('bbe_shape_rest_dims',dimensions(s))) if root and not (reflow and protected) else dimensions(s)
    layout=SimpleNamespace(width=dims[0],depth=dims[1],height=dims[2],
        **{key:getattr(s,key) for key in ('dimension','outline','shell','detail','sides','flat','fit','filled_2d','preserve_edges','tube_ratio','pole_taper')})
    fill_scale=root.get('bbe_shape_fill_scale') if root is not None else None
    layout.planar=planar
    layout.edge_detail=s.edge_detail
    layout.rim_layout=planar and (budgeted or root is None or root.get('bbe_shape_rim_layout',False))
    layout.edge_quality=s.edge_quality
    # Reconstruct old saved rest cells until the first refit.
    layout.part_limit=s.part_limit if budgeted or root is None or root.get('bbe_shape_budgeted') else shape_layout.MAX_PARTS
    if root is None or reflow:
        if not s.fit:fill_scale=None
        elif s.fill_gaps:fill_scale=s.size
    if fill_scale is not None:
        layout.detail=s.detail/fill_scale
        # Fail before allocating ring coordinates for a sub-millimetre size.
        if s.dimension=='D2' and (planar or not s.filled_2d):
            layout.detail=min(layout.detail,layout.part_limit)
        elif layout.detail>(512 if s.dimension=='D2' else 128):
            raise ValueError('This fill exceeds the 4,096-part limit. Increase Piece scale to use fewer parts.')
    groups=[]
    if refined is None:refined=root is None or bool(root.get('bbe_shape_refined'))
    all_cells=shape_layout.placements(layout,footprint,groups,refined=refined)
    excluded=set(root.get('bbe_shape_excluded','').split('|')) if root else set()
    slots=[i for i,group in enumerate(groups) if group not in excluded]
    result=Surface([all_cells[i] for i in slots],dims,footprint,correction)
    result.protected=protected and not planar
    result.fill_scale=fill_scale
    result.slots=slots
    result.groups=groups
    return result


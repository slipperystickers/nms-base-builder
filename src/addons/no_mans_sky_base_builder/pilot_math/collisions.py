"""Read-only native collider queries. No Blender, game, save, or binary API.

Transforms are 4x4 column matrices in a caller-chosen common coordinate frame.
Only explicit native collision shapes are accepted; visual meshes are never
used. Geometry coverage and unresolved candidates are returned separately.
"""
from dataclasses import dataclass
import numpy as np


class NativeCollisionError(ValueError):
    """The supplied build cannot be covered by the native collision catalog."""


@dataclass(frozen=True)
class Segment:
    start: object
    end: object


def foot_ray_segments(model_ankles,model_to_world,extent):
    """Native ray lengths around supplied previous-solved ankle anchors.

    The caller owns the pose/raycast iteration. No captured position, chair,
    or cockpit-specific adjustment is used. Rays run +0.6 to -1.2 extents.
    """
    matrix=np.asarray(model_to_world,float)
    up=matrix[:3,1];up=up/np.linalg.norm(up)
    return [Segment(point(matrix,a)+up*.6*extent,point(matrix,a)-up*1.2*extent) for a in model_ankles]


def pilot_model_transform(cockpit_matrix,native_locator):
    """Scaled cockpit locator translation with full-size pilot orientation."""
    part=np.asarray(cockpit_matrix,float);scale=np.linalg.norm(part[:3,1])
    if scale<=0:raise ValueError('Zero cockpit scale')
    matrix=part.copy();matrix[:3,:3]=part[:3,:3]/scale@np.diag([-1,1,-1])
    matrix[:3,3]=point(part,native_locator)
    return matrix


def exported_transform(obj):
    """Native exported Position/Up/At: Up length is uniform part scale."""
    up=np.asarray(obj['Up'],float);scale=np.linalg.norm(up)
    if not scale>0:raise ValueError('Zero part scale')
    forward=np.asarray(obj['At'],float);forward=forward/np.linalg.norm(forward)
    right=np.cross(up/scale,forward);right=right/np.linalg.norm(right)
    up=np.cross(forward,right)
    matrix=np.eye(4);matrix[:3,:3]=np.column_stack((right,up,forward))*scale
    matrix[:3,3]=obj['Position']
    return matrix


def point(matrix,value):
    return np.asarray(matrix,float)[:3,:3]@np.asarray(value,float)+np.asarray(matrix,float)[:3,3]


def box_intersection(start,end,minimum,maximum):
    start,end,minimum,maximum=map(lambda x:np.asarray(x,float),(start,end,minimum,maximum))
    delta=end-start;enter,leave=0.,1.;normal=None
    for axis in range(3):
        if abs(delta[axis])<1e-14:
            if start[axis]<minimum[axis] or start[axis]>maximum[axis]:return None
            continue
        low=(minimum[axis]-start[axis])/delta[axis];high=(maximum[axis]-start[axis])/delta[axis]
        sign=-1.
        if low>high:low,high=high,low;sign=1.
        if low>enter:
            enter=low;normal=np.eye(3)[axis]*sign
        leave=min(leave,high)
        if enter>leave:return None
    if normal is None:
        # Inside-origin behavior differs across physics engines. Flag it instead
        # of inventing a contact normal or silently treating it as a clean miss.
        return dict(fraction=0.,leave_fraction=leave,normal=None,inside_origin=True)
    return dict(fraction=enter,leave_fraction=leave,normal=normal,inside_origin=False)


def mesh_intersections(start,end,vertices,triangles):
    """Two-sided segment/triangle intersections on native collision triangles."""
    vertices=np.asarray(vertices,float);triangles=np.asarray(triangles,int)
    direction=np.asarray(end,float)-start;hits=[]
    for index,tri in enumerate(triangles):
        a,b,c=vertices[tri];e1=b-a;e2=c-a;p=np.cross(direction,e2);det=float(e1@p)
        if abs(det)<1e-14:continue
        q=np.asarray(start,float)-a;u=float(q@p)/det
        if u<0 or u>1:continue
        cross=np.cross(q,e1);v=float(direction@cross)/det
        if v<0 or u+v>1:continue
        fraction=float(e2@cross)/det
        if fraction<0 or fraction>1:continue
        normal=np.cross(e1,e2);normal/=np.linalg.norm(normal)
        hits.append(dict(fraction=fraction,normal=normal,triangle=index,inside_origin=False))
    return hits


def query_segment(segment,instances,*,admit=None):
    """Return all geometric hits and every unresolved intersecting candidate.

    `instances` supplies native colliders with already accumulated world
    matrices. `admit` is an optional explicit filter; no guessed mask/physics
    semantics are hidden here. Without a filter every native candidate is
    included, which is conservative for proving an empty segment.
    """
    start,end=np.asarray(segment.start,float),np.asarray(segment.end,float)
    hits=[];unresolved=[];excluded=0
    for collider in instances:
        if admit is not None and not admit(collider):continue
        matrix=np.asarray(collider['matrix'],float);inv=np.linalg.inv(matrix)
        local_start,local_end=point(inv,start),point(inv,end)
        shape=collider['shape'];bounds=collider.get('bounds')
        bound_hit=box_intersection(local_start,local_end,*bounds) if bounds is not None else None
        if bounds is not None and bound_hit is None:excluded+=1;continue
        interval=None if bound_hit is None else [(start+(end-start)*f).tolist() for f in (bound_hit['fraction'],bound_hit['leave_fraction'])]
        if shape=='Box':
            half=np.asarray(collider['dimensions'],float)/2
            hit=box_intersection(local_start,local_end,-half,half);local_hits=[] if hit is None else [hit]
        elif shape=='Mesh' and collider.get('geometry_provenance')=='native_collision_hull_indices':
            local_hits=mesh_intersections(local_start,local_end,collider['vertices'],collider['triangles'])
        else:
            unresolved.append(dict(id=collider['id'],shape=shape,position_interval=interval,reason=collider.get('unsupported_reason','Unsupported native shape')));continue
        for hit in local_hits:
            if hit['normal'] is None:
                unresolved.append(dict(id=collider['id'],shape=shape,position_interval=interval,reason='Segment begins inside collision volume'));continue
            normal=inv[:3,:3].T@hit['normal'];normal/=np.linalg.norm(normal)
            hits.append(dict(id=collider['id'],shape=shape,fraction=float(hit['fraction']),
                position=(start+(end-start)*hit['fraction']).tolist(),normal=normal.tolist(),
                part_index=collider.get('part_index'),node=collider.get('node'),triangle=hit.get('triangle')))
    hits.sort(key=lambda h:(h['fraction'],h['id'],h['triangle'] or 0))
    return dict(hits=hits,unresolved=unresolved,bounds_excluded=excluded,
                complete_geometry_query=not unresolved,
                proven_no_geometric_hit=not hits and not unresolved)


def instantiate(catalog,objects,*,extra_roots=None,strict=True):
    placements=[dict(part_id=str(o['ObjectID']).lstrip('^'),matrix=exported_transform(o),part_index=i) for i,o in enumerate(objects)]
    return instantiate_transforms(catalog,placements,extra_roots=extra_roots,strict=strict)


def instantiate_transforms(catalog,placements,*,extra_roots=None,strict=True):
    """Instantiate native-local -> common-world column matrices.

    Supply the complete colliders.json document to retain root-selection
    provenance. Missing IDs raise NativeCollisionError by default. With
    strict=False, pass the returned issues as catalog_issues to the agreement
    query. No placement or alternate exterior roots are added implicitly.
    """
    if not isinstance(catalog,dict) or not catalog:
        raise NativeCollisionError('Native collision catalog is missing or empty')
    roots=catalog.get('root_selection',{})
    parts=catalog.get('catalog',catalog)
    instances=[];missing=[]
    for order,obj in enumerate(placements):
        index=obj.get('part_index',order);part_id=obj['part_id'].lstrip('^')
        keys=[part_id]+list((extra_roots or {}).get(part_id,[]))
        matrix=np.asarray(obj['matrix'],float)
        for key in keys:
            if key not in parts:
                missing.append(dict(part_index=index,part_id=key,reason='Native collision catalog has no entry for this part'));continue
            if matrix.shape!=(4,4) or not np.isfinite(matrix).all() or abs(np.linalg.det(matrix[:3,:3]))<1e-30:
                raise NativeCollisionError(f'Invalid native transform for part {index}:{key}')
            selection=roots.get(key,{})
            for local_index,local in enumerate(parts[key]):
                collider=dict(local);collider['matrix']=(matrix@np.asarray(local['matrix'],float)).tolist()
                collider['part_index']=index;collider['part_id']=key
                collider['id']=f'{index}:{key}:{local_index}:{local["id"]}'
                collider['root_selection']=selection
                instances.append(collider)
    if missing and strict:
        raise NativeCollisionError('Missing native collider definitions: '+', '.join(f"{i['part_index']}:{i['part_id']}" for i in missing))
    return instances,missing


def steady_ray_correction(hit_positions,model_to_world,extent,*,model_y_scale=1.,cap_factor=.2):
    """Decoded steady-state native per-ray clamp/select; no-hit gives zero.

    Caller supplies the admitted native ray hits, not all geometric candidates.
    Their eligibility depends on native physics filters outside this module.
    Native frame-to-frame smoothing is intentionally separate from steady state.
    """
    if not hit_positions:return 0.
    inv=np.linalg.inv(np.asarray(model_to_world,float))
    cap=np.float32(np.float32(extent)*np.float32(cap_factor)/np.float32(model_y_scale))
    values=[np.float32(np.clip(np.float32(point(inv,h)[1]),-cap,cap)) for h in hit_positions]
    return float(min(values,key=abs))

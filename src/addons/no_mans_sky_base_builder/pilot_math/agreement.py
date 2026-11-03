"""Conditional native-geometry prediction with explicit agreement checks.

No application/game/file access. Defaults are derived from native metadata;
runtime activation and category overrides remain explicit conditions. This
module never silently selects a guessed mesh hit-emission implementation.
"""
import numpy as np
from .collisions import query_segment,steady_ray_correction,point
from .filter_rules import initial_component_category,player_ik_body_admitted,select_native_ray_hits


def metadata_admission(collider):
    """Return initial category admission and its unproven runtime conditions."""
    ancestors=collider.get('physics_ancestors',[])
    if not ancestors:return dict(admitted=None,reason='No owning physics attachment resolved',body_key=None)
    owner=ancestors[-1];components=owner['physics']
    if len(components)!=1:return dict(admitted=None,reason='Multiple physics components at attachment',body_key=None)
    component=components[0];category,reason=initial_component_category(component)
    body_key=f"{collider.get('part_index')}:{owner.get('asset')}:{owner['node']}:{owner['entity']}"
    if category is None:return dict(admitted=None,reason=reason,body_key=body_key)
    return dict(admitted=player_ik_body_admitted(0,category),category=category,
        flags54_rejection_bit20=False,body_key=body_key,
        reason='Initial non-trigger metadata category; assumes body remains active with no runtime category override',
        no_player_collide_does_not_exclude_ik=component['fields'].get('NoPlayerCollide')=='true')


def _nearest_groups(hits,key):
    seen=set();result=[]
    for hit in sorted(hits,key=lambda h:h['fraction']):
        value=key(hit)
        if value not in seen:seen.add(value);result.append(hit)
    return result


def _interval_cannot_change(interval,selected,matrix,extent,y_scale):
    if interval is None:return False
    inv=np.linalg.inv(np.asarray(matrix,float))
    cap=float(np.float32(np.float32(extent)*np.float32(.2)/np.float32(y_scale)))
    values=sorted(float(np.clip(point(inv,p)[1],-cap,cap)) for p in interval)
    low,high=values
    minimum_abs=0. if low<=0<=high else min(abs(low),abs(high))
    return minimum_abs>abs(selected)+1e-7 or (abs(low-selected)<=1e-7 and abs(high-selected)<=1e-7)


def conservative_foot_corrections(segments,instances,model_to_world,extent,*,
        model_y_scale=1.,runtime_filters=None,activation=None,root_selection_uncertainties=(),catalog_issues=(),tolerance=1e-7):
    """Return per-leg corrections only when documented alternatives agree.

    `runtime_filters`: optional collider-id -> {flags54,category_info90};
    `activation`: optional collider-id -> bool. Missing entries use metadata
    defaults, reported as conditions, never as observed runtime state.
    Unknown root variants are allowed only when their full catalogued native
    union misses the segment. Intersecting variants block the result. Missing
    catalog entries supplied through catalog_issues block every segment.
    root_selection_uncertainties are unbounded caller issues and also block.
    Hit-emission alternatives: all triangles; first per collision shape.
    Native AllHits compound traversal forwards every child hit, so closest
    per attachment/part is reported only as a non-native counterfactual.
    All use capacity32 and per-leg min-absolute clamped modelY. Agreement is
    limited to these documented shape-emission alternatives.
    """
    instances=list(instances);runtime_filters=runtime_filters or {};activation=activation or {}
    if not np.isfinite(extent) or extent<=0 or not np.isfinite(model_y_scale) or model_y_scale<=0:
        raise ValueError('Native model extent and Y scale must be finite and positive')
    by_id={c['id']:c for c in instances};admissions={};conditions=[]
    for collider in instances:
        key=collider['id'];entry=metadata_admission(collider)
        if key in runtime_filters:
            entry=dict(entry,admitted=player_ik_body_admitted(**runtime_filters[key]),reason='Explicit runtime body filter')
        if activation.get(key) is False:entry=dict(entry,admitted=False,reason='Explicitly inactive')
        admissions[key]=entry
    rays=[]
    for segment in segments:
        query=query_segment(segment,instances,admit=lambda c:admissions[c['id']]['admitted'] is not False)
        hits=query['hits'];unknown=[]
        intersected={row['id'] for row in hits+query['unresolved']}
        root_issues=[dict(id=key,reason='Intersecting native root variant selection is unresolved',selection=by_id[key]['root_selection'])
                     for key in sorted(intersected) if by_id[key].get('root_selection',{}).get('status')=='candidate_union']
        for hit in hits:
            entry=admissions[hit['id']];hit['body_key']=entry['body_key'] or hit['id']
            if entry['admitted'] is None:unknown.append(dict(id=hit['id'],reason=entry['reason']))
            if hit['id'] not in activation or hit['id'] not in runtime_filters:
                conditions.append(dict(id=hit['id'],reason=entry['reason'],activation_observed=hit['id'] in activation))
        alternatives={'all_triangle_hits':hits,'first_per_shape':_nearest_groups(hits,lambda h:h['id'])}
        counterfactuals={
            'first_per_attachment':_nearest_groups(hits,lambda h:h['body_key']),
            'first_per_part':_nearest_groups(hits,lambda h:h.get('part_index',h['id']))}
        values={name:steady_ray_correction([h['position'] for h in select_native_ray_hits(rows)],model_to_world,extent,model_y_scale=model_y_scale)
                for name,rows in alternatives.items()}
        selected=values['all_triangle_hits'];agreement=max(values.values())-min(values.values())<=tolerance
        irrelevant=[];unresolved=[]
        # A bound-only candidate cannot be dismissed if it is the only
        # potential hit, or if its emissions could push the selected known
        # hit beyond the native capacity. Convex primitives have at most two
        # segment/surface crossings; unported arbitrary shapes do not.
        bounded_capacity=len(hits)+2*len(query['unresolved'])<=32 and all(i['shape'] in ('Box','Sphere','Cylinder') for i in query['unresolved'])
        for issue in query['unresolved']:
            if agreement and hits and bounded_capacity and _interval_cannot_change(issue.get('position_interval'),selected,model_to_world,extent,model_y_scale):irrelevant.append(issue)
            else:unresolved.append(issue)
        blocking=unknown+unresolved+root_issues+list(catalog_issues)+list(root_selection_uncertainties)
        if not agreement:blocking.append(dict(reason='Native mesh emission alternatives produce different corrections',values=values))
        counterfactual_values={name:steady_ray_correction([h['position'] for h in select_native_ray_hits(rows)],model_to_world,extent,model_y_scale=model_y_scale) for name,rows in counterfactuals.items()}
        rays.append(dict(correction=selected if not blocking else None,alternatives=values,
            non_native_counterfactual_grouping=counterfactual_values,
            agrees=agreement,blocking=blocking,unresolved_but_proven_irrelevant=irrelevant,
            hit_count=len(hits),selected_counts={name:len(select_native_ray_hits(rows)) for name,rows in alternatives.items()},
            hits=hits,bounds_excluded=query['bounds_excluded']))
    conditions=list({(c['id'],c['reason']):c for c in conditions}.values())
    all_agree=all(ray['correction'] is not None for ray in rays)
    return dict(corrections=[ray['correction'] for ray in rays] if all_agree else None,
        emission_alternatives_agree=all_agree,rays=rays,conditions=conditions,
        root_selection_uncertainties=list(root_selection_uncertainties),catalog_issues=list(catalog_issues),
        runtime_activation_verified=bool(activation) and all(c['id'] in activation for c in instances) and not root_selection_uncertainties,
        scope='Conditional on supplied native roots and initial metadata category/activation; documented emission alternatives only')

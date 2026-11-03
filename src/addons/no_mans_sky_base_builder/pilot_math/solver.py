"""Clean pilot constraint solver accepting named semantic inputs only.

No executable, emulator, process memory, fixture path or binary record decoding
is used by this module. Collision correction values are explicit inputs; the
caller remains responsible for querying supported native collision geometry.
"""
import numpy as np
import copy
from .pose import evaluate_pose,regularization_weights,quaternion_rows,compose_affine
from .linear import assemble_normal_equations,regularize,solve_normal_equations,update_variables
from .constraints import orthonormal_axes,matrix_to_native_rotation_vector,point_and_jacobian,angle_and_jacobian,wrapped_rotation_residual
from .feet import FootSettings,prepare_foot,foot_residual
from .cog import prepare_target,residual_and_jacobian
F=np.float32

def initial_pose(settings):
    """Build unmodified animation globals directly from named native TRS."""
    nodes=settings['nodes'];n=len(nodes);parents=[node['parent'] for node in nodes]
    trs=np.zeros((n,4,4),dtype=F);trs[:,0,3]=1;trs[:,2,3]=1
    for j,node in enumerate(nodes):
        trs[j,0,:3]=node['input_scale'];trs[j,1]=node['input_quaternion_xyzw'];trs[j,2,:3]=node['input_translation']
    return evaluate_pose(trs,parents,np.zeros(3+3*n,dtype=F),np.zeros((n,4),dtype=F),
                         np.repeat(np.eye(3,dtype=F)[None],n,axis=0),[node['dof_offset'] for node in nodes])[:2]

def derive_foot_baselines(settings):
    """Derive sole offsets/targets from native rest rig and current animation.

The rig sole point is the rest ankle projected to native model Y=0, expressed
in the ankle's local frame. The pre-solver animated point becomes the target
and its Y becomes base_height. No ship geometry is consulted here.
"""
    result=copy.deepcopy(settings);_,animated=initial_pose(result)
    for constraint in result['constraints']:
        if constraint['kind']!='foot':continue
        s=constraint['settings'];bone=s['bone'];rest=np.asarray(result['nodes'][bone]['original_global'],dtype=F)
        # The native rig inverse is affine; fourth lanes are implementation data.
        affine=rest.copy();affine[:,3]=[0,0,0,1]
        inverse=np.linalg.inv(affine.astype(np.float64)).astype(F)
        vector=np.array([0,-rest[3,1],0],dtype=F)
        offset=F(F(vector[1]*inverse[1,:3]+vector[0]*inverse[0,:3])+vector[2]*inverse[2,:3])
        matrix=animated[bone]
        target=F(F(F(offset[0]*matrix[0,:3]+offset[1]*matrix[1,:3])+offset[2]*matrix[2,:3])+matrix[3,:3])
        s['local_offset']=np.r_[offset,F(1)].tolist();s['stored_target']=np.r_[target,F(1)].tolist();s['base_height']=float(target[1])
    return result

def solve_pilot(settings,foot_corrections=None,foot_slopes=None):
    """Return local/global matrices and named joint positions in native Y-up.

The bounded cockpit path has unconstrained three-axis joints and no external
tracking or foot glue. Unsupported settings fail explicitly.
"""
    if settings['schema_version']!=1:raise ValueError('Unsupported pilot solver schema')
    solver=settings['solver'];nodes=settings['nodes'];parents=[n['parent'] for n in nodes]
    if any(n['dof_type']!=0 or n['dof_count']!=3 for n in nodes):raise NotImplementedError('Only native three-axis cockpit joints validated')
    if solver['translation_disabled'] or solver['parent_selector']!=0:raise NotImplementedError('Alternate solver root/topology mode not validated')
    n=len(nodes);dimension=int(solver['dof_count'])
    if dimension!=3+3*n:raise ValueError('Unexpected pilot variable count')
    trs=np.zeros((n,4,4),dtype=F);trs[:,0,3]=1;trs[:,2,3]=1
    initial_vectors=[]
    for j,node in enumerate(nodes):
        trs[j,0,:3]=node['input_scale'];trs[j,1]=node['input_quaternion_xyzw'];trs[j,2,:3]=node['input_translation']
        matrix=np.eye(4,dtype=F);matrix[:3,:3]=quaternion_rows(trs[j,1]);matrix[:3,:3]=orthonormal_axes(matrix)
        initial_vectors.append(matrix_to_native_rotation_vector(compose_affine(matrix,np.asarray(node['inverse_bind_local'],dtype=F))))
    initial_vectors=np.array(initial_vectors,dtype=F)
    offsets=[node['dof_offset'] for node in nodes]
    zeros=np.zeros(dimension,dtype=F);identity_axes=np.repeat(np.eye(3,dtype=F)[None],n,axis=0)
    initial_local,initial_global,_=evaluate_pose(trs,parents,zeros,initial_vectors,identity_axes,offsets)
    axes=np.array([orthonormal_axes(m) for m in initial_global],dtype=F)
    _,_,initial_angles=evaluate_pose(trs,parents,zeros,initial_vectors,axes,offsets)
    masses=np.array([node['mass'] for node in nodes],dtype=F);rigidity=np.array([node['rigidity'] for node in nodes],dtype=F)
    scale=F(solver['position_scale'])
    weights=regularization_weights(masses,rigidity,scale,solver['stiffness_scale'],solver['stiffness_floor'])
    active=[c for c in settings['constraints'] if c['enabled']]
    foot_inputs=[c['settings'] for c in active if c['kind']=='foot']
    corrections=np.array(foot_corrections if foot_corrections is not None else [s['ray_correction'] for s in foot_inputs],dtype=F)
    slopes=np.array(foot_slopes if foot_slopes is not None else [s['slope_degrees'] for s in foot_inputs],dtype=F)
    if len(corrections)!=len(foot_inputs) or len(slopes)!=len(foot_inputs):raise ValueError('One correction/slope required per active foot')
    mean=F(0)
    for value in corrections:mean=F(mean+value)
    if len(corrections):mean=F(mean/F(len(corrections)))
    constraints=[];foot_index=0
    for constraint in active:
        kind=constraint['kind'];s=dict(constraint['settings']);strength=F(constraint['strength'])
        if kind=='foot':
            bone=s['bone'];rotation_weight=s.pop('rotation_weight',constraint.get('rotation_weight'))
            if rotation_weight is None:raise ValueError('Foot rotation weight required')
            s['ray_correction']=corrections[foot_index];s['slope_degrees']=slopes[foot_index];foot_index+=1
            foot=prepare_foot(FootSettings(**s),nodes[bone]['original_global'],nodes[bone]['working_global'],initial_global,initial_angles,parents)
            constraints.append((kind,strength,dict(bone=bone,offset=foot['local_offset'][:3],target=foot['target'],rotation=foot['rotation'],rotation_weight=rotation_weight)))
        elif kind=='head':
            bone=s['bone'];node=nodes[bone]
            target=F(np.asarray(s['position_reference'],dtype=F)-np.asarray(node['original_global'],dtype=F)[3])
            target=F(target+np.asarray(node['working_global'],dtype=F)[3])
            correction=mean if s.get('mean_foot_correction') else F(s['height_correction'])
            target[1]=F(target[1]+correction)
            constraints.append((kind,strength,dict(s,target_position=target,target_rotation=F(initial_angles[bone]+np.asarray(s['rotation_offset'],dtype=F)))))
        elif kind=='cog':
            offset=np.array(s['offset'],dtype=F)
            if s.get('mean_foot_correction'):offset[1]=mean
            constraints.append((kind,strength,prepare_target(initial_global,masses,offset)))
        else:raise NotImplementedError('Unsupported active constraint '+kind)
    variables=zeros.copy();factor=F(solver['initial_step']);iterations=float(solver['iterations'])
    if not iterations.is_integer():raise NotImplementedError('Fractional iteration count not validated')
    for _ in range(int(iterations)):
        local,global_pose,angles=evaluate_pose(trs,parents,variables,initial_vectors,axes,offsets)
        rows=[]
        for kind,strength,c in constraints:
            if kind=='foot':
                point,pj=point_and_jacobian(nodes,global_pose,c['bone'],c['offset'],dimension)
                angle,aj=angle_and_jacobian(nodes,global_pose,c['bone'],angles,dimension)
                residual,jac=foot_residual(point,angle,pj,aj,c['target'],c['rotation'],scale,c['rotation_weight'])
            elif kind=='head':
                residual=np.zeros(4,dtype=F);jac=np.zeros((4,dimension),dtype=F);bone=c['bone']
                if c['rotation_enabled']:
                    angle,aj=angle_and_jacobian(nodes,global_pose,bone,angles,dimension)
                    weight=F(np.asarray(c['axis_weights'],dtype=F)*F(c['rotation_weight']))
                    residual[:3]=F(wrapped_rotation_residual(angle,c['target_rotation'][:3])*weight);jac[:3]=F(aj*weight[:,None])
                if c['height_enabled']:
                    point,pj=point_and_jacobian(nodes,global_pose,bone,ndof=dimension)
                    residual[3]=F(F(F(point[1]-c['target_position'][1])*scale)*F(c['height_weight']))
                    jac[3]=F(F(pj[1]*scale)*F(c['height_weight']))
            else:
                pjs=np.array([point_and_jacobian(nodes,global_pose,j,ndof=dimension)[1] for j in range(n)],dtype=F)
                residual,jac=residual_and_jacobian(global_pose,masses,c,scale,pjs)
            rows.append((strength,residual,jac))
        h,b=assemble_normal_equations(rows,dimension);h,b=regularize(h,b,variables,weights)
        step,_=solve_normal_equations(h,b);variables=update_variables(variables,step,factor);factor=F(factor*F(solver['step_decay']))
    local,global_pose,angles=evaluate_pose(trs,parents,variables,initial_vectors,axes,offsets)
    return {'names':[node['name'] for node in nodes],'native_indices':[node['native_index'] for node in nodes],
            'local_matrices':local,'global_matrices':global_pose,'variables':variables,
            'positions':{node['name']:global_pose[j,3,:3].copy() for j,node in enumerate(nodes)}}

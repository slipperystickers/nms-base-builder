"""Binary-independent native row-matrix FK and additive solver coordinates."""
import math
import numpy as np
F=np.float32

def quat_multiply(a,b):
    x,y,z,w=np.asarray(a,dtype=F);X,Y,Z,W=np.asarray(b,dtype=F)
    return np.array([F(F(F(y*Z-z*Y)+w*X)+x*W),
                     F(F(F(z*X-x*Z)+w*Y)+y*W),
                     F(F(F(x*Y-y*X)+w*Z)+z*W),
                     F(w*W-F(F(y*Y+x*X)+z*Z))],dtype=F)

def delta_quaternion(vector):
    v=np.asarray(vector,dtype=F);squared=F(F(v[1]*v[1]+v[0]*v[0])+v[2]*v[2])
    if squared<F(2.3283064365386963e-10):return np.array([0,0,0,1],dtype=F)
    length=F(np.sqrt(squared));unit=v*F(F(1)/length);half=F(length*F(.5))
    return np.r_[unit*F(math.sin(float(half))),F(math.cos(float(half)))].astype(F)

def quaternion_rows(q):
    x,y,z,w=np.asarray(q,dtype=F);xx=F(x*F(x+x));yy=F(y*F(y+y));zz=F(z*F(z+z))
    xy=F(x*F(y+y));xz=F(x*F(z+z));yz=F(y*F(z+z))
    wx=F(w*F(x+x));wy=F(w*F(y+y));wz=F(w*F(z+z))
    return np.array([[F(1)-F(zz+yy),F(wz+xy),F(xz-wy)],
                     [F(xy-wz),F(1)-F(zz+xx),F(wx+yz)],
                     [F(wy+xz),F(yz-wx),F(1)-F(yy+xx)]],dtype=F)

def compose_affine(local,parent):
    out=F(F(local[:,0,None]*parent[0])+F(local[:,1,None]*parent[1]))
    out=F(out+F(local[:,2,None]*parent[2]));out[3]=F(out[3]+parent[3])
    return out

def forward_kinematics(local,parents):
    result=np.empty_like(local)
    for i,parent in enumerate(parents):result[i]=local[i] if parent<0 else compose_affine(local[i],result[parent])
    return result

def evaluate_pose(trs,parents,variables,initial_local_vectors,initial_global_axes,dof_offsets=None):
    trs=np.asarray(trs,dtype=F).reshape(-1,4,4);n=len(trs)
    theta=np.asarray(variables,dtype=F)
    if dof_offsets is None:dof_offsets=np.arange(n)*3+3
    local=np.zeros((n,4,4),dtype=F);local[:,3,3]=1
    current_vectors=np.zeros((n,4),dtype=F)
    for i,parent in enumerate(parents):
        delta=theta[dof_offsets[i]:dof_offsets[i]+3]
        quaternion=quat_multiply(trs[i,1],delta_quaternion(delta))
        rotation=quaternion_rows(quaternion)
        local[i,:3,:3]=rotation*trs[i,0,:3,None]
        if parent>=0:local[i,:3,:3]=F(local[i,:3,:3]/trs[parent,0,:3])
        local[i,3,:3]=trs[i,2,:3]
        if parent<0:local[i,3,:3]=F(local[i,3,:3]+theta[:3])
        v=F(initial_local_vectors[i,:3]+delta);axes=initial_global_axes[i]
        current_vectors[i,:3]=F(F(v[1]*axes[1]+v[0]*axes[0])+v[2]*axes[2])
        if parent>=0:current_vectors[i,:3]=F(current_vectors[i,:3]+current_vectors[parent,:3])
    return local,forward_kinematics(local,parents),current_vectors

def regularization_weights(masses,rigidity,position_scale,stiffness,minimum):
    base=F(np.asarray(masses,dtype=F)+np.asarray(rigidity,dtype=F))
    weights=np.r_[np.repeat(F(base[0]*F(position_scale)),3),np.repeat(base,3)].astype(F)
    factor=F(F(1)/weights[0]);return F(F(F(weights*factor)*F(stiffness))+F(minimum))

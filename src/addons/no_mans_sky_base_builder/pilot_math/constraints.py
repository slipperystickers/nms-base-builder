"""Explicit native constraint equations, independently tested against saved callbacks.

No game process, executable, emulator, Blender, or scene mutation is used here.
Matrices use native row-vector storage. Supported scope: unrestricted
joint chains, positive nonzero scales (zero-axis cases handled), native DOF
types 0..7. Restriction-list attenuation is deliberately not guessed.
"""
import numpy as np

F=np.float32
DOF_AXES={0:(0,1,2),1:(0,),2:(1,),3:(2,),4:(0,1),5:(0,2),6:(1,2),7:()}
PI_SQUARED=F(9.86960506439209)
TWO_PI=F(6.2831854820251465)

def norm2(v):
 v=np.asarray(v,dtype=F);q=v*v
 return F(F(q[0]+q[1])+q[2])
def unit(v):
 v=np.asarray(v,dtype=F);length=F(np.sqrt(norm2(v)))
 return v if length==0 else v*F(F(1)/length)
def orthonormal_axes(matrix):
 """Native basis extraction: normalize rows and retain the least parallel pair."""
 x,y,z=[unit(v[:3]) for v in np.asarray(matrix,dtype=F)[:3]]
 lengths=[norm2(v) for v in (x,y,z)]
 if not any(lengths):return np.eye(3,dtype=F)
 if not lengths[0]:
  x=unit(np.cross(y,z));z=unit(np.cross(x,y))
 elif not lengths[1]:
  y=unit(np.cross(z,x));x=unit(np.cross(y,z))
 elif not lengths[2]:
  z=unit(np.cross(x,y));y=unit(np.cross(z,x))
 else:
  yz=abs(F(np.dot(y,z)));xz=abs(F(np.dot(x,z)));xy=abs(F(np.dot(x,y)))
  if xz>yz and xy>yz:
   x=unit(np.cross(y,z));z=unit(np.cross(x,y))
  elif xz<=yz and xy>xz:
   y=unit(np.cross(z,x));x=unit(np.cross(y,z))
  else:
   z=unit(np.cross(x,y));y=unit(np.cross(z,x))
 return np.array([x,y,z],dtype=F)


def chain(nodes,index):
 seen=set()
 while index>=0:
  if index in seen:raise ValueError('Cyclic solver chain')
  seen.add(index);yield index;index=nodes[index]['parent']

def point_and_jacobian(nodes,global_pose,index,point=(0,0,0),ndof=72,
                       fixed_translation=False,restrictions=None):
 """Native transformed point and 3xN spatial point Jacobian (142ce7aa0 Y row).

For 142cebf90 add mass*value and mass*Jacobian to the accumulators. For the
first three rows of 142ce6560 use the value/Jacobian directly.
"""
 if restrictions:raise NotImplementedError('Native restriction-list weighting is not ported')
 pose=np.asarray(global_pose,dtype=F);p=np.asarray(point,dtype=F)
 value=F(p[0]*pose[index,0,:3])+F(p[1]*pose[index,1,:3])
 value=F(value+F(p[2]*pose[index,2,:3]));value=F(value+pose[index,3,:3])
 jac=np.zeros((3,ndof),dtype=F)
 if not fixed_translation:jac[:,:3]=np.eye(3,dtype=F)
 for j in chain(nodes,index):
  n=nodes[j];axes=orthonormal_axes(pose[j]);lever=F(value-pose[j,3,:3])
  for k,axis in enumerate(DOF_AXES[n['dof_type']]):
   jac[:,n['dof_offset']+k]=np.cross(unit(axes[axis]),lever)
 return value,jac

def angle_and_jacobian(nodes,global_pose,index,rotation_vectors,ndof=72,restrictions=None):
 """Native orientation-coordinate value and spatial angular Jacobian.

Native142ce8850 uses the provided rotation-coordinate array unchanged and
spatial axes for its linearization, not an exact logarithm-map derivative.
"""
 if restrictions:raise NotImplementedError('Native restriction-list weighting is not ported')
 value=np.asarray(rotation_vectors,dtype=F)[index,:3].copy()
 jac=np.zeros((3,ndof),dtype=F)
 for j in chain(nodes,index):
  n=nodes[j];axes=orthonormal_axes(global_pose[j])
  for k,axis in enumerate(DOF_AXES[n['dof_type']]):jac[:,n['dof_offset']+k]=axes[axis]
 return value,jac

def wrapped_rotation_residual(value,target):
 value=np.asarray(value,dtype=F).copy();target=np.asarray(target,dtype=F)
 if norm2(value)!=0:
  delta=F(target-value)
  for _ in range(100):
   if norm2(delta)<=PI_SQUARED:break
   value=F(value+F(unit(delta)*TWO_PI));delta=F(target-value)
  else:raise ValueError('Native rotation wrap did not converge')
 return F(value-target)




def matrix_to_native_rotation_vector(matrix):
 """142ce5df0 / 1411438e0: basis repair, native quaternion branch and acos.

Returns the native four-lane vector (XYZ rotation vector; W is SIMD baggage).
This intentionally preserves the game's float32 polynomial and threshold,
including its non-shortest branch when quaternion W is negative.
"""
 m=orthonormal_axes(matrix);a,b,c=m[0,0],m[1,1],m[2,2]
 if c<0:
  if a>b:
   t=F(F(F(a+F(1))-b)-c)
   q=np.array([t,F(m[1,0]+m[0,1]),F(m[0,2]+m[2,0]),F(m[1,2]-m[2,1])],dtype=F)
  else:
   t=F(F(F(F(1)-a)+b)-c)
   q=np.array([F(m[1,0]+m[0,1]),t,F(m[1,2]+m[2,1]),F(m[2,0]-m[0,2])],dtype=F)
 else:
  if F(-b)>a:
   t=F(F(F(F(1)-a)-b)+c)
   q=np.array([F(m[0,2]+m[2,0]),F(m[1,2]+m[2,1]),t,F(m[0,1]-m[1,0])],dtype=F)
  else:
   t=F(F(F(a+F(1))+b)+c)
   q=np.array([F(m[1,2]-m[2,1]),F(m[2,0]-m[0,2]),F(m[0,1]-m[1,0]),t],dtype=F)
 q=F(q*F(F(.5)/F(np.sqrt(t))))
 w=F(min(F(1),max(F(-1),q[3])));x=F(abs(w))
 coefficients=[.0007179649546742439,-.004116097930818796,.011272900737822056,
  -.02094927802681923,.03268376365303993,-.050625279545784,
  .08903469890356064,-.21460144221782684,1.5707963705062866]
 poly=F(coefficients[0])
 for value in coefficients[1:]:poly=F(F(poly*x)+F(value))
 acos=F(F(np.sqrt(F(F(1)-x)))*poly)
 if w<0:acos=F(F(3.1415927410125732)-acos)
 angle=F(acos+acos);q[3]=F(1)
 limit=F(2.3283064365386963e-10)
 if norm2(q)<limit:axis=np.array([0,1,0,1],dtype=F)
 else:axis=F(q*F(F(1)/F(np.sqrt(norm2(q)))))
 if norm2(axis)<limit:return np.array([0,0,0,1],dtype=F)
 axis=F(axis*F(F(1)/F(np.sqrt(norm2(axis)))))
 return F(axis*angle)

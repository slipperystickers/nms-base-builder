"""Read-only surface picking with an explicit preview/accept step."""
import math
import time
from dataclasses import dataclass
from collections import defaultdict
import bpy
import gpu
from bpy.app.handlers import persistent
from gpu_extras.batch import batch_for_shader
from bpy_extras import view3d_utils as view
from mathutils import Vector
from mathutils.bvhtree import BVHTree

_sessions = []
# A single read-only snapshot survives successive traces on the same mesh.
# Geometry edits and file changes evict it; transforms are part of the key.
_surface_snapshot = {}


class Surface:
    def __init__(self, mesh, matrix):
        for _ in self.build_steps(mesh, matrix): pass

    def build_steps(self, mesh, matrix):
        # Weld coincident UV/material seam vertices in the snapshot only.
        self.vertices = []
        weld = {}; remap = {}
        for v in mesh.vertices:
            co = matrix @ v.co
            key = tuple(round(x, 6) for x in co)
            if key not in weld:
                weld[key] = len(self.vertices); self.vertices.append(co)
            remap[v.index] = weld[key]
            if v.index % 256 == 0: yield f'Preparing vertices: {v.index:,} / {len(mesh.vertices):,}'
        self.faces = []; self.edges = defaultdict(set); self.face_edges = []
        for face in mesh.polygons:
            ids = [remap[i] for i in face.vertices]
            self.faces.append(ids)
            edges = {tuple(sorted((a, b))) for a, b in zip(ids, ids[1:]+ids[:1]) if a != b}
            self.face_edges.append(edges)
            for edge in edges: self.edges[edge].add(face.index)
            if face.index % 256 == 0: yield f'Preparing faces: {face.index:,} / {len(mesh.polygons):,}'
        normal_matrix = matrix.to_3x3().inverted_safe().transposed()
        self.normals = []
        for p in mesh.polygons:
            self.normals.append((normal_matrix @ p.normal).normalized())
            if p.index % 256 == 0: yield f'Preparing normals: {p.index:,} / {len(mesh.polygons):,}'
        self.patches = {}

    def patch(self, face):
        """Connected surface facets up to a meaningful change in direction."""
        for _ in self.patch_steps(face): pass
        return self.patches[face]

    def patch_steps(self, face):
        if face in self.patches: return self.patches[face]
        normal = self.normals[face]
        local_limit=math.cos(math.radians(50))
        seed_limit=math.cos(math.radians(60))
        found = {face}; pending = [face]
        count = 0
        while pending:
            current = pending.pop()
            for edge in self.face_edges[current]:
                for other in self.edges[edge] - found:
                    if other in self.patches:continue
                    # Follow small facets, but stop at a real crease or when a
                    # curved sheet has turned away from the clicked side.
                    if self.normals[current].dot(self.normals[other]) < local_limit: continue
                    if normal.dot(self.normals[other]) < seed_limit: continue
                    found.add(other); pending.append(other)
            count += 1
            if count % 256 == 0: yield f'Finding flat outline: {count:,} faces'
        result = frozenset(found)
        for count, index in enumerate(found):
            self.patches[index] = result
            if count % 256 == 0: yield f'Caching flat outline: {count:,} faces'

    def boundary(self, faces):
        counts = defaultdict(int)
        for face in faces:
            for edge in self.face_edges[face]: counts[edge] += 1
        return {edge for edge, count in counts.items() if count == 1}

    def patch_faces(self, face):
        return self.patches[face]

    def same_patch(self, face, other):
        return other in self.patches[face]

    def boundary_segments(self, faces):
        return {segment(self.vertices[a], self.vertices[b]) for a,b in self.boundary(faces)}

    def edge_chain(self, edge, max_turn=35, allowed=None):
        """Continue through the most aligned edge at each end, stopping at corners."""
        neighbors = defaultdict(set)
        if allowed is None:
            allowed = set()
            for candidate, faces in self.edges.items():
                if len(faces)==1:
                    allowed.add(candidate)
                elif len(faces)==2:
                    a,b=tuple(faces)
                    if self.normals[a].dot(self.normals[b])<math.cos(math.radians(35)):
                        allowed.add(candidate)
        for a, b in allowed:
            neighbors[a].add(b); neighbors[b].add(a)
        a, b = edge
        chain = {tuple(sorted(edge))}
        def walk(previous, current):
            heading=(self.vertices[current]-self.vertices[previous]).normalized()
            while True:
                incoming = (self.vertices[current]-self.vertices[previous]).normalized()
                choices = []
                for next_vertex in neighbors[current] - {previous}:
                    candidate = tuple(sorted((current, next_vertex)))
                    if candidate in chain: continue
                    outgoing = (self.vertices[next_vertex]-self.vertices[current]).normalized()
                    if outgoing.dot(heading)<math.cos(math.radians(70)):continue
                    turn = incoming.angle(outgoing)
                    if turn <= math.radians(max_turn): choices.append((turn, candidate, next_vertex))
                if not choices: break
                _, candidate, next_vertex = min(choices)
                chain.add(candidate); previous, current = current, next_vertex
        walk(a,b); walk(b,a)
        return chain

    def edge_chain_at(self, face, location, xy, region, region_data, scale):
        features=list(self.boundary(self.patch_faces(face)))
        best=None;distance=36*max(.75,scale)
        for edge in features:
            a,b=(self.vertices[i] for i in edge)
            pa=view.location_3d_to_region_2d(region,region_data,a)
            pb=view.location_3d_to_region_2d(region,region_data,b)
            if pa is None or pb is None:continue
            delta=pb-pa;t=max(0.,min(1.,(xy-pa).dot(delta)/max(delta.length_squared,1e-12)))
            d=(xy-pa-delta*t).length
            if d<distance:distance=d;best=edge
        if best is None:return frozenset()
        return frozenset(segment(self.vertices[a],self.vertices[b])
                         for a,b in self.edge_chain(best,allowed=set(features)))

    def guide(self, faces, angle=0., hint=None):
        """A straight directional guide projected onto the selected surface."""
        ids = {i for face in faces for i in self.faces[face]}
        points = [self.vertices[i] for i in ids]
        center = sum(points, Vector()) / len(points)
        normal = sum((self.normals[i] for i in faces), Vector()).normalized()
        if normal.length_squared < 1e-8: normal = self.normals[next(iter(faces))]
        u = normal.orthogonal().normalized(); v = normal.cross(u).normalized()
        xx = sum((p-center).dot(u)**2 for p in points)
        yy = sum((p-center).dot(v)**2 for p in points)
        xy = sum((p-center).dot(u)*(p-center).dot(v) for p in points)
        theta = .5*math.atan2(2*xy, xx-yy)
        direction = (u*math.cos(theta)+v*math.sin(theta)).normalized()
        if hint is not None and hint.length_squared > 1e-10:
            direction = (hint-normal*hint.dot(normal)).normalized()
        direction = direction*math.cos(angle)+normal.cross(direction)*math.sin(angle)
        extent = [(p-center).dot(direction) for p in points]
        lo, hi = min(extent), max(extent)
        if not hasattr(self,'guide_trees'):self.guide_trees={}
        if not hasattr(self,'guide_meta'):self.guide_meta={}
        tree_key = min(faces)
        if tree_key not in self.guide_trees:
            self.guide_trees[tree_key] = BVHTree.FromPolygons(self.vertices, [self.faces[i] for i in faces], all_triangles=False)
        tree = self.guide_trees[tree_key]
        self.guide_meta[tree_key]=(center,normal,max((p-center).length for p in points)*.22)
        if hint is None and abs(angle)<1e-8:
            from .curve_surface_centerline import centerline
            if not hasattr(self,'center_paths'):self.center_paths={}
            if tree_key not in self.center_paths:
                self.center_paths[tree_key]=centerline(
                    [(self.vertices[a],self.vertices[b]) for a,b in self.boundary(faces)],center,normal,direction)
            path=[tree.find_nearest(p)[0] for p in self.center_paths[tree_key]]
            if len(path)>1:return path,center,normal
        count = max(2, min(96, math.ceil((hi-lo)/max((hi-lo)/80, 1e-5))))
        depth = max((max(points,key=lambda p:(p-center).length)-center).length*3, 1.)
        result = []
        for j in range(count+1):
            target = center+direction*(lo+(hi-lo)*j/count)
            projected = tree.ray_cast(target+normal*depth,-normal,depth*2)[0]
            if projected is None:projected = tree.find_nearest(target)[0]
            if projected is not None and (not result or (projected-result[-1]).length>1e-5):
                result.append(projected)
        return result, center, normal


class DenseSurface:
    """Vectorized topology for large triangulated meshes; one snapshot per object."""
    def __init__(self, mesh, matrix, obj):
        for _ in self.build_steps(mesh, matrix, obj): pass

    def build_steps(self, mesh, matrix, obj):
        import numpy as np
        self.np = np; self.obj = obj; self.matrix = matrix.copy()
        self.inverse = matrix.inverted_safe()
        faces = len(mesh.polygons); loops = len(mesh.loops); edges = len(mesh.edges)
        starts = np.empty(faces, dtype=np.int32)
        totals = np.empty(faces, dtype=np.int32)
        mesh.polygons.foreach_get('loop_start', starts)
        mesh.polygons.foreach_get('loop_total', totals)
        if not np.all(totals == 3):
            raise ValueError('Dense topology requires triangles')
        yield 'Reading mesh topology...'
        loop_edges = np.empty(loops, dtype=np.int32)
        loop_vertices = np.empty(loops, dtype=np.int32)
        mesh.loops.foreach_get('edge_index', loop_edges)
        yield 'Reading mesh vertices...'
        mesh.loops.foreach_get('vertex_index', loop_vertices)
        self.face_edges_np = loop_edges.reshape(-1, 3)
        self.face_vertices_np = loop_vertices.reshape(-1, 3)
        coords = np.empty(len(mesh.vertices)*3, dtype=np.float32)
        mesh.vertices.foreach_get('co', coords)
        local = coords.reshape(-1,3)
        world = np.asarray(matrix, dtype=np.float64)
        self.coords = local @ world[:3,:3].T + world[:3,3]
        self.diagonal=float(np.linalg.norm(self.coords.max(axis=0)-self.coords.min(axis=0)))
        yield 'Finding neighboring facets...'
        order = np.argsort(loop_edges, kind='stable').astype(np.int32)
        counts=np.bincount(loop_edges,minlength=edges)
        offsets=np.empty(edges+1,dtype=np.int32)
        offsets[0]=0;np.cumsum(counts,out=offsets[1:])
        paired=np.flatnonzero(counts==2)
        left=order[offsets[paired]];right=order[offsets[paired]+1]
        owner = np.repeat(np.arange(faces,dtype=np.int32),3)
        other = np.full(loops,-1,dtype=np.int32)
        other[left]=owner[right]
        other[right]=owner[left]
        self.neighbors = other.reshape(-1,3)
        self.edge_vertices = np.empty((edges,2),dtype=np.int32)
        mesh.edges.foreach_get('vertices',self.edge_vertices.ravel())
        yield 'Reading facet directions...'
        normals = np.empty(faces*3,dtype=np.float32)
        mesh.polygons.foreach_get('normal',normals)
        normal_matrix = np.asarray(matrix.to_3x3().inverted_safe().transposed(),dtype=np.float64)
        self.normals_np = normals.reshape(-1,3) @ normal_matrix.T
        lengths = np.linalg.norm(self.normals_np,axis=1)
        self.normals_np /= np.maximum(lengths[:,None],1e-12)
        self.patch_labels = np.full(faces,-1,dtype=np.int32)
        self.patches = {}; self.guide_data = {}; self.guide_meta = {}
        self.boundary_cache = {};self.boundary_graph = {}
        yield f'Ready: {faces:,} facets'

    def patch_steps(self, face, seed_override=None):
        np = self.np
        label = int(self.patch_labels[face])
        if label >= 0: return self.patches[label]
        seed = self.normals_np[face] if seed_override is None else seed_override
        visited = np.zeros(len(self.neighbors),dtype=np.bool_)
        visited[face] = True
        frontier = np.array([face],dtype=np.int32)
        rounds = 0
        local_limit = math.cos(math.radians(50))
        seed_limit = math.cos(math.radians(60 if seed_override is None else 45))
        while frontier.size:
            candidates = self.neighbors[frontier].ravel()
            parents = np.repeat(frontier,3)
            connected=candidates>=0
            candidates=candidates[connected];parents=parents[connected]
            unseen = ~visited[candidates] & (self.patch_labels[candidates]<0)
            candidates = candidates[unseen]; parents = parents[unseen]
            if candidates.size:
                local = np.einsum('ij,ij->i',self.normals_np[candidates],self.normals_np[parents])
                global_angle = self.normals_np[candidates] @ seed
                candidates = np.unique(candidates[(local >= local_limit) & (global_angle >= seed_limit)])
                visited[candidates] = True
                frontier = candidates
            else: frontier = np.empty(0,dtype=np.int32)
            rounds += 1
            if rounds % 16 == 0: yield f'Grouping surface: {int(visited.sum()):,} facets'
        patch = np.flatnonzero(visited).astype(np.int32)
        if seed_override is None and len(patch)>32:
            # Rounded lips can connect two broad surfaces even though neither
            # belongs to the other's patch. Cluster the provisional normals,
            # then anchor the flood to the broad side closest to the click.
            sample_ids=patch[::max(1,len(patch)//4096)]
            sample=self.normals_np[sample_ids]
            triangles=self.coords[self.face_vertices_np[sample_ids]]
            weights=np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]),axis=1)
            centers=np.array([seed,sample[np.argmin(sample@seed)]])
            for _ in range(8):
                groups=np.argmax(sample@centers.T,axis=1)
                if not np.any(groups==0) or not np.any(groups==1):break
                centers=np.array([np.average(sample[groups==i],axis=0,weights=np.maximum(weights[groups==i],1e-12)) for i in (0,1)])
                centers/=np.maximum(np.linalg.norm(centers,axis=1)[:,None],1e-12)
            proportion=float(np.mean(groups==0))
            if .1<proportion<.9 and centers[0]@centers[1]<math.cos(math.radians(50)):
                anchor=centers[np.argmax(centers@seed)]
                return (yield from self.patch_steps(face,anchor))
        self.patch_labels[patch] = face
        self.patches[face] = patch
        return patch

    def patch(self, face):
        job=self.patch_steps(face)
        while True:
            try:next(job)
            except StopIteration as result:return result.value

    def patch_faces(self, face):
        return self.patches[int(self.patch_labels[face])]

    def same_patch(self, face, other):
        return self.patch_labels[face] == self.patch_labels[other]

    def boundary_ids(self, faces):
        np = self.np
        label=int(self.patch_labels[faces[0]])
        if label not in self.boundary_cache:
            counts=np.bincount(self.face_edges_np[faces].ravel(),minlength=len(self.edge_vertices))
            self.boundary_cache[label]=np.flatnonzero(counts==1).astype(np.int32)
        return self.boundary_cache[label]

    def boundary_segments(self, faces):
        vertices = self.edge_vertices[self.boundary_ids(faces)]
        return {segment(self.coords[a],self.coords[b]) for a,b in vertices}

    def _guide_frame(self, faces):
        np = self.np
        label = int(self.patch_labels[faces[0]])
        if label not in self.guide_data:
            # Direction/extents depend on the outline, not the millions of
            # interior tessellation vertices. Reuse the cached boundary.
            vertices = np.unique(self.edge_vertices[self.boundary_ids(faces)].ravel())
            if not len(vertices):vertices=np.unique(self.face_vertices_np[faces[::max(1,len(faces)//4096)]].ravel())
            points = self.coords[vertices]
            center = points.mean(axis=0)
            normal = self.normals_np[faces].mean(axis=0)
            normal /= max(np.linalg.norm(normal),1e-12)
            u = Vector(normal).orthogonal().normalized()
            u = np.asarray(u); v = np.cross(normal,u)
            offsets = points-center
            xy = np.column_stack((offsets @ u,offsets @ v))
            values,vectors = np.linalg.eigh(xy.T @ xy)
            direction = u*vectors[0,1]+v*vectors[1,1]
            radius = float(np.linalg.norm(offsets,axis=1).max()*.22)
            self.guide_data[label] = (points,center,normal,direction,radius)
        return self.guide_data[label]

    def guide(self, faces, angle=0., hint=None):
        np = self.np
        points,center,normal,base,radius = self._guide_frame(faces)
        direction = base
        if hint is not None and hint.length_squared > 1e-10:
            direction = np.asarray(hint,dtype=np.float64)
            direction -= normal*np.dot(direction,normal)
            direction /= max(np.linalg.norm(direction),1e-12)
        direction = direction*math.cos(angle)+np.cross(normal,direction)*math.sin(angle)
        extent = (points-center) @ direction
        lo,hi = float(extent.min()),float(extent.max())
        depth = max(radius*15,1.)
        label = int(self.patch_labels[faces[0]])
        self.guide_meta[label] = (Vector(center),Vector(normal),radius)
        targets=[Vector(center+direction*(lo+(hi-lo)*j/80)) for j in range(81)]
        if hint is None and abs(angle)<1e-8:
            from .curve_surface_centerline import centerline
            if not hasattr(self,'center_paths'):self.center_paths={}
            if label not in self.center_paths:
                self.center_paths[label]=centerline(self.coords[self.edge_vertices[self.boundary_ids(faces)]],center,normal,base)
            if len(self.center_paths[label])>1:targets=self.center_paths[label]
        result = []
        for target in targets:
            target=np.asarray(target)
            origin = Vector(target+normal*depth)
            local_origin = self.inverse @ origin
            local_direction = (self.inverse.to_3x3() @ Vector(-normal)).normalized()
            found,co,n,face = self.obj.ray_cast(local_origin,local_direction)
            if found and self.patch_labels[face] == label:
                world = self.matrix @ co
                if not result or (world-result[-1]).length>1e-5:result.append(world)
        return result,Vector(center),Vector(normal)

    def edge_chain_at(self, face, location, xy, region, region_data, scale):
        np = self.np
        label=int(self.patch_labels[face])
        boundary=self.boundary_ids(self.patch_faces(face))
        if not len(boundary):return frozenset()
        vertices=self.edge_vertices[boundary]
        midpoints=(self.coords[vertices[:,0]]+self.coords[vertices[:,1]])*.5
        distance = np.linalg.norm(midpoints-np.asarray(location),axis=1)
        candidates = np.argpartition(distance,min(128,len(distance)-1))[:128]
        best = None; best_distance = 36*max(.75,scale)
        for candidate in candidates:
            a,b = vertices[candidate]
            pa = view.location_3d_to_region_2d(region,region_data,Vector(self.coords[a]))
            pb = view.location_3d_to_region_2d(region,region_data,Vector(self.coords[b]))
            if pa is None or pb is None:continue
            delta=pb-pa;t=max(0.,min(1.,(xy-pa).dot(delta)/max(delta.length_squared,1e-12)))
            d=(xy-pa-delta*t).length
            if d<best_distance:best_distance=d;best=int(candidate)
        if best is None:return frozenset()
        cached=getattr(self,'last_edge_preview',None)
        if cached and cached[0]==label and best in cached[1]:return cached[2]
        chain=self.boundary_chain(label,best)
        edges=frozenset(segment(self.coords[a],self.coords[b]) for a,b in vertices[list(chain)])
        self.last_edge_preview=(label,chain,edges)
        return edges

    def boundary_chain(self, label, start):
        vertices=self.edge_vertices[self.boundary_ids(self.patches[label])]
        if label not in self.boundary_graph:
            graph=defaultdict(list)
            for i,(a,b) in enumerate(vertices):
                graph[int(a)].append(i);graph[int(b)].append(i)
            self.boundary_graph[label]=graph
        graph=self.boundary_graph[label]
        chain={start}
        span=max(self.diagonal*.01,.1)
        def walk(previous,current):
            heading=Vector(self.coords[current]-self.coords[previous]).normalized()
            ahead_previous,ahead=previous,current
            travelled=0.
            for _ in range(32):
                onward=[]
                for eid in graph[ahead]:
                    a,b=vertices[eid];other=int(b if a==ahead else a)
                    if other!=ahead_previous:onward.append(other)
                if len(onward)!=1:break
                following=onward[0]
                travelled+=float(self.np.linalg.norm(self.coords[following]-self.coords[ahead]))
                ahead_previous,ahead=ahead,following
                if travelled>=span:break
            averaged=Vector(self.coords[ahead]-self.coords[previous])
            if averaged.length_squared>1e-12:heading=averaged.normalized()
            while True:
                incoming=Vector(self.coords[current]-self.coords[previous]).normalized()
                choices=[]
                for candidate in graph[current]:
                    if candidate in chain:continue
                    a,b=vertices[candidate];next_vertex=int(b if a==current else a)
                    outgoing=Vector(self.coords[next_vertex]-self.coords[current]).normalized()
                    turn=incoming.angle(outgoing)
                    choices.append((turn,candidate,next_vertex))
                if not choices:break
                turn,candidate,next_vertex=min(choices)
                if turn>math.radians(55):
                    # Dense triangulation can insert a tiny right-angle jog
                    # into an otherwise continuous rim. Look ahead for the
                    # original heading; a real corner does not return to it.
                    trial=[(candidate,current,next_vertex)]
                    travelled=(Vector(self.coords[next_vertex])-Vector(self.coords[current])).length
                    restored=False
                    while len(trial)<8 and travelled<span:
                        _,last_from,last_to=trial[-1]
                        options=[]
                        for edge_id in graph[last_to]:
                            if edge_id in chain or any(edge_id==item[0] for item in trial):continue
                            a,b=vertices[edge_id]
                            following=int(b if a==last_to else a)
                            turn_next=Vector(self.coords[last_to]-self.coords[last_from]).angle(
                                Vector(self.coords[following]-self.coords[last_to]))
                            options.append((turn_next,edge_id,following))
                        if not options:break
                        _,edge_id,following=min(options)
                        travelled+=(Vector(self.coords[following])-Vector(self.coords[last_to])).length
                        trial.append((edge_id,last_to,following))
                        net=Vector(self.coords[following]-self.coords[current]).normalized()
                        if net.dot(incoming)>math.cos(math.radians(35)) and net.dot(heading)>math.cos(math.radians(70)):
                            restored=True;break
                    if not restored:break
                    chain.update(item[0] for item in trial)
                    previous,current=trial[-1][1],trial[-1][2]
                else:
                    if Vector(self.coords[next_vertex]-self.coords[current]).normalized().dot(heading)<math.cos(math.radians(70)):break
                    chain.add(candidate);previous,current=current,next_vertex
        a,b=vertices[start]
        walk(int(a),int(b));walk(int(b),int(a))
        return chain


class FastGuide:
    """Project a highlighter direction with cached Blender ray casts, no mesh scan."""
    def __init__(self, hit, points):
        key,location,index,obj,matrix,depsgraph = hit
        self.obj = obj.evaluated_get(depsgraph)
        self.matrix = matrix.copy(); self.inverse = matrix.inverted_safe()
        mesh = self.obj.data
        self.normal = (matrix.to_3x3().inverted_safe().transposed() @ mesh.polygons[index].normal).normalized()
        first,last = Vector(points[0]),Vector(points[-1])
        self.center = (first+last)*.5
        self.direction = last-first
        self.direction -= self.normal*self.direction.dot(self.normal)
        if self.direction.length_squared<1e-10:self.direction=self.normal.orthogonal()
        self.direction.normalize()
        self.corners = [matrix @ Vector(corner) for corner in obj.bound_box]
        self.radius = max((corner-self.center).length for corner in self.corners)*.22

    def guide(self, angle=0.):
        normal=self.normal
        direction=self.direction*math.cos(angle)+normal.cross(self.direction)*math.sin(angle)
        extent=[(corner-self.center).dot(direction) for corner in self.corners]
        lo,hi=min(extent),max(extent)
        depth=max(self.radius*15,1.)
        local_direction=(self.inverse.to_3x3() @ -normal).normalized()
        sampled=[]
        for j in range(81):
            target=self.center+direction*(lo+(hi-lo)*j/80)
            local_origin=self.inverse @ (target+normal*depth)
            found,co,hit_normal,index=self.obj.ray_cast(local_origin,local_direction)
            if found and (self.matrix.to_3x3().inverted_safe().transposed() @ hit_normal).normalized().dot(normal)>.35:
                sampled.append((j,self.matrix @ co))
        if not sampled:return []
        # Keep the connected run nearest the marked stroke; never bridge gaps.
        runs=[];current=[]
        for index,co in sampled:
            if current and index != current[-1][0]+1:runs.append(current);current=[]
            current.append((index,co))
        if current:runs.append(current)
        center_index=min(range(81),key=lambda i:abs(lo+(hi-lo)*i/80))
        run=min(runs,key=lambda r:min(abs(i-center_index) for i,_ in r))
        return [co for _,co in run]


def paths_from_edges(vertices, edges):
    """Split branches and disconnected islands; never invent connecting edges."""
    neighbors = defaultdict(set)
    remaining = set(edges)
    for a, b in remaining: neighbors[a].add(b); neighbors[b].add(a)
    paths = []
    def walk(start, other):
        ids = [start]; a, b = start, other
        while tuple(sorted((a, b))) in remaining:
            remaining.remove(tuple(sorted((a, b)))); ids.append(b)
            if b == start or len(neighbors[b]) != 2: break
            nexts = [v for v in neighbors[b] if tuple(sorted((b, v))) in remaining]
            if not nexts: break
            a, b = b, nexts[0]
        closed = ids[0] == ids[-1]
        if closed: ids.pop()
        points = [vertices[i].copy() for i in ids]
        # Exact collinear subdivisions need no extra editing handles.
        changed = True
        while changed and len(points) > (3 if closed else 2):
            changed = False
            for i in range(len(points)) if closed else range(1, len(points)-1):
                a = points[i]-points[i-1]; b = points[(i+1)%len(points)]-points[i]
                if a.dot(b) >= 0 and a.cross(b).length <= 1e-7*max(1., a.length+b.length):
                    points.pop(i); changed = True; break
        if len(points) >= 2: paths.append((points, closed))
    for start in sorted(neighbors):
        if len(neighbors[start]) != 2:
            for other in sorted(neighbors[start]):
                if tuple(sorted((start, other))) in remaining: walk(start, other)
    while remaining:
        a, b = min(remaining); walk(a, b)
    return paths


def create_guides(context, paths):
    from . import curve_tools
    guides = []
    for points, closed in paths:
        obj = curve_tools.new_curve(context, 'FREE')
        obj.name = 'BBE Surface Curve'
        obj.location = points[0]
        spline = obj.data.splines.new('BEZIER'); spline.bezier_points.add(len(points)-1)
        spline.use_cyclic_u = closed
        for bp, co in zip(spline.bezier_points, points):
            bp.co = co-points[0]
            bp.handle_left_type = bp.handle_right_type = 'VECTOR'
        obj.bbe_curve.linked_handles = False
        obj['bbe_surface_trace'] = True
        curve_tools.refresh(obj); guides.append(obj)
    # One guide active for editing, all new guides selected for easy moving.
    if guides:
        for obj in context.selected_objects: obj.select_set(False)
        for obj in guides: obj.select_set(True)
        context.view_layer.objects.active = guides[-1]
    return guides


@dataclass(frozen=True)
class Pick:
    kind: str
    source: tuple
    edges: frozenset = frozenset()
    points: tuple = ()
    face_index: int = -1
    angle: float = 0.
    guide_id: int = -1


def point_key(co):
    return tuple(round(float(x), 6) for x in co)


def segment(a, b):
    return tuple(sorted((point_key(a), point_key(b))))


class SelectionHistory:
    def __init__(self):
        self.items = (); self.past = []; self.future = []

    def commit(self, items):
        items = tuple(items)
        if items == self.items: return
        self.past.append(self.items); self.items = items; self.future.clear()

    def toggle(self, pick):
        items = list(self.items)
        if pick in items: items.remove(pick)
        else: items.append(pick)
        self.commit(items)

    def undo(self):
        if not self.past: return
        self.future.append(self.items); self.items = self.past.pop()

    def redo(self):
        if not self.future: return
        self.past.append(self.items); self.items = self.future.pop()


def selected_segments(picks):
    groups = {}
    for pick in picks:
        if pick.kind == 'DRAW': continue
        faces, edges = groups.setdefault(pick.source, (defaultdict(int), set()))
        if pick.kind == 'FACE':
            for edge in pick.edges: faces[edge] += 1
        else: edges.update(pick.edges)
    return {key: {edge for edge,count in faces.items() if count == 1} | edges
            for key,(faces,edges) in groups.items()}


def selection_paths(picks):
    result = []
    for edges in selected_segments(p for p in picks if not (p.kind == 'FACE' and p.points)).values():
        coords = sorted({co for edge in edges for co in edge})
        indices = {co:i for i,co in enumerate(coords)}
        result.extend(paths_from_edges([Vector(co) for co in coords],
                                      {(indices[a],indices[b]) for a,b in edges}))
    result.extend(([Vector(co) for co in pick.points],False) for pick in picks
                  if pick.kind in {'DRAW','FACE'} and len(pick.points)>1)
    return result


def stroke_samples(a, b, spacing=4., limit=32):
    """Bound ray work per mouse event, interpolating fast pointer movement."""
    count = min(limit, max(1, math.ceil((b-a).length/spacing)))
    return [a+(b-a)*(i/count) for i in range(1,count+1)]


class Stroke:
    def __init__(self):
        self.runs = []; self.current = []; self.source = None

    def break_run(self):
        if len(self.current)>1:
            self.runs.append(Pick('DRAW', self.source, points=tuple(self.current)))
        self.current = []; self.source = None

    def add(self, source, location):
        if source != self.source: self.break_run(); self.source = source
        co = point_key(location)
        if not self.current or co != self.current[-1]: self.current.append(co)

    def finish(self):
        self.break_run()
        return tuple(self.runs)

    def lines(self):
        paths = [run.points for run in self.runs] + [self.current]
        return [co for points in paths for pair in zip(points,points[1:]) for co in pair]


class BBE_OT_surface_leave_choice(bpy.types.Operator):
    bl_idname='bbe.surface_leave_choice'
    bl_label='Resolve Temporary Curves'
    bl_description='Apply this choice to your temporary surface curves'
    bl_options={'INTERNAL'}
    choice: bpy.props.EnumProperty(items=[('KEEP','Keep Editing','Return to your temporary curves'),
        ('CREATE','Create Curves','Create editable curve objects now'),
        ('DISCARD','Discard Lines','Remove these temporary curves')],default='KEEP')

    def execute(self,context):
        session=next((op for op in _sessions if op.window==context.window),None)
        if session is None:return {'CANCELLED'}
        session.leave_action=self.choice
        session.leave_prompt=False
        session.area.tag_redraw()
        return {'FINISHED'}


class BBE_OT_surface_leave(bpy.types.Operator):
    bl_idname='bbe.surface_leave'
    bl_label='Keep your temporary curves?'
    bl_description='Create the curves, continue editing, or explicitly discard the preview'

    def invoke(self,context,event):
        self.session=next((op for op in _sessions if op.window==context.window),None)
        if self.session is None:return {'CANCELLED'}
        self.session.set_cursor('DEFAULT')
        # A menu closes on an action or dismissal. Property popups stay open
        # after nested operators and property dialogs add Continue/Cancel.
        # Blender's menu handler consumes input while it is open; dismissal
        # simply returns to the unchanged tracing session.
        context.window_manager.popup_menu(type(self).draw,title=self.bl_label)
        return {'FINISHED'}

    def draw(self,context):
        self.layout.ui_units_x=24
        self.layout.label(text='Your lines have not been created yet.',icon='INFO')
        row=self.layout.row(align=True)
        row.operator_context='EXEC_DEFAULT'
        for choice,label in (('KEEP','Keep Editing'),('CREATE','Create Curves'),('DISCARD','Discard Lines')):
            row.operator('bbe.surface_leave_choice',text=label).choice=choice

    def execute(self,context):
        return {'FINISHED'}

class BBE_OT_curve_surface(bpy.types.Operator):
    bl_idname = 'bbe.curve_from_surface'
    bl_label = 'Curve from Edges / Faces'
    bl_description = 'Select edge chains or broad faces for centered surface curves, or draw a direction; preview before creating'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.area and context.area.type == 'VIEW_3D'

    def invoke(self, context, event):
        if context.region.type != 'WINDOW':
            region = next(r for r in context.area.regions if r.type == 'WINDOW')
            with context.temp_override(region=region):
                result = bpy.ops.bbe.curve_from_surface('INVOKE_DEFAULT')
            return {'CANCELLED'} if result == {'RUNNING_MODAL'} else result
        if _sessions:
            self.report({'INFO'}, 'Finish or cancel the current surface trace first.')
            return {'CANCELLED'}
        self.area = context.area; self.region = context.region; self.window = context.window
        self.workspace = context.workspace; self.scene = context.scene
        self.mode = 'EDGE'; self.cache = {}; self.history = SelectionHistory(); self.hover = None
        self.selected_lines = []; self.hover_lines = []; self.stroke = None; self.last_xy = None
        self.stroke_hits = {}; self.active_pick = None; self.rotating = False
        self.draw_guides = {}; self.next_guide_id = 0; self.rotation_input = ''
        self.gizmo_lines = []; self.gizmo_center = None; self.gizmo_normal = None
        self.grabber_lines = []
        self.job = None; self.progress = ''; self.last_hover_time = 0.; self.dirty = True
        self.job_is_hover = False; self.hover_request = None; self.pending_click = None
        self.face_previews = {}; self.hover_due = 0.; self.hover_visible = False
        self.preview_lines = []; self.cursor_kind = None
        self.leave_prompt=False;self.leave_action=None;self.leave_pending=False
        self.shader = None; self.batches = []
        self.helper = context.scene.bbe_curve_helper; context.scene.bbe_curve_helper = False
        self.handles = [bpy.types.SpaceView3D.draw_handler_add(self.draw_lines, (), 'WINDOW', 'POST_VIEW'),
                        bpy.types.SpaceView3D.draw_handler_add(self.draw_panel, (), 'WINDOW', 'POST_PIXEL')]
        self.timer = context.window_manager.event_timer_add(.016,window=context.window)
        self.wm = context.window_manager
        _sessions.append(self)
        self.change_mode('EDGE')
        context.window_manager.modal_handler_add(self); self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    @property
    def picks(self): return self.history.items

    def change_mode(self, mode):
        self.cancel_job(); self.commit_stroke(); self.mode = mode; self.hover = None
        self.hover_request = None; self.pending_click = None; self.hover_visible = False
        self.set_cursor('CROSSHAIR')
        self.area.header_text_set('SURFACE CURVE: D draw | E edges | F faces | R rotate 90 | drag ring to rotate | Ctrl Z undo | Enter create')
        self.workspace.status_text_set({'DRAW':'Hold left mouse and draw on the model. Orbit to reach the underside. Blank gaps split strokes.',
            'EDGE':'Click near a visible boundary or crease to select its continuous chain.',
            'FACE':'Click a face for a broad surface patch and its longest guide. Drag the rotation ring to adjust.'}[mode])
        self.update_lines()
        if mode in {'FACE','EDGE'}:
            # Start while the pointer is still on the mode button. Only use an
            # unambiguous source, and never scan all scene meshes preemptively.
            candidates=[o for o in bpy.context.selected_objects if o.type=='MESH' and not o.hide_select]
            if not candidates:
                candidates=[o for o in bpy.context.visible_objects if o.type=='MESH' and not o.hide_select]
            if len(candidates)==1:
                obj=candidates[0];depsgraph=bpy.context.evaluated_depsgraph_get()
                matrix=obj.matrix_world.copy();key=(obj.as_pointer(),tuple(x for row in matrix for x in row))
                if key not in self.cache:
                    self.job=self.surface_for((key,None,0,obj,matrix,depsgraph));self.job_is_hover=True
                    self.progress='Preparing surface preview...'

    def cancel_job(self):
        if self.job is not None: self.job.close()
        self.job = None; self.progress = ''
        self.job_is_hover = False

    def set_cursor(self, kind):
        if getattr(self, 'cursor_kind', None) != kind:
            self.window.cursor_modal_set(kind); self.cursor_kind = kind

    def cursor_at(self, context, event):
        mx,my=event.mouse_x-self.region.x,event.mouse_y-self.region.y
        scale,x,top,_=self.buttons()
        inside=(0<=mx<self.region.width and 0<=my<self.region.height
                and not any(r.type!='WINDOW' and r.x<=event.mouse_x<r.x+r.width
                            and r.y<=event.mouse_y<r.y+r.height for r in self.area.regions))
        panel=inside and x<=mx<=x+314*scale and top-290*scale<=my<=top
        ring=inside and not panel and not self.stroke and self.on_ring(context,Vector((mx,my)))
        self.set_cursor('HAND' if self.rotating else 'DEFAULT' if panel or not inside
                        else 'PAINT_BRUSH' if self.stroke else 'HAND' if ring else 'CROSSHAIR')
        return inside,panel,ring,mx,my

    def accept_pick(self, pick):
        surface = self.cache.get(pick.source)
        existing = next((p for p in self.picks if p.kind == pick.kind and p.source == pick.source
                         and (surface.same_patch(pick.face_index, p.face_index) if pick.kind == 'FACE'
                              else p.edges == pick.edges)), None)
        self.history.toggle(existing or pick)
        self.active_pick = pick if existing is None and pick.kind == 'FACE' else None
        self.update_lines()

    def publish_pick(self, pick, preview):
        if preview:
            request = self.hover_request
            if not self.hover_visible or request is None or request[2] != pick.kind or request[0][0] != pick.source:
                return
            if pick.kind == 'FACE' and not self.cache[pick.source].same_patch(pick.face_index, request[0][2]):
                return
            self.hover = pick; self.update_lines()
        else:
            self.accept_pick(pick)

    def start_pick_job(self, request, preview):
        hit, xy, mode = request
        self.job_is_hover = preview
        self.job = self.prepare_face(hit, preview) if mode == 'FACE' else self.prepare_edge(hit, xy, preview)
        self.progress = 'Preparing hover preview...' if preview else 'Preparing selection...'

    def advance_preview(self):
        if self.job is not None:
            self.advance_job()
        if self.job is None:
            if self.pending_click is not None:
                request = self.pending_click; self.pending_click = None
                self.start_pick_job(request, False)
            elif self.hover_request is not None and self.hover_due and time.perf_counter() >= self.hover_due:
                self.hover_due = 0.
                self.start_pick_job(self.hover_request, True)

    def update_lines(self):
        self.outline_lines = [co for edges in selected_segments(tuple(p for p in self.picks if p.kind=='FACE')).values() for edge in edges for co in edge]
        self.selected_lines = [co for edges in selected_segments(tuple(p for p in self.picks if p.kind=='EDGE')).values() for edge in edges for co in edge]
        for pick in self.picks:
            if pick.kind in {'DRAW','FACE'}:
                self.selected_lines.extend(co for edge in zip(pick.points,pick.points[1:]) for co in edge)
        if self.stroke: self.selected_lines.extend(self.stroke.lines())
        self.hover_lines = [co for edge in self.hover.edges for co in edge] if self.hover else []
        self.preview_lines = ([co for pair in zip(self.hover.points, self.hover.points[1:]) for co in pair]
                              if self.hover else [])
        self.gizmo_lines = [];self.grabber_lines=[]
        pick=self.active_pick
        if pick in self.picks and len(pick.points)>1:
            if pick.kind=='DRAW':
                spec=self.draw_guides.get(pick.guide_id)
                meta=(spec.center,spec.normal,spec.radius) if spec else None
            else:
                surface=self.cache.get(pick.source)
                meta=None
                if surface is not None:
                    patch=surface.patch_faces(pick.face_index)
                    label=int(surface.patch_labels[pick.face_index]) if isinstance(surface,DenseSurface) else min(patch)
                    meta=surface.guide_meta.get(label)
            if meta:
                center,normal,radius=meta
                self.gizmo_center=center;self.gizmo_normal=normal
                radius=max(.05,radius)
                u=normal.orthogonal().normalized()*radius;v=normal.cross(u)
                ring=[center+u*math.cos(i*math.tau/48)+v*math.sin(i*math.tau/48) for i in range(49)]
                self.gizmo_lines=[tuple(co) for pair in zip(ring,ring[1:]) for co in pair]
                direction=(Vector(pick.points[-1])-Vector(pick.points[0]))
                direction-=normal*direction.dot(normal)
                if direction.length_squared>1e-10:
                    direction.normalize()
                    grip=center+direction*radius
                    tangent=normal.cross(direction)
                    size=radius*.11
                    diamond=[grip+direction*size,grip+tangent*size,
                             grip-direction*size,grip-tangent*size,grip+direction*size]
                    self.grabber_lines=[tuple(co) for pair in zip(diamond,diamond[1:]) for co in pair]
        self.dirty = True

    def ray(self, context, xy):
        region_data=self.area.spaces.active.region_3d
        origin = view.region_2d_to_origin_3d(self.region, region_data, xy)
        direction = view.region_2d_to_vector_3d(self.region, region_data, xy)
        depsgraph = context.evaluated_depsgraph_get()
        hit, location, normal, index, obj, matrix = self.scene.ray_cast(depsgraph, origin, direction)
        if not hit:return None
        if obj.type != 'MESH' or obj.hide_select or obj.get('bbe_asset_browser_pin'):
            # Curves already laid on the surface must not occlude the next
            # trace. Query eligible mesh objects when a helper intercepted it.
            closest=None
            for candidate in context.visible_objects:
                if candidate.type!='MESH' or candidate.hide_select or candidate.get('bbe_asset_browser_pin'):continue
                evaluated=candidate.evaluated_get(depsgraph)
                inverse=evaluated.matrix_world.inverted_safe()
                found,co,n,fi=evaluated.ray_cast(inverse@origin,(inverse.to_3x3()@direction).normalized())
                if not found:continue
                world=evaluated.matrix_world@co;distance=(world-origin).length_squared
                if closest is None or distance<closest[0]:closest=(distance,world,fi,candidate,evaluated.matrix_world.copy())
            if closest is None:return None
            _,location,index,obj,matrix=closest
        if index<0:return None
        key = (obj.as_pointer(), tuple(x for row in matrix for x in row))
        return key, location, index, obj, matrix, depsgraph

    def local_pick(self, context, xy):
        # A few neighboring rays allow clicks just outside a silhouette edge.
        offsets = [(0,0)] if self.mode == 'FACE' else [(0,0),(-7,0),(7,0),(0,-7),(0,7)]
        best = None; distance = 18*max(.75,context.preferences.system.ui_scale)
        face_hit = None
        for dx,dy in offsets:
            hit = self.ray(context, xy+Vector((dx,dy)))
            if hit is None: continue
            key, location, index, obj, matrix, depsgraph = hit
            mesh = obj.evaluated_get(depsgraph).data
            if index >= len(mesh.polygons): continue
            face = mesh.polygons[index]
            coords = [matrix @ mesh.vertices[i].co for i in face.vertices]
            edges = frozenset(segment(a,b) for a,b in zip(coords,coords[1:]+coords[:1]) if (a-b).length_squared>1e-14)
            if self.mode in {'FACE','EDGE'}: return Pick(self.mode,key), hit
            for edge in edges:
                a,b = [view.location_3d_to_region_2d(self.region,context.region_data,Vector(co)) for co in edge]
                if a is None or b is None: continue
                delta=b-a; t=max(0.,min(1.,(xy-a).dot(delta)/max(delta.length_squared,1e-12)))
                d=(xy-(a+t*delta)).length
                if d<distance: distance=d;best=Pick('EDGE',key,frozenset((edge,)));face_hit=hit
            if best is not None: break
        return best,face_hit

    def surface_for(self, hit):
        key, location, index, obj, matrix, depsgraph = hit
        mesh = obj.evaluated_get(depsgraph).data
        signature = (key, obj.data.as_pointer(), len(mesh.vertices), len(mesh.polygons))
        if key not in self.cache:
            if _surface_snapshot.get('signature') == signature:
                surface = _surface_snapshot['surface']
                if isinstance(surface,DenseSurface):surface.obj=obj.evaluated_get(depsgraph)
                self.face_previews = _surface_snapshot['previews']
            elif len(mesh.polygons)>100000:
                surface=DenseSurface.__new__(DenseSurface)
                try:yield from surface.build_steps(mesh,matrix,obj.evaluated_get(depsgraph))
                except ValueError:
                    surface=Surface.__new__(Surface)
                    yield from surface.build_steps(mesh,matrix)
            else:
                surface = Surface.__new__(Surface)
                yield from surface.build_steps(mesh,matrix)
            # One evaluated mesh snapshot bounds memory and keeps repeated picks fast.
            self.cache = {key:surface}
            if _surface_snapshot.get('signature') != signature:
                self.face_previews = {}
                _surface_snapshot.clear()
                _surface_snapshot.update(signature=signature, surface=surface, previews=self.face_previews,
                                         object_pointer=obj.as_pointer(), mesh_pointer=obj.data.as_pointer())
        return self.cache[key]

    def prepare_face(self, hit, preview=False):
        key, location, index, obj, matrix, depsgraph = hit
        surface = yield from self.surface_for(hit)
        yield from surface.patch_steps(index)
        patch=surface.patch_faces(index)
        label = int(surface.patch_labels[index]) if isinstance(surface, DenseSurface) else min(patch)
        cached = self.face_previews.get((key, label))
        if cached is not None:
            self.publish_pick(cached, preview); return
        edges=surface.boundary_segments(patch)
        yield f'Projecting guide across {len(patch):,} facets...'
        path, center, normal = surface.guide(patch)
        pick = Pick('FACE',key,frozenset(edges),tuple(point_key(p) for p in path),index)
        self.face_previews[key, label] = pick
        self.publish_pick(pick, preview)

    def prepare_edge(self, hit, xy, preview=False):
        key, location, index, obj, matrix, depsgraph = hit
        surface = yield from self.surface_for(hit)
        yield from surface.patch_steps(index)
        edges=surface.edge_chain_at(index,location,xy,self.region,self.area.spaces.active.region_3d,
                                    bpy.context.preferences.system.ui_scale)
        if not edges:
            if not preview:self.report({'INFO'},'Click closer to a visible boundary or crease edge.')
            self.hover=None;self.update_lines();return
        pick = Pick('EDGE',key,edges)
        self.publish_pick(pick, preview)

    def prepare_draw(self, runs, hits):
        yield 'Projecting the highlighted direction...'
        prepared = []
        for run in runs:
            hit = hits.get(run.source)
            if hit is None: continue
            spec=FastGuide(hit,run.points)
            path=spec.guide()
            if len(path)>1:
                guide_id=self.next_guide_id;self.next_guide_id+=1
                self.draw_guides[guide_id]=spec
                prepared.append(Pick('DRAW',run.source,points=tuple(point_key(p) for p in path),guide_id=guide_id))
        if prepared:
            self.history.commit(self.picks+tuple(prepared)); self.active_pick = prepared[-1]
        self.update_lines()

    def rotate_active(self, angle):
        pick = self.active_pick
        if pick not in self.picks:return
        self.set_active_angle(pick.angle+angle)

    def set_active_angle(self, angle, record=True):
        pick=self.active_pick
        if pick not in self.picks:return
        from dataclasses import replace
        if pick.kind=='DRAW':
            spec=self.draw_guides.get(pick.guide_id)
            if spec is None:return
            path=spec.guide(angle)
        else:
            surface=self.cache.get(pick.source)
            if surface is None:return
            path,_,_=surface.guide(surface.patch_faces(pick.face_index),angle=angle)
        if len(path)<2:return
        updated=replace(pick,points=tuple(point_key(p) for p in path),angle=angle)
        items=list(self.picks);items[items.index(pick)]=updated
        if record:self.history.commit(items)
        else:self.history.items=tuple(items)
        self.active_pick=updated;self.update_lines()

    def finish_rotation(self):
        if self.picks!=self.rotation_original_items:
            self.history.past.append(self.rotation_original_items)
            self.history.future.clear()
        self.rotating=False;self.rotation_input=''
        self.area.tag_redraw()

    def ring_angle(self, context, xy):
        if self.gizmo_center is None or self.gizmo_normal is None:return None
        origin=view.region_2d_to_origin_3d(self.region,context.region_data,xy)
        ray=view.region_2d_to_vector_3d(self.region,context.region_data,xy)
        denominator=ray.dot(self.gizmo_normal)
        if abs(denominator)<1e-5:return None
        location=origin+ray*((self.gizmo_center-origin).dot(self.gizmo_normal)/denominator)
        direction=location-self.gizmo_center
        if direction.length_squared<1e-10:return None
        u=self.gizmo_normal.orthogonal().normalized()
        return math.atan2(self.gizmo_normal.dot(u.cross(direction)),u.dot(direction))

    def on_ring(self, context, xy):
        if not self.gizmo_lines:return False
        segments=self.gizmo_lines+self.grabber_lines
        for a,b in zip(segments[::2],segments[1::2]):
            pa=view.location_3d_to_region_2d(self.region,context.region_data,Vector(a))
            pb=view.location_3d_to_region_2d(self.region,context.region_data,Vector(b))
            if pa is None or pb is None:continue
            delta=pb-pa;t=max(0.,min(1.,(xy-pa).dot(delta)/max(delta.length_squared,1e-12)))
            if (xy-pa-delta*t).length<12*max(.75,context.preferences.system.ui_scale):return True
        return False

    def advance_job(self):
        deadline = time.perf_counter()+.006
        try:
            while self.job is not None and time.perf_counter()<deadline:
                self.progress = next(self.job)
        except StopIteration:
            self.job = None; self.progress = ''
        except Exception as error:
            self.cancel_job(); self.cache.clear()
            self.report({'WARNING'},'Surface selection could not finish: '+str(error))

    def draw_sample(self, context, xy):
        hit = self.ray(context,xy)
        if hit is None: self.stroke.break_run()
        else:
            self.stroke.add(hit[0],hit[1]);self.stroke_hits.setdefault(hit[0],hit)

    def commit_stroke(self):
        if self.stroke:
            runs=self.stroke.finish()
            if runs:
                self.cancel_job();self.job=self.prepare_draw(runs,self.stroke_hits.copy())
                self.progress='Finding a clean surface path...'
            self.stroke = None; self.last_xy = None
            self.stroke_hits.clear()
            self.set_cursor('CROSSHAIR')

    def undo(self, redo=False):
        if self.job is not None:
            self.cancel_job(); return
        if self.stroke is not None:
            self.stroke = None; self.last_xy = None
        elif redo: self.history.redo()
        else: self.history.undo()
        self.hover = None
        self.active_pick = next((p for p in reversed(self.picks)
                                 if p.face_index>=0 or p.guide_id>=0),None)
        self.update_lines()

    def buttons(self):
        scale=max(.75,bpy.context.preferences.system.ui_scale)
        x=64*scale;top=max(254*scale,self.region.height-250*scale)
        return scale,x,top,[('EDGE','Edges',12,-64,140,30),('FACE','Faces',162,-64,140,30),
            ('DRAW','Draw on Surface',12,-101,290,30),
            ('ROTATE','Rotate 90°',12,-137,290,26),
            ('UNDO','Undo',12,-205,90,26),('REDO','Redo',112,-205,90,26),('STOP','Stop scan',212,-205,90,26),
            ('FINISH','Create Curves',12,-242,140,30),('CANCEL','Cancel',162,-242,140,30)]

    def draw_panel(self):
        context=bpy.context
        if context.area!=self.area or context.region!=self.region:return
        from . import curve_widgets as w
        w.update_theme(context);scale,x,top,buttons=self.buttons()
        shader=gpu.shader.from_builtin('UNIFORM_COLOR')
        with w.canvas(context):
            w.rounded(shader,x,top-290*scale,314*scale,290*scale,12*scale,w.INK)
            w.text('CURVE FROM EDGES / FACES',x+14*scale,top-23*scale,13*scale)
            for action,label,bx,by,width,height in buttons:
                enabled = (action!='STOP' or self.job is not None) and (action!='ROTATE' or self.active_pick in self.picks)
                fill=w.PURPLE if action==self.mode or action=='FINISH' else w.BUTTON
                w.rounded(shader,x+bx*scale,top+by*scale,width*scale,height*scale,6*scale,fill)
                w.text(label,x+(bx+width/2)*scale,top+(by+9)*scale,11*scale,w.TEXT if enabled else w.MUTED,align='CENTER')
            status=(f'Rotation: {self.rotation_input}°' if self.rotating and self.rotation_input
                    else self.progress or f'{len(self.picks)} selections / strokes')
            w.text(status,x+14*scale,top-157*scale,10*scale,w.MUTED)
            w.text('Drag diamond; type degrees while holding.' if self.active_pick in self.picks
                   else 'Stroke marks direction.' if self.mode=='DRAW'
                   else 'Click near a boundary or broad surface.',x+14*scale,top-174*scale,10*scale,w.MUTED)
            w.text('Ctrl Z: undo   Ctrl Y: redo   Enter: create',x+14*scale,top-267*scale,10*scale,w.MUTED)
            if self.hover_visible and self.hover_request is not None:
                mx,my=self.hover_request[1]
                color=(.4,1.,.65,1.) if self.hover else (.15,.85,1.,1.)
                selected = self.hover is not None and any(p.kind==self.hover.kind and p.source==self.hover.source
                    and (self.cache[p.source].same_patch(p.face_index,self.hover.face_index) if p.kind=='FACE'
                         else p.edges==self.hover.edges) for p in self.picks)
                w.disc(shader,mx,my,3*scale,color)
                w.text('Click to remove' if selected else 'Click to select' if self.hover else 'Preparing preview…',
                       mx+15*scale,my+16*scale,11*scale,color)

    def draw_lines(self):
        if bpy.context.area!=self.area or bpy.context.region!=self.region:return
        if self.shader is None:self.shader=gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        shader=self.shader
        if self.dirty:
            self.batches=[(batch_for_shader(shader,'LINES',{'pos':lines}),color)
                for lines,color in ((self.outline_lines,(.25,.65,.6,.3)),
                                  (self.hover_lines,(.15,.85,1.,.7)),
                                  (self.preview_lines,(.4,1.,.65,1)),
                                  (self.selected_lines,(1.,.9,.2,1)),
                                  (self.gizmo_lines,(1.,.55,.18,1)),
                                  (self.grabber_lines,(1.,.9,.2,1))) if lines]
            self.dirty=False
        blend=gpu.state.blend_get();depth=gpu.state.depth_test_get();mask=gpu.state.depth_mask_get()
        try:
            gpu.state.blend_set('ALPHA');gpu.state.depth_test_set('NONE');gpu.state.depth_mask_set(False)
            shader.bind();shader.uniform_float('viewportSize',(self.region.width,self.region.height));shader.uniform_float('lineWidth',3.)
            for batch,color in self.batches:shader.uniform_float('color',color);batch.draw(shader)
        finally:
            gpu.state.blend_set(blend);gpu.state.depth_test_set(depth);gpu.state.depth_mask_set(mask)

    def cleanup(self):
        # Release the session first, even if Blender already removed a window
        # or timer. A stale operator must never block creating another curve.
        if self in _sessions:_sessions.remove(self)
        self.cancel_job()
        self.wm.event_timer_remove(self.timer)
        for handle in self.handles:bpy.types.SpaceView3D.draw_handler_remove(handle,'WINDOW')
        self.handles=[];self.cache.clear();self.batches=[]
        self.scene.bbe_curve_helper=self.helper
        self.window.cursor_modal_restore();self.workspace.status_text_set(None)
        self.area.header_text_set(None);self.area.tag_redraw()

    def finish(self, context):
        if getattr(self,'pending_click',None) is not None:
            request=self.pending_click;self.pending_click=None
            self.cancel_job();self.start_pick_job(request,False)
        if getattr(self,'job_is_hover',False):
            self.cancel_job(); self.hover_request = None; self.hover_due = 0.
        if self.job is not None:
            self.report({'INFO'},'The surface selection is still being prepared. Wait or choose Stop scan.');return {'RUNNING_MODAL'}
        self.commit_stroke()
        if self.job is not None:
            self.report({'INFO'},'Finding a clean surface path. Create Curves when it is ready.')
            return {'RUNNING_MODAL'}
        paths=selection_paths(self.picks)
        if not paths:
            self.report({'INFO'},'Draw on the model or select edges / faces, then choose Create Curves.');return {'RUNNING_MODAL'}
        self.cleanup();guides=create_guides(context,paths)
        self.report({'INFO'},f'Created {len(guides)} editable curve(s). Source objects unchanged.')
        return {'FINISHED'}

    def request_leave(self,context,event=None):
        if self.picks or self.stroke or self.pending_click is not None or (self.job is not None and not self.job_is_hover):
            if event is not None and event.type=='LEFTMOUSE' and event.value=='PRESS':
                # Open after release so the click that requested the menu
                # cannot also activate whichever choice appears under it.
                self.leave_pending=True
                return {'RUNNING_MODAL'}
            if not getattr(self,'leave_prompt',False):
                bpy.ops.bbe.surface_leave('INVOKE_DEFAULT')
            return {'RUNNING_MODAL'}
        self.cleanup();return {'CANCELLED'}

    def modal(self, context, event):
        if self not in _sessions:return {'CANCELLED'}
        if getattr(self,'leave_pending',False):
            if event.type=='LEFTMOUSE' and event.value=='RELEASE':
                self.leave_pending=False
                return self.request_leave(context)
            return {'RUNNING_MODAL'}
        if getattr(self,'leave_prompt',False):return {'PASS_THROUGH'}
        action=getattr(self,'leave_action',None)
        if action:
            self.leave_action=None
            if action=='DISCARD':self.cleanup();return {'CANCELLED'}
            if action=='CREATE':return self.finish(context)
            self.set_cursor('CROSSHAIR')
        if event.type=='TIMER':
            if self.job is not None or self.pending_click is not None or self.hover_due:
                self.advance_preview();self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if self.rotating and event.type=='ESC' and event.value=='PRESS':
            self.history.items=self.rotation_original_items
            self.active_pick=self.rotation_original_pick
            self.rotating=False;self.rotation_input='';self.update_lines();self.cursor_at(context,event)
            self.area.tag_redraw();return {'RUNNING_MODAL'}
        if self.rotating and event.type in {'RET','NUMPAD_ENTER'} and event.value=='PRESS':
            self.finish_rotation();self.cursor_at(context,event);return {'RUNNING_MODAL'}
        if self.rotating and event.value=='PRESS':
            digits={'ZERO':'0','ONE':'1','TWO':'2','THREE':'3','FOUR':'4',
                    'FIVE':'5','SIX':'6','SEVEN':'7','EIGHT':'8','NINE':'9'}
            digits.update({f'NUMPAD_{i}':str(i) for i in range(10)})
            if event.type in digits:
                self.rotation_input+=digits[event.type]
            elif event.type in {'PERIOD','NUMPAD_PERIOD','NUMPAD_DECIMAL'}:
                if '.' not in self.rotation_input:self.rotation_input+='.'
            elif event.type in {'MINUS','NUMPAD_MINUS'}:
                self.rotation_input=(self.rotation_input[1:] if self.rotation_input.startswith('-')
                                     else '-'+self.rotation_input)
            elif event.type=='BACK_SPACE':
                self.rotation_input=self.rotation_input[:-1]
            if event.type in digits or event.type in {'PERIOD','NUMPAD_PERIOD','NUMPAD_DECIMAL','MINUS','NUMPAD_MINUS','BACK_SPACE'}:
                try:degrees=float(self.rotation_input)
                except ValueError:degrees=None
                if degrees is not None:self.set_active_angle(self.rotation_start_angle+math.radians(degrees),record=False)
                self.area.tag_redraw();return {'RUNNING_MODAL'}
        if event.type in {'ESC','RIGHTMOUSE'} and event.value=='PRESS':return self.request_leave(context,event)
        if event.type=='LEFTMOUSE' and event.value=='RELEASE' and self.rotating:
            self.finish_rotation();self.cursor_at(context,event)
            return {'RUNNING_MODAL'}
        if self.rotating and event.type=='MOUSEMOVE':
            self.set_cursor('HAND')
            angle=self.ring_angle(context,Vector((event.mouse_region_x,event.mouse_region_y)))
            if angle is not None:
                if not self.rotation_input:
                    delta=(angle-self.rotate_last_angle+math.pi)%math.tau-math.pi
                    if abs(delta)>1e-4:self.set_active_angle(self.active_pick.angle+delta,record=False)
                self.rotate_last_angle=angle;self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.value=='PRESS' and ((event.type=='Z' and event.ctrl) or (event.type=='Y' and event.ctrl) or event.type=='BACK_SPACE'):
            self.undo(redo=(event.type=='Y' or (event.type=='Z' and event.shift)));self.area.tag_redraw();return {'RUNNING_MODAL'}
        if event.type in {'RET','NUMPAD_ENTER'} and event.value=='PRESS':return self.finish(context)
        if event.type=='R' and event.value=='PRESS':
            self.rotate_active(math.pi/2);self.area.tag_redraw();return {'RUNNING_MODAL'}
        if event.type in {'MIDDLEMOUSE','WHEELUPMOUSE','WHEELDOWNMOUSE','NDOF_MOTION'}:
            self.hover=None;self.hover_visible=False;self.hover_request=None;self.hover_due=0.
            self.commit_stroke();self.update_lines();return {'PASS_THROUGH'}
        if event.type in {'D','E','F'} and event.value=='PRESS':self.change_mode({'D':'DRAW','E':'EDGE','F':'FACE'}[event.type])
        if event.type=='LEFTMOUSE' and event.value=='RELEASE' and self.stroke:
            xy=Vector((event.mouse_region_x,event.mouse_region_y))
            if 0<=xy.x<self.region.width and 0<=xy.y<self.region.height:
                self.draw_sample(context,xy)
            self.commit_stroke();self.update_lines()
        if event.type in {'LEFTMOUSE','MOUSEMOVE'}:
            scale,x,top,buttons=self.buttons()
            in_region,panel,ring,mx,my=self.cursor_at(context,event)
            if panel:
                self.hover=None; self.hover_visible=False; self.hover_request=None; self.hover_due=0.
                if self.stroke:self.stroke.break_run();self.last_xy=None
                if event.type=='LEFTMOUSE' and event.value=='PRESS':
                    for action,label,bx,by,width,height in buttons:
                        if x+bx*scale<=mx<=x+(bx+width)*scale and top+by*scale<=my<=top+(by+height)*scale:
                            if action=='FINISH':return self.finish(context)
                            if action=='CANCEL':return self.request_leave(context,event)
                            if action=='ROTATE':self.rotate_active(math.pi/2)
                            if action in {'UNDO','REDO'}:self.undo(action=='REDO')
                            elif action=='STOP':self.cancel_job()
                            elif action in {'DRAW','EDGE','FACE'}:self.change_mode(action)
                self.update_lines()
                self.set_cursor('DEFAULT')
            elif in_region:
                xy=Vector((mx,my))
                if ring:
                    self.hover=None;self.hover_visible=False;self.hover_request=None;self.hover_due=0.
                    self.update_lines()
                if event.type=='LEFTMOUSE' and event.value=='PRESS' and ring:
                    angle=self.ring_angle(context,xy)
                    if angle is not None:
                        self.rotating=True;self.rotate_last_angle=angle
                        self.rotation_start_angle=self.active_pick.angle
                        self.rotation_original_pick=self.active_pick
                        self.rotation_original_items=self.picks
                        self.rotation_input='';self.set_cursor('HAND')
                        return {'RUNNING_MODAL'}
                if ring:
                    self.area.tag_redraw();return {'RUNNING_MODAL'}
                try:
                    if self.mode=='DRAW':
                        if event.type=='LEFTMOUSE' and event.value=='PRESS':
                            if self.picks and self.ray(context,xy) is None:return self.request_leave(context)
                            self.stroke=Stroke();self.last_xy=xy;self.draw_sample(context,xy)
                            self.set_cursor('PAINT_BRUSH')
                        elif event.type=='MOUSEMOVE' and self.stroke:
                            if self.last_xy is None or (xy-self.last_xy).length>=16:
                                self.draw_sample(context,xy);self.last_xy=xy
                        if self.stroke:self.update_lines()
                    elif event.type=='LEFTMOUSE' or time.perf_counter()-self.last_hover_time>.035:
                        self.last_hover_time=time.perf_counter();candidate,hit=self.local_pick(context,xy)
                        self.hover_visible=hit is not None
                        self.hover_request=(hit,xy,self.mode) if hit is not None else None
                        if hit is None:
                            self.hover=None;self.hover_due=0.;self.update_lines()
                            if self.picks and event.type=='LEFTMOUSE' and event.value=='PRESS':
                                return self.request_leave(context,event)
                        else:
                            same = (self.hover is not None and self.hover.kind==self.mode and self.hover.source==hit[0]
                                    and self.mode=='FACE' and self.cache[hit[0]].same_patch(self.hover.face_index,hit[2]))
                            if not same:
                                self.hover_due=time.perf_counter()+.04
                                if self.mode=='FACE':self.hover=None;self.update_lines()
                            if event.type=='LEFTMOUSE' and event.value=='PRESS':
                                if same:self.accept_pick(self.hover)
                                else:self.pending_click=self.hover_request
                except (ReferenceError,RuntimeError,IndexError):
                    self.cleanup();self.report({'WARNING'},'The source mesh changed. Restart surface tracing.');return {'CANCELLED'}
            else:
                if event.type=='LEFTMOUSE' and event.value=='PRESS' and (self.picks or self.stroke or self.pending_click is not None or (self.job is not None and not self.job_is_hover)):
                    return self.request_leave(context,event)
                self.hover=None;self.hover_visible=False;self.hover_request=None;self.hover_due=0.
                if self.stroke:self.stroke.break_run();self.last_xy=None
                self.update_lines()
                return {'PASS_THROUGH'}
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def cancel(self,context):
        if self in _sessions:self.cleanup()


@persistent
def stop_sessions(*_):
    for session in list(_sessions):session.cleanup()
    _surface_snapshot.clear()


@persistent
def invalidate_surface_snapshot(scene, depsgraph):
    pointers = (_surface_snapshot.get('object_pointer'), _surface_snapshot.get('mesh_pointer'))
    for update in depsgraph.updates:
        if update.is_updated_geometry and update.id.original.as_pointer() in pointers:
            _surface_snapshot.clear()
            # Do not retain an invalid evaluated object during an active trace.
            for session in _sessions:
                session.cancel_job();session.cache.clear();session.face_previews.clear()
                session.hover=None;session.hover_request=None;session.hover_due=0.;session.update_lines()
            break


def register():
    bpy.utils.register_class(BBE_OT_surface_leave_choice)
    bpy.utils.register_class(BBE_OT_surface_leave)
    bpy.utils.register_class(BBE_OT_curve_surface)
    bpy.app.handlers.load_pre.append(stop_sessions)
    bpy.app.handlers.depsgraph_update_post.append(invalidate_surface_snapshot)


def unregister():
    stop_sessions()
    if stop_sessions in bpy.app.handlers.load_pre:bpy.app.handlers.load_pre.remove(stop_sessions)
    if invalidate_surface_snapshot in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(invalidate_surface_snapshot)
    bpy.utils.unregister_class(BBE_OT_curve_surface)
    bpy.utils.unregister_class(BBE_OT_surface_leave)
    bpy.utils.unregister_class(BBE_OT_surface_leave_choice)

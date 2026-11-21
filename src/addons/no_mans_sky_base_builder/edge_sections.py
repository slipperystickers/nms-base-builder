"""Connected mesh sections shared by the trace picker and the alignment tool."""
import math
from collections import defaultdict
from mathutils import Vector


class EdgeSections:
    def __init__(self, coordinates, edges):
        self.coordinates = coordinates
        self.neighbors = defaultdict(list)
        for a, b in edges:
            self.neighbors[a].append(b)
            self.neighbors[b].append(a)
        self.turns = {}
        self.spans = {}

    def direction(self, a, b):
        return Vector(self.coordinates[b]) - Vector(self.coordinates[a])

    def onward(self, a, b):
        key = (a, b)
        if key not in self.turns:
            incoming = self.direction(a, b)
            options = sorted((incoming.angle(self.direction(b, c), math.pi), c)
                             for c in self.neighbors[b] if c != a)
            # Do not let vertex numbering decide which fork a click follows.
            self.turns[key] = (options[0] if options and
                               (len(options) == 1 or options[1][0] - options[0][0] > math.radians(2))
                               else (math.pi, None))
        return self.turns[key]

    def next_vertex(self, a, b, limit):
        angle, c = self.onward(a, b)
        if c is not None and angle <= limit and self.onward(c, b)[1] == a:
            return c
        return None

    def span(self, a, b):
        """Collapse collinear subdivisions before comparing neighbouring bends."""
        key = tuple(sorted((a, b)))
        if key in self.spans:
            return self.spans[key]
        seen = {key}
        def walk(previous, current):
            result = []
            while True:
                nxt = self.next_vertex(previous, current, math.radians(.25))
                if nxt is None:
                    return result
                edge = tuple(sorted((current, nxt)))
                if edge in seen:
                    return result
                seen.add(edge)
                result.append(nxt)
                previous, current = current, nxt
        left = walk(b, a)
        right = walk(a, b)
        span = tuple(reversed(left)) + (a, b) + tuple(right)
        for edge in seen:
            self.spans[edge] = span
        return span

    def next_span(self, path, limit):
        a, b = path[-2:]
        c = self.next_vertex(a, b, limit)
        if c is None:
            return ()
        span = self.span(b, c)
        if span[0] == b:
            return span
        return span[::-1] if span[-1] == b else ()

    def bend(self, left, right):
        u = self.direction(left[0], left[-1])
        v = self.direction(right[0], right[-1])
        if min(u.length, v.length) < .32 * max(u.length, v.length):
            return None
        return u.angle(v, math.pi), u.cross(v).normalized()

    @staticmethod
    def similar(a, b):
        return bool(a and b and min(a[0], b[0]) >= .7 * max(a[0], b[0]) and a[1].dot(b[1]) > .85)

    def short_fillet(self, left, right, bend, limit):
        """Recognize a two-chord bevel between substantially longer straight sides."""
        if not bend or bend[0] > min(2*limit, math.radians(60)):
            return False
        outer_limit=math.radians(60)
        before=self.next_span(left[::-1],outer_limit)
        after=self.next_span(right,outer_limit)
        if not before or not after:
            return False
        u=self.direction(left[0],left[-1])
        v=self.direction(right[0],right[-1])
        lead=self.direction(before[-1],before[0])
        tail=self.direction(after[0],after[-1])
        if lead.length < 3*u.length or tail.length < 3*v.length:
            return False
        half=(bend[0]/2,bend[1])
        return (self.similar((lead.angle(u),lead.cross(u).normalized()),half) and
                self.similar((v.angle(tail),v.cross(tail).normalized()),half))

    def section(self, a, b, max_turn):
        start = self.span(a, b)
        seen = {start}
        limit = math.radians(min(max_turn, 80))
        def walk(path):
            while True:
                nxt = self.next_span(path, min(2*limit, math.radians(80)))
                if not nxt or nxt in seen or nxt[::-1] in seen:
                    return
                bend = self.bend(path, nxt)
                before = self.next_span(path[::-1], limit)
                after = self.next_span(nxt, limit)
                # A rounded section has repeated turns in the same direction.
                # A lone corner or a long tangent touching a fillet starts a new pick.
                # Near-flat ripples on a tessellated rim can change bend sign.
                # Preserve the rim where both sides are individual, similarly
                # sized facets rather than merging a long straight span.
                shallow = (bend and max(len(path),len(nxt))<=3 and
                           bend[0]<=min(limit,math.radians(3)))
                rounded = bend and bend[0] <= limit and (before and self.similar(self.bend(before[::-1], path), bend) or
                        after and self.similar(bend, self.bend(nxt, after)))
                if not shallow and not rounded and not self.short_fillet(path,nxt,bend,limit):
                    return
                seen.add(nxt)
                path = nxt
        walk(start)
        walk(start[::-1])
        return {tuple(sorted(pair)) for span in seen for pair in zip(span, span[1:])}


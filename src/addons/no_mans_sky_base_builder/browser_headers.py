"""Scoped header drawing for dedicated BBE windows and building layouts."""
def add(header, method, owner, draw):
    original = getattr(header, method)
    routes = getattr(original, "_bbe_header_routes", None)
    if routes is None:
        routes = {}
        def dispatch(self, context):
            for handler in reversed(tuple(routes.values())):
                if handler(self, context):
                    return
            original(self, context)
        dispatch._bbe_header_routes = routes
        dispatch._bbe_header_original = original
        setattr(header, method, dispatch)
    routes[owner] = draw


def remove(header, method, owner):
    current = getattr(header, method)
    routes = getattr(current, "_bbe_header_routes", None)
    if routes is not None:
        routes.pop(owner, None)
        if not routes:
            setattr(header, method, current._bbe_header_original)

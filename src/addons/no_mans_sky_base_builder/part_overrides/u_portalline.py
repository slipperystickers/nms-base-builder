from ..part_overrides import line
from ..utils import material


class U_PORTALLINE(line.Line):
    def __init__(self, *args, **kwargs):
        super(U_PORTALLINE, self).__init__(*args, **kwargs)
        from .. import cable_connections
        cable_connections.style(self.object)

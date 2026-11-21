"""The searchable, read-only How-To surface used by the sidebar and toolbar."""
from functools import lru_cache, partial

import blf
import unicodedata

from .. import i18n, curve_widgets as paint, menu_surface as ui
from ..build_editors import Editor, action, section
from .function_help import TOPICS


GROUPS = (
    ('Getting started', 'navigation', ('BBE','NAVIGATION','WORKSPACE','TOOLBAR','THEMES','ASSETS','STRIP')),
    ('Build and place', 'hammer', ('BUILDER','SNAP','REPEAT','DUPLICATE','ALIGN','TRANSFORM','BATCH','COLOUR','DECALS')),
    ('Shape and connect', 'spline', ('CURVES','SHAPES','TUBES','LOGIC','SELECTED_PART','PART_DISPLAY','PILOT')),
    ('Inspect and share', 'scan', ('CUTAWAY','BOUNDARY','LIGHTING','PREFABS','CHAT')),
    ('Save and recover', 'save', ('IO','SAVE_MANAGER','PICK_SHIP','EXPORT','SHIP_FILE','COCKPIT','OPTIMIZER','RECOVERY','REPAIR','REPLACE','SUPPORT')),
)


@lru_cache(maxsize=6)
def search_index(locale):
    index = []
    for key, (title, steps) in TOPICS.items():
        for step, (heading, body) in enumerate(steps):
            terms = (title, heading, body)
            translated = (i18n.for_locale(locale, text) for text in terms)
            index.append((key, step, heading, ' '.join((*terms, *translated)).casefold()))
    return tuple(index)


def article_lines(text, width, scale):
    """Wrap at measured glyph widths, including Chinese paragraphs without spaces."""
    blf.size(0, 14 * scale)
    line = ''
    word_break = 0
    for char in text:
        if unicodedata.east_asian_width(char) in {'W', 'F'} and not unicodedata.category(char).startswith('P'):
            word_break = len(line)
        if char.isspace():
            word_break = len(line) + 1
        if line and blf.dimensions(0, line + char)[0] > width:
            cut = word_break or len(line)
            yield line[:cut].rstrip()
            line = line[cut:].lstrip()
            word_break = 0
        if line or not char.isspace():
            line += char
    if line:
        yield line


class GuideBrowser(Editor):
    menu = 'HOW_TO'
    preferred_width = 660
    header_icon = 'circle-help'

    def __init__(self, owner):
        super().__init__(owner)
        self.title = 'How-To Guide'
        self.topic = None if owner.browse else owner.topic
        self.step = owner.section if owner.source_topic == self.topic else -1
        self.offsets = {}
        self.category = None

    def rebuild(self, context):
        super().rebuild(context)
        self.region_size = self.region.width, self.region.height
        self.position_limits = (self.region.width / self.scale - self.width - 8,
                                self.region.height / self.scale - 12)
        if self.workspace_position is not None:
            # A tall article may need more room. Keep the user's anchor for shorter pages.
            self.left, self.top = self.clamped_position(*self.workspace_position)
            self.hover = self.hit_test(*self.mouse)

    def needs_refresh(self, context):
        return self.region_size != (self.region.width, self.region.height)

    def open_category(self, key):
        self.category = key
        self.select(None)

    def select(self, topic, step=-1):
        self.topic, self.step = topic, step
        self.scroll = 0

    def body(self, context, root, ceiling):
        if self.topic is not None:
            self.article(root)
            return
        op = self.modal_owner
        root.prop(op.properties, 'query', text='', placeholder=i18n.interface('Search the guide'),
                  live_search='guides', height=34)
        words = op.query.casefold().split()
        if words:
            previous = None
            for key, index, heading, searchable in search_index(i18n.interface_locale()):
                if all(word in searchable for word in words):
                    if previous != key:
                        section(root, TOPICS[key][0], 'search')
                        previous = key
                    action(root, heading, partial(self.select, key, index),
                           outline='chevron-right', height=27)
            if previous is None:
                root.label(text=i18n.interface('No matching guides'))
            return

        if self.category is None:
            for category, icon, _ in GROUPS:
                action(root, category, partial(self.open_category, category),
                       outline=icon, height=36, secondary=True)
            return

        action(root, 'Back to guides', partial(self.open_category, None),
               outline='chevron-left', height=27)
        category, icon, topics = next(group for group in GROUPS if group[0] == self.category)
        section(root, category, icon)
        columns = 2 if self.width >= 520 else 1
        for index, key in enumerate(topics):
            if index % columns == 0:
                row = root.row(equal=True, gap=7)
            action(row, TOPICS[key][0], partial(self.select, key),
                   outline='chevron-right', height=29)

    def article(self, root):
        action(root, self.category if self.category and not self.modal_owner.query else 'Back to guides',
               partial(self.select,None), outline='chevron-left', height=28)
        title, steps = TOPICS[self.topic]
        section(root, title, self.header_icon)
        if 0 <= self.step < len(steps):
            action(root,'Show all steps',partial(self.select,self.topic),outline='layers',height=26)
            steps = (steps[self.step],)
        for heading, body in steps:
            root.label(text=i18n.interface(heading), height=31, guide_heading=True)
            for line in article_lines(i18n.interface(body), (self.width - 42) * self.scale, self.scale):
                root.label(text=line, height=19, guide_line=True)

    def paint_node(self, node, rect):
        if node.options.get('guide_heading') or node.options.get('guide_line'):
            x, y, _, height = rect
            s = self.scale
            color = ui.ACCENT if node.options.get('guide_heading') else ui.TEXT
            paint.text(ui.leaf_text(node), x+5*s, y+height/2-5*s, 14*s, color)
            return
        super().paint_node(node, rect)

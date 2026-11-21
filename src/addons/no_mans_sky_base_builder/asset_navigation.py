"""Navigation for the detached asset grid, in the grid's own window region."""
from functools import lru_cache

from . import i18n


def mix(a, b, amount):
    return tuple(x + (y-x)*amount for x,y in zip(a[:3], b[:3])) + (1.0,)


@lru_cache(maxsize=16)
def navigation_palette(surface, raised, accent, text):
    """Use the active theme's panel and header swatches for the large surfaces."""
    return {
        'body': surface,
        'library': mix(surface, raised, .35),
        'header': raised,
        'rule': mix(raised, text, .22),
        'hairline': mix(surface, text, .10),
        'branch': mix(surface, raised, .26),
        'heading': text,
        'label': mix(surface, text, .81),
        'secondary': mix(surface, text, .72),
        'control': mix(raised, text, .11),
        'hover': mix(raised, accent, .23),
        'selected': mix(surface, accent, .42),
        'marker': mix(accent, text, .32),
    }


class BrowserNavigation:
    def __init__(self):
        self.editing = False
        self.offset = 0
        self.limit = 0
        self.hover = self.pressed = None
        self.hits = []
        self.width = self.height = 0
        self.collapsed = None
        self.focus = None

    @staticmethod
    def pane_width(width, scale):
        return int(min(230 * scale, width * .29))

    def draw(self, grid, width, height, footer, state):
        categories, category, groups, group, mode, pinned = state
        scale = grid._scale
        theme = grid._palette
        colors = navigation_palette(theme['background'], theme['footer'], theme['accent'], theme['text'])
        pane = self.width = self.pane_width(width, scale)
        self.height = height - footer
        self.hits.clear()
        row = 26 * scale
        margin = 7 * scale
        edge = pane - margin
        grid.rectangle(0, footer, pane, self.height, colors['body'])
        grid.rectangle(0, height-4*row-5*scale, pane, 4*row+5*scale, colors['library'])
        grid.rectangle(pane-scale, footer, scale, self.height, colors['rule'])

        def button(action, label, x, top, w, h, *, active=False, inset=7, button_bg=False):
            if w <= 0:
                return
            self.hits.append((x, top, w, h, action))
            hot = action == self.hover or active
            if hot or button_bg:
                grid.rectangle(x, height-top-h+scale, w, h-2*scale,
                               colors['selected'] if active else colors['hover'] if hot else colors['control'])
            if active:
                grid.rectangle(x, height-top-h+3*scale, 2*scale, h-6*scale, colors['marker'])
            ink = colors['secondary'] if action[0]=='group' else colors['label']
            grid.label(x+inset*scale, height-top-h*.66, i18n.interface(label),
                       max(1,w-(inset+2)*scale), 11, colors['heading'] if hot else ink)

        def heading(text, top):
            grid.rectangle(0, height-top-row, pane-scale, row, colors['header'])
            grid.rectangle(0, height-top-row, pane-scale, scale, colors['rule'])
            grid.label(margin+5*scale, height-top-18*scale, i18n.interface(text),
                       max(1,edge-margin), 13, colors['heading'])

        heading('Library', 0)
        top = row
        for key, text in [('fav','Favourites'), ('recent','Recent'), ('preset','Presets')]:
            button(('mode', key), {'fav':'♡','recent':'◷','preset':'◇'}[key]+'   '+i18n.interface(text), margin, top, edge-margin, row, active=mode==key)
            top += row
        top += 5*scale
        grid.rectangle(0, height-top, pane-scale, scale, colors['rule'])
        heading('Categories', top)
        edit_width = min(63*scale, pane*.33)
        button(('edit',''), 'Done' if self.editing else 'Reorder',
               edge-edit_width, top, edit_width, row, button_bg=True)
        top += row+4*scale

        if self.editing:
            button(('reset',''), 'Reset to A–Z', margin, top, edge-margin, row, button_bg=True)
            top += row+2*scale
        if self.focus and category != self.focus[0]:
            self.collapsed = None
        rows = []
        for index, name in enumerate(categories):
            rows.append(('category', name, index))
            if not self.editing and mode=='asset' and name==category and self.collapsed!=name:
                rows.extend(('group', key, 0) for key in groups)
        count = max(0, int((self.height-top-margin)/row))
        self.limit = max(0, len(rows)-count)
        self.offset = min(self.offset, self.limit)
        focus = (category, group, mode, self.editing)
        if focus != self.focus:
            self.focus = focus
            target = ('group',group) if not self.editing and mode=='asset' and self.collapsed!=category else ('category',category)
            index = next((i for i,item in enumerate(rows) if item[:2]==target),None)
            if count and index is not None and not self.offset <= index < self.offset+count:
                self.offset = min(self.limit, max(0,index-count//2))
        for kind, key, index in rows[self.offset:self.offset+count]:
            selected = mode=='asset' and (key==category if kind=='category' else key==group)
            arrow_w = min(25*scale, pane*.12)
            w = edge-margin - (2*arrow_w if self.editing else 0)
            expanded = not self.editing and mode=='asset' and key==category and self.collapsed!=key
            label = i18n.interface('All' if kind=='group' and key=='ALL' else key)
            if kind=='category':
                label = ('▾  ' if expanded else '▸  ') + ('★ ' if key in pinned else '') + label
            if kind=='category':
                grid.rectangle(margin, height-top, edge-margin, scale, colors['hairline'])
            else:
                grid.rectangle(margin, height-top-row, edge-margin, row, colors['branch'])
                grid.rectangle(margin+8*scale, height-top-row, scale, row, colors['rule'])
            # The selected subcategory gets the filled row. Mark its parent
            # with a narrow accent so it is clear which choice filters the grid.
            button((kind,key), label, margin, top, w, row, active=selected and not expanded,
                   inset=6 if kind=='category' else 22)
            if selected and expanded:
                grid.rectangle(margin, height-top-row+3*scale, 3*scale, row-6*scale, colors['marker'])
            if self.editing:
                for step, action, symbol in [(-1,'up','↑'),(1,'down','↓')]:
                    neighbor=index+step
                    if 0<=neighbor<len(categories) and (key in pinned)==(categories[neighbor] in pinned):
                        x=edge-(2 if step<0 else 1)*arrow_w
                        button((action,key), symbol, x, top, arrow_w-scale, row, button_bg=True)
            top += row
        if count and self.limit:
            track=count*row
            thumb=max(10*scale,track*count/len(rows))
            pos=(track-thumb)*self.offset/self.limit
            grid.rectangle(pane-4*scale,height-(top-track)-pos-thumb,3*scale,thumb,colors['rule'])

    def event(self, grid, context, event, x, y, dispatch):
        inside = 0 <= x < self.width and 0 <= y < self.height
        hit = next((action for l,t,w,h,action in self.hits if l<=x<l+w and t<=y<t+h),None) if inside else None
        if self.hover != hit:
            self.hover = hit
            grid._area.tag_redraw()
        if self.pressed and event.type=='LEFTMOUSE' and event.value=='RELEASE':
            pressed, self.pressed = self.pressed, None
            if hit==pressed:
                action, key = hit
                if action=='edit':
                    self.editing = not self.editing
                else:
                    dispatch(context,self,action,key)
                grid._area.tag_redraw()
            return True
        if not inside or grid._drag:
            return False
        if grid._hover:
            grid._hover = None
            grid._area.tag_redraw()
        if event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE','TRACKPADPAN'}:
            delta = (1 if event.type=='WHEELDOWNMOUSE' else -1)
            if event.type=='TRACKPADPAN':
                delta = 1 if event.mouse_y<event.mouse_prev_y else -1
            self.offset = min(self.limit,max(0,self.offset+delta))
            grid._area.tag_redraw()
        if event.type=='LEFTMOUSE' and event.value=='PRESS':
            self.pressed = hit
            grid._pressed = None
        return event.type in {'MOUSEMOVE','INBETWEEN_MOUSEMOVE','LEFTMOUSE','RIGHTMOUSE',
                              'WHEELUPMOUSE','WHEELDOWNMOUSE','TRACKPADPAN','MIDDLEMOUSE'}

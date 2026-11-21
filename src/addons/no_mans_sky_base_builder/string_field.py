"""Single-line text input for graphical Blender menus."""
import blf
from . import curve_widgets as paint, menu_surface as ui


def handle_key(edit, context, event):
    value = edit["text"]
    lo, hi = sorted((edit["anchor"], edit["caret"]))
    if event.ctrl and event.type == 'A':
        edit.update(anchor=0, caret=len(value))
    elif event.type in {'LEFT_ARROW','RIGHT_ARROW','HOME','END'}:
        if event.type == 'HOME':
            caret = 0
        elif event.type == 'END':
            caret = len(value)
        elif lo != hi and not event.shift:
            caret = lo if event.type == 'LEFT_ARROW' else hi
        else:
            caret = max(0, min(len(value), edit['caret'] + (-1 if event.type == 'LEFT_ARROW' else 1)))
        edit['caret'] = caret
        if not event.shift:
            edit['anchor'] = caret
    else:
        replacement = None
        if event.ctrl and event.type in {'C', 'X'}:
            if hi != lo:
                context.window_manager.clipboard = value[lo:hi]
                if event.type == 'X':
                    replacement = ''
        elif event.ctrl and event.type == 'V':
            replacement = context.window_manager.clipboard.replace('\r','').replace('\n',' ')
        elif event.type in {'BACK_SPACE','DEL'}:
            if lo == hi and event.type == 'BACK_SPACE':
                lo = max(0, lo - 1)
            elif lo == hi:
                hi = min(len(value), hi + 1)
            replacement = ''
        elif event.unicode and not event.ctrl and not event.alt:
            replacement = event.unicode
        if replacement is not None:
            value = value[:lo] + replacement + value[hi:]
            edit.update(text=value, anchor=lo+len(replacement), caret=lo+len(replacement))


def draw(edit, shader, s, x, y, w, h):
    blf.size(0, 13*s)
    value, caret = edit['text'], edit['caret']
    left, available = x+7*s, max(8, w-16*s)
    # Keep the insertion point in view for long platform IDs.
    first = 0
    while first < caret and blf.dimensions(0,value[first:caret])[0] > available-2*s:
        first += 1
    visible = value[first:]
    while visible and blf.dimensions(0,visible)[0] > available:
        visible = visible[:-1]
    def position(i):
        return left + blf.dimensions(0,visible[:max(0, i-first)])[0]
    lo, hi = sorted((position(edit['anchor']), position(caret)))
    if hi > lo:
        paint.rounded(shader, lo,y+6*s,hi-lo,h-12*s,2*s,ui.HOVER)
    paint.text(visible,left,y+h/2-4*s,13*s,ui.TEXT)
    px = position(caret)
    paint.line(shader,(px,y+8*s),(px,y+h-8*s),1.3*s,ui.ACCENT)


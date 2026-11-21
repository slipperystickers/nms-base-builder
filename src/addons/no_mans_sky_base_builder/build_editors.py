"""Viewport editors for Corvette export order and build ownership."""
import colorsys
import hashlib
from functools import partial

import bpy
import blf

from . import curve_widgets as paint, icons, menu_surface as ui, i18n
from .save_editor import optimizer_core
from . import string_field


# Category identity is independent of where a user puts the category in the list.
CATEGORY_COLORS = {
    'Rockhopper Wing': (0.83, 0.57, 0.98), 'Generators': (0.28, 0.81, 0.91),
    'Thrusters': (0.98, 0.61, 0.32), 'Weapon Turrets': (0.99, 0.43, 0.47),
    'Shield Units': (0.39, 0.63, 1.0), 'Landing Gear': (0.49, 0.83, 0.55),
    'Landing Bay': (0.91, 0.76, 0.32), 'Cockpit': (0.98, 0.55, 0.79),
}


def category_color(name):
    if name in CATEGORY_COLORS:
        return CATEGORY_COLORS[name]
    seed = int.from_bytes(hashlib.sha256(name.casefold().encode()).digest()[:4], 'big')
    return colorsys.hsv_to_rgb(seed / 2**32, .52, .94)


def membership(pid, categories):
    if pid in categories:
        name = categories[pid]
        return name, category_color(name)
    if pid == 'U_PARAGON':
        return 'Last by default', (.73, .73, .76)
    if pid in optimizer_core.ORANGE_IDS:
        return 'Orange tier', (1., .61, .25)
    if pid in optimizer_core.RED_IDS:
        return 'Red tier', (.98, .43, .47)
    return 'Unlisted', (.69, .72, .76)


def contrast_color(rgb, background):
    def luminance(c):
        linear = [s / 12.92 if s < .04045 else ((s + .055) / 1.055) ** 2.4 for s in c[:3]]
        return sum(v * k for v, k in zip(linear, (.2126, .7152, .0722)))
    lum = luminance(background)
    target = (0., 0., 0., 1.) if lum > .179 else (1., 1., 1., 1.)
    color = (*rgb, 1.)
    for _ in range(12):
        a, b = sorted((luminance(color), lum))
        if (b + .05) / (a + .05) >= 4.5:
            break
        color = paint.mix(color, target, .19)
    return color


def action(parent, text, callback, **options):
    return parent.child('action', text=i18n.interface(text), callback=callback, **options)


def section(layout, text, symbol=None):
    layout.label(text=i18n.interface(text), section=True, section_icon=symbol, height=31 if symbol else 23)


class Editor(ui.MenuSurface):
    anchor_x = anchor_y = -1
    menu = 'BUILD_EDITOR'
    anchor_center = True

    def __init__(self, owner):
        self.modal_owner = owner
        self.title = i18n.interface(owner.bl_label)
        self.closed = False

    def rebuild(self, context):
        ui.use_theme(context)
        self.width = min(self.preferred_width, max(200, self.region.width / self.scale - 20))
        ceiling = self.region.height / self.scale - 12
        self.root = ui.Layout()
        self.body(context, self.root, ceiling)
        self.leaves, self.content_height = ui.layout_tree(self.root, self.width - 24)
        for node, _ in self.leaves:
            node.can_click = node.is_enabled()
        self.header_help = self.header_count = None
        self.height = min(self.content_height + 68, max(100, ceiling - 8))
        self.scroll = min(self.scroll, max(0, self.content_height + 68 - self.height))
        self.left = (self.region.width / self.scale - self.width) / 2
        self.top = (ceiling + self.height + 8) / 2
        self.hover = self.hit_test(*self.mouse)
        self.area.tag_redraw()

    def footer(self, root, label):
        root.separator()
        bar = root.row(gap=8, equal=True)
        action(bar, 'Cancel', self.finish, secondary=True, center=True)
        action(bar, label, self.apply, primary=True, outline='check', center=True)

    def apply(self):
        self.result = self.modal_owner.execute(bpy.context)
        self.finish()

    def activate(self, node, context):
        if node.kind == 'action' and node.can_click:
            node.options['callback']()
            if self.closed:
                return getattr(self, 'result', {'CANCELLED'})
            self.rebuild(context)
            return {'RUNNING_MODAL'}
        if node.options.get('choices'):
            self.open_choices(node, node.options['choices'], lambda v: self.set_property(node, v))
            return {'RUNNING_MODAL'}
        if node.kind == 'prop':
            data, key = node.options['data'], node.options['key']
            if data.bl_rna.properties[key].type == 'STRING':
                value = getattr(data, key)
                self.edit = dict(node=node, text=value, original=value, anchor=0, caret=len(value))
                self.area.tag_redraw()
                return {'RUNNING_MODAL'}
        return super().activate(node, context)

    def set_property(self, node, value):
        setattr(node.options['data'], node.options['key'], value)
        self.edit = self.dropdown = None
        self.rebuild(bpy.context)

    def edit_event(self, context, event):
        if event.value != 'PRESS':
            return {'RUNNING_MODAL'}
        edit = self.edit
        node, value = edit['node'], edit['text']
        key = node.options['key']
        if event.type == 'ESC':
            self.set_property(node, edit['original'])
        elif event.type in {'RET','NUMPAD_ENTER','TAB','LEFTMOUSE'}:
            fields = [n.options['key'] for n, _ in self.leaves if n.kind == 'prop'
                      and n.options['data'].bl_rna.properties[n.options['key']].type == 'STRING']
            self.set_property(node, value)
            if event.type == 'TAB':
                following = fields[(fields.index(key) + (-1 if event.shift else 1)) % len(fields)]
                next_node = next(n for n, _ in self.leaves if n.kind == 'prop' and n.options['key'] == following)
                self.activate(next_node, context)
            if event.type == 'LEFTMOUSE':
                return None  # Deliver the click to its new field or button too.
        else:
            string_field.handle_key(edit, context, event)
            if edit['text'] != value and node.options.get('live_search'):
                setattr(node.options['data'], key, edit['text'])
                self.offsets[node.options['live_search']] = 0
                self.rebuild(context)
                edit['node'] = next(n for n, _ in self.leaves if n.options.get('live_search'))
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def draw_edit_text(self, x, y, w, h):
        string_field.draw(self.edit, self.shader, self.scale, x, y, w, h)

    def paint_node(self, node, rect):
        symbol = node.options.get('section_icon')
        if not symbol:
            return super().paint_node(node, rect)
        x,y,w,h = rect
        s = self.scale
        ui.draw_image(ui.outline_icon(symbol), x+3*s,y+(h-19*s)/2,19*s,19*s)
        paint.text(ui.leaf_text(node), x+30*s,y+h/2-5*s,14*s,ui.TEXT)
        blf.size(0,14*s)
        start = x+40*s+blf.dimensions(0,ui.leaf_text(node))[0]
        if start < x+w-4*s:
            paint.line(self.shader,(start,y+h/2),(x+w-4*s,y+h/2),s,ui.EDGE)

    def handle_event(self, context, event):
        if self.closed:
            return {'CANCELLED'}
        if context.scene != self.scene or self.area.type != 'VIEW_3D':
            self.finish()
            return {'CANCELLED'}
        if self.edit and event.type != 'WINDOW_DEACTIVATE':
            result = self.edit_event(context,event)
            if result is not None:
                return result
        if event.type == 'TIMER' and not self.edit and not self.dropdown:
            if self.needs_refresh(context):
                self.rebuild(context)
        result = super().handle_event(context, event)
        if self.closed and 'FINISHED' in result and not hasattr(self, 'result'):
            return (result - {'FINISHED'}) | {'CANCELLED'}
        return result

    def needs_refresh(self, context):
        return False

    def finish(self):
        if self.closed:
            return
        self.closed = True
        super().finish()
        self.modal_owner.cancel(bpy.context)

    def report(self, level, message):
        self.modal_owner.report(level, message)


def open_editor(owner, context, event, editor_type, width, confirm):
    if getattr(getattr(context, 'area', None), 'type', None) != 'VIEW_3D' or bpy.app.background:
        return context.window_manager.invoke_props_dialog(owner, width=width, confirm_text=confirm)
    editor = editor_type(owner)
    owner._editor = editor
    editor.scene = context.scene
    try:
        return editor.invoke(context, event)
    except Exception:
        owner.cancel(context)
        raise


class BackupFolderEditor(Editor):
    preferred_width = 570
    header_icon = 'folder-cog'
    browsing = False
    error = ''

    def body(self, context, root, ceiling):
        op = self.modal_owner
        section(root, 'Backup location', 'folder-open')
        path = root.row(factor=.77, gap=6)
        path.prop(op.properties, 'folder', text='', placeholder=op._default_folder,
                  tip=op.folder or op._default_folder, height=36)
        action(path, 'Browse…', self.browse, outline='folder-open', secondary=True, height=36)
        row = root.row(factor=.73)
        changed_folder = op.folder.strip() != op._original_folder
        row.label(text='Existing backups stay in the previous folder.' if changed_folder
                  else 'Projects and game saves use separate subfolders.')
        reset = action(row, 'Use default', self.reset_folder, outline='rotate-ccw')
        reset.enabled = bool(op.folder.strip())
        section(root, 'Game-save history', 'history')
        row = root.row(factor=.70)
        row.label(text='Backups to keep per save slot')
        count = row.row(equal=True)
        action(count, '−', partial(self.step, -1), secondary=True, center=True,
               tip='Keep one fewer backup').enabled = self.count() > 1
        count.prop(op.properties, 'retention_input', text='', tip='Enter a number from 1 to 500')
        action(count, '+', partial(self.step, 1), secondary=True, center=True,
               tip='Keep one more backup').enabled = self.count() < 500
        hint = self.error or 'Each backup is a complete copy of that slot’s save files.'
        root.label(text=hint, tip=hint, notice=bool(self.error)).alert = bool(self.error)
        self.footer(root, 'Save settings')

    def count(self):
        value = self.modal_owner.retention_input.strip()
        return int(value) if value.isascii() and value.isdecimal() and len(value) <= 3 else 0

    def step(self, delta):
        self.modal_owner.retention_input = str(max(1, min(500, self.count() + delta)))
        self.error = ''

    def reset_folder(self):
        self.modal_owner.folder = ''
        self.error = ''

    def browse(self):
        bpy.ops.bbe.choose_backup_folder('INVOKE_DEFAULT')

    def handle_event(self, context, event):
        if self.browsing and not self.closed:
            return {'PASS_THROUGH'}
        return super().handle_event(context, event)

    def apply(self):
        op = self.modal_owner
        count = self.count()
        if not 1 <= count <= 500:
            self.error = 'Enter a backup count from 1 to 500.'
            return
        op.retention = count
        result = op.execute(bpy.context)
        if result == {'FINISHED'}:
            self.result = result
            self.finish()

    def set_property(self, node, value):
        self.error = ''
        super().set_property(node, value)


class MetadataEditor(Editor):
    preferred_width = 550
    header_icon = 'pencil-line'

    def body(self, context, root, ceiling):
        op = self.modal_owner
        data = op.properties
        section(root, 'Build owner', 'house')
        root.prop(data, 'owner_usn', text='Owner name', placeholder='USN')
        root.prop(data, 'owner_uid', text='User ID', placeholder='UID')
        pair = root.row(equal=True)
        pair.prop(data, 'owner_lid', text='LID')
        pair.prop(data, 'owner_ptk', text='PTK')
        root.prop(data, 'owner_ts', text='Timestamp', placeholder='TS')
        root.prop(data, 'copy_owner', text='Copy owner from a saved Corvette')
        if op.copy_owner:
            field = root.prop(data, 'owner_donor', text='Source Corvette')
            field.options['choices'] = op._donor_items
            if op._donor_error:
                root.label(text=op._donor_error, notice=True).alert = True
        section(root, 'Last editor', 'pencil-line')
        root.prop(data, 'last_editor_name', text='Player name')
        root.prop(data, 'last_editor_id', text='Player ID')
        section(root, 'Game-save export', 'upload')
        root.prop(data, 'owner_to_save', text='Include this owner on export')
        root.label(text=i18n.interface('Export will update the destination owner.' if op.owner_to_save
                                       else 'The destination keeps its current owner.'), height=23)
        self.footer(root, 'Apply to build')


class PagedEditor(Editor):
    def list_rows(self, parent, key, indices, count, draw):
        last = max(0, len(indices) - count)
        index = self.follow.pop(key, None)
        if index is not None and index in indices:
            at = indices.index(index)
            self.offsets[key] = max(at-count+1, min(at, self.offsets[key]))
        offset = self.offsets[key] = min(last, max(0, self.offsets[key]))
        for index in indices[offset:offset + count]:
            draw(index).options['scroll_key'] = key
        if not indices:
            parent.label(text=i18n.interface('No matching parts'), empty=True)
        if last:
            bar = parent.row()
            for delta, symbol in ((-count, '‹'), (count, '›')):
                if delta > 0:
                    bar.label(text=f'{offset + 1} – {min(len(indices), offset + count)} / {len(indices)}',
                              height=23)
                n = action(bar, symbol, partial(self.scroll_list, key, delta), center=True,
                           secondary=True, width=38, height=24)
                n.enabled = offset > 0 if delta < 0 else offset < last
        self.lists[key] = (indices, count)

    def scroll_list(self, key, delta):
        self.offsets[key] += delta

    def handle_event(self, context, event):
        if not self.edit and not self.dropdown and event.type in {'WHEELUPMOUSE','WHEELDOWNMOUSE'}:
            hit = self.hit_test(event.mouse_x-self.region.x, event.mouse_y-self.region.y)
            key = hit.options.get('scroll_key') if hit else None
            if key and len(self.lists[key][0]) > self.lists[key][1]:
                self.scroll_list(key, -1 if event.type == 'WHEELUPMOUSE' else 1)
                self.rebuild(context)
                return {'RUNNING_MODAL'}
        return super().handle_event(context, event)


class SwapOrderEditor(PagedEditor):
    preferred_width = 620
    header_icon = 'arrow-left-right'
    menu = 'SWAP_ORDER'

    def __init__(self, owner):
        super().__init__(owner)
        from .save_editor.corvette_optimizer import group_choices
        self.groups = [(pid, label.removesuffix(f' ({pid})')) for pid, _, label in group_choices(owner, None)]
        self.group_names = dict(self.groups)
        self.page = None
        self.parent = None
        self.offsets = {'choices': 0}
        self.follow = {}
        self.lists = {}

    def invoke(self, context, event):
        # Keep the optimizer draft, its scroll position and its own Apply/Cancel
        # boundary alive while the user makes this separate scene edit.
        key = context.area.as_pointer()
        parent = ui._sessions.get(key)
        if isinstance(parent, OptimizerEditor):
            self.parent = parent
            parent.swap_editor = self
            return self.begin_surface(context, event, (key, self.menu))
        return super().invoke(context, event)

    def apply(self):
        from .save_editor.corvette_optimizer import ship_instances
        parent = self.parent
        def sources():
            return [(obj.session_uid, child, pid) for obj, child, pid in ship_instances()]
        current = parent and not parent.closed and parent.modal_owner._sources == sources()
        super().apply()
        if current and self.result == {'FINISHED'}:
            parent.modal_owner._sources = sources()

    def finish(self):
        super().finish()
        if self.parent:
            self.parent.swap_editor = None
            if not self.parent.closed:
                self.parent.area.tag_redraw()

    def show_page(self, page):
        self.page = page
        self.modal_owner.search = ''
        self.scroll = self.offsets['choices'] = 0
        if page in {'first','second'}:
            self.follow['choices'] = int(getattr(self.modal_owner, page))
        elif page == 'type':
            self.follow['choices'] = next(i for i, (pid, _) in enumerate(self.groups)
                                          if pid == self.modal_owner.object_type)

    def choose(self, value):
        op = self.modal_owner
        if self.page == 'type':
            if op.object_type != value:
                op.object_type = value
        else:
            setattr(op, self.page, str(value))
        self.show_page(None)

    @staticmethod
    def position(xyz):
        return '    '.join(f'{axis} {v:.2f}' for axis, v in zip('XYZ', xyz))

    def card(self, root, title, detail, pid, badge, callback, **options):
        return action(root, title, callback, pid=pid, detail=detail, badge=badge,
                      swap_card=True, height=62, tip=f'{title}   {detail}', **options)

    def body(self, context, root, ceiling):
        op = self.modal_owner
        rows = op._placed[op.object_type]
        if self.page:
            typ = self.page == 'type'
            section(root, 'Choose a part type' if typ else f'Choose the {self.page} object', 'search')
            root.prop(op.properties, 'search', text='', live_search='choices',
                      placeholder='Search by part name or Object ID' if typ else 'Search by object name, ID or scene slot')
            query = op.search.strip().casefold()
            if typ:
                indices = [i for i, (pid, label) in enumerate(self.groups) if
                           query in f'{label} {pid}'.casefold() or
                           (pid == 'COCKPITS' and any(query in row[1].casefold() for row in op._placed[pid]))]
            else:
                indices = [i for i, (name, pid, slot, xyz) in enumerate(rows)
                           if query in f'{name} {pid} #{slot}'.casefold()]
            def draw(index):
                if typ:
                    group, label = self.groups[index]
                    members = op._placed[group]
                    return self.card(root, label, 'Cockpit variants' if group == 'COCKPITS' else group,
                                     members[0][1], f'{len(members)} objects', partial(self.choose, group),
                                     selected=group == op.object_type, choice=group)
                name, pid, slot, xyz = rows[index]
                other = int(op.second if self.page == 'first' else op.first)
                node = self.card(root, name, f'{pid}     {self.position(xyz)}', pid,
                                 'Already paired' if index == other else f'Scene slot {slot}',
                                 partial(self.choose, index), selected=str(index) == getattr(op, self.page), choice=index)
                node.enabled = index != other
                return node
            count = max(2, min(7, int((ceiling-216)/64)))
            self.list_rows(root, 'choices', indices, count, draw)
            action(root, 'Back to swap', partial(self.show_page, None), secondary=True, center=True)
            return

        section(root, 'Part type', 'boxes')
        action(root, f'{self.group_names[op.object_type]}   ({len(rows)} objects)',
               partial(self.show_page, 'type'), outline='search', secondary=True, height=38,
               tip='Choose a different part type')
        section(root, 'Scene export order', 'arrow-left-right')
        for field, other in (('first', 'second'), ('second', 'first')):
            name, pid, slot, xyz = rows[int(getattr(op, field))]
            target = rows[int(getattr(op, other))][2]
            self.card(root, name, f'{pid}     {self.position(xyz)}', pid,
                      f'Slot {slot} to {target}', partial(self.show_page, field), change=field)
        root.label(text='Click either object to change it. Positions in the viewport stay fixed.')
        if context.scene.bbe_optimizer_order:
            root.label(text='Optimize & Export uses the manual order saved for this build.', notice=True)
        row = root.row()
        row.label(text='Ctrl+Z undoes the swap. Save the .blend to keep it.')
        action(row, 'How this works', self.help, outline='circle-help', width=145)
        self.footer(root, 'Swap order')

    def help(self):
        bpy.ops.bbe.function_help('INVOKE_DEFAULT', topic='COCKPIT')

    def handle_event(self, context, event):
        if self.page and not self.edit and event.type == 'ESC' and event.value == 'PRESS':
            self.show_page(None)
            self.rebuild(context)
            return {'RUNNING_MODAL'}
        return super().handle_event(context, event)

    def paint_node(self, node, rect):
        o = node.options
        if not o.get('swap_card'):
            return super().paint_node(node, rect)
        x,y,w,h = rect
        s = self.scale
        hot = node.can_click and self.hover == node
        bg = ui.HOVER if hot or o.get('selected') else ui.SURFACE
        paint.rounded(self.shader,x,y,w,h,7*s,bg)
        art = h-8*s
        previews = icons.get_asset_icons_pcoll()
        preview = previews.get(o['pid']) if previews is not None else None
        if preview:
            ui.draw_image(preview.icon_id,x+6*s,y+4*s,art,art,preview=preview)
        else:
            ui.draw_image(ui.outline_icon('box'),x+12*s,y+10*s,art-12*s,art-12*s)
        left = x+art+15*s
        badge = o['badge']
        blf.size(0,12*s)
        bw = min(w*.34,blf.dimensions(0,badge)[0]+18*s)
        bx = x+w-bw-9*s
        paint.rounded(self.shader,bx,y+(h-23*s)/2,bw,23*s,7*s,paint.mix(bg,ui.TEXT,.08))
        paint.text(ui.trim(badge,bw-8*s,12*s),bx+bw/2,y+h/2-4*s,12*s,ui.MUTED,'CENTER')
        paint.text(ui.trim(o['text'],max(4*s,bx-left-6*s),15*s),left,y+h/2+3*s,15*s,
                   ui.TEXT if node.can_click else ui.MUTED)
        paint.text(ui.trim(o['detail'],max(4*s,bx-left-6*s),12*s),left,y+h/2-15*s,12*s,ui.MUTED)


class OptimizerEditor(PagedEditor):
    preferred_width = 720
    header_icon = 'rocket'

    def __init__(self, owner):
        super().__init__(owner)
        self.offsets = dict(instances=0, groups=0, parts=0)
        self.follow = {}

    def draw_surface(self):
        if not getattr(self, 'swap_editor', None):
            super().draw_surface()

    def handle_event(self, context, event):
        if getattr(self, 'swap_editor', None) and not self.closed:
            return {'PASS_THROUGH'}
        return super().handle_event(context, event)

    def signature(self):
        state = self.state
        group = state.groups[state.active_group] if state.groups else None
        return (state.rules_revision, state.active_group, group.active_part if group else -1)

    def needs_refresh(self, context):
        signature = self.signature()
        if signature != self.last_signature:
            self.follow.update(groups=signature[1], parts=signature[2])
            return True
        return False

    def body(self, context, root, ceiling):
        self.state = context.window_manager.bbe_optimizer
        state = self.state
        self.last_signature = self.signature()
        tabs = root.row(equal=True, decor='segments')
        for key, label, outline in [('SHIP', 'Ship parts', 'rocket'), ('RULES', 'Priority rules', 'layers')]:
            action(tabs, label, partial(setattr, state, 'tab', key), depress=state.tab == key,
                   outline=outline, center=True, height=38)
        if state.tab == 'SHIP':
            self.ship(root, ceiling)
        else:
            self.rules(root, ceiling)
        self.footer(root, 'Apply settings')

    def run(self, identifier, mode='EXEC_DEFAULT', **kwargs):
        return ui.operation(identifier)(mode, **kwargs)

    def move(self, key, direction):
        state = self.state
        if key == 'instances':
            self.run('bbe.move_ship_instance', action=direction)
            self.follow[key] = state.active_instance
        else:
            self.run('bbe.optimizer_move', group=key == 'groups', direction=direction)
            self.follow[key] = state.active_group if key == 'groups' else state.groups[state.active_group].active_part

    def select(self, key, index):
        if key == 'groups':
            self.state.active_group = index
            self.offsets['parts'] = 0
        elif key == 'parts':
            self.state.groups[self.state.active_group].active_part = index
        else:
            self.state.active_instance = index

    def item(self, parent, key, index, name, detail, pid, category, selected, height):
        return action(parent, name, partial(self.select, key, index), entry=True, detail=detail,
                      pid=pid, category=category, selected=selected, height=height,
                      index=index, list_key=key, tip=' · '.join(filter(None, (name, detail, category[0]))))

    def ship(self, root, ceiling):
        from .save_editor.corvette_optimizer import instance_matches
        self.lists = {}
        s = self.state
        if not s.instances:
            root.label(text=i18n.interface('Import a Corvette or place a part to start ordering.'), empty=True)
            return
        header = root.row()
        header.label(text=(self.scene.nms_base_tool.string_base.strip() or i18n.interface('Current build'))
                     + f'  ·  {len(s.instances)}', section=True)
        header.label(text=i18n.interface('Manual order' if s.manual else 'Automatic order'), section=True)
        root.prop(s, 'search', text='', placeholder='Find a part name, Object ID or instance', live_search='instances')
        categories = {p.part_id: g.name for g in s.groups for p in g.parts}
        indices = [i for i, item in enumerate(s.instances) if instance_matches(item, s.search)]
        def draw(i):
            item = s.instances[i]
            instance = item.child or (item.owner.name if item.owner else '')
            detail = item.part_id + (f'   ·   {instance}' if instance and instance != item.part_id else '')
            return self.item(root, 'instances', i, item.name, detail, item.part_id,
                             membership(item.part_id, categories), i == s.active_instance, 61)
        count = max(2, min(7, int((ceiling - 320) / 63)))
        self.list_rows(root, 'instances', indices, count, draw)
        bar = root.row(equal=True)
        for key, label in [('FIRST', 'First'), ('UP', 'Up'), ('DOWN', 'Down'), ('LAST', 'Last')]:
            n = action(bar, label, partial(self.move, 'instances', key), secondary=True, center=True,
                       move_icon=key)
            n.enabled = (s.active_instance in indices and
                         (s.active_instance > 0 if key in {'FIRST','UP'} else s.active_instance < len(s.instances)-1))
        info = root.row()
        active = s.instances[s.active_instance]
        if active.owner and s.active_instance in indices:
            x, y, z = active.owner.matrix_world.translation
            info.label(text=active.owner.name if active.child else f'X {x:.2f}     Y {y:.2f}     Z {z:.2f}')
        reset = action(info, 'Use priority rules', partial(self.run, 'bbe.move_ship_instance', action='AUTO'),
                       outline='rotate-ccw', width=155)
        reset.enabled = s.manual

    def rules(self, root, ceiling):
        from . import BUILDER
        self.lists = {}
        s = self.state
        split = root.split(factor=.34, gap=12)
        left, right = split.column(), split.column()
        section(left, 'Categories')
        section(right, 'Parts in category')
        group = s.groups[s.active_group] if s.groups else None
        def category(i):
            g = s.groups[i]
            return self.item(left, 'groups', i, g.name, str(len(g.parts)), '', (g.name, category_color(g.name)),
                             i == s.active_group, 36)
        def part(i):
            pid = group.parts[i].part_id
            name = BUILDER.get_nice_name(pid)
            return self.item(right, 'parts', i, name.title() if name.isupper() else name, pid, pid,
                             (group.name, category_color(group.name)), i == group.active_part, 57)
        available = max(150, min(370, ceiling - 325))
        self.list_rows(left, 'groups', list(range(len(s.groups))), max(3, int(available / 38)), category)
        self.list_rows(right, 'parts', list(range(len(group.parts)) if group else ()), max(2, int(available / 59)), part)
        for column, key, entries, selected in ((left, 'groups', s.groups, s.active_group),
                (right, 'parts', group.parts if group else (), group.active_part if group else 0)):
            bar = column.row(equal=True)
            for direction, label in ((-1, 'Up'), (1, 'Down')):
                n = action(bar, label, partial(self.move, key, direction), center=True, secondary=True,
                           move_icon='UP' if direction < 0 else 'DOWN')
                n.enabled = 0 <= selected + direction < len(entries)
            def edit(row, label, command, enabled=True):
                button = action(row, label, partial(self.run, 'bbe.optimizer_edit', 'INVOKE_DEFAULT', action=command),
                                center=True, secondary=True)
                button.enabled = enabled
            edits = column.row(equal=True)
            if key == 'groups':
                edit(edits, 'Add', 'ADD_GROUP')
                edit(edits, 'Rename', 'RENAME_GROUP', bool(group))
                edit(column, 'Remove category', 'REMOVE_GROUP', bool(group))
            else:
                action(edits, 'Add part', partial(self.run, 'bbe.optimizer_choose_part','INVOKE_DEFAULT'),
                       center=True, secondary=True).enabled = bool(group)
                edit(edits, 'By ID', 'ADD_PART', bool(group))
                edit(edits, 'Remove part', 'REMOVE_PART', bool(entries))
        root.prop(s, 'delete_identical', text='Remove exact duplicates on export')
        row = root.row(equal=True)
        action(row, 'Reset rules', partial(self.run, 'bbe.optimizer_reset'), outline='rotate-ccw')
        action(row, 'Swap scene order…', partial(self.run, 'bbe.swap_corvette_cockpits','INVOKE_DEFAULT'), outline='arrow-left-right')
        action(row, 'Optimizer help', partial(self.run, 'bbe.function_help','INVOKE_DEFAULT',topic='OPTIMIZER'), outline='circle-help')

    def paint_node(self, node, rect):
        o = node.options
        if o.get('move_icon'):
            x,y,w,h = rect
            s = self.scale
            hot = self.hover is node and node.can_click
            paint.rounded(self.shader,x,y,w,h,6*s,ui.HOVER if hot else ui.SURFACE)
            text = ui.leaf_text(node)
            blf.size(0,14*s)
            cx = x+(w-blf.dimensions(0,text)[0]-9*s)/2
            cy = y+h/2
            ink = ui.TEXT if node.can_click else ui.MUTED
            dy = 4*s if o['move_icon'] in {'UP','FIRST'} else -4*s
            paint.line(self.shader,(cx-4*s,cy-dy/2),(cx,cy+dy),1.5*s,ink)
            paint.line(self.shader,(cx,cy+dy),(cx+4*s,cy-dy/2),1.5*s,ink)
            if o['move_icon'] in {'FIRST','LAST'}:
                paint.line(self.shader,(cx-4*s,cy+1.7*dy),(cx+4*s,cy+1.7*dy),1.5*s,ink)
            paint.text(text,cx+10*s,cy-4*s,14*s,ink)
            return
        if not o.get('entry'):
            return super().paint_node(node, rect)
        x,y,w,h = rect
        s = self.scale
        name, rgb = o['category']
        bg = paint.mix(ui.SURFACE, ui.PRIMARY, .28) if o['selected'] else ui.HOVER if self.hover is node else ui.SURFACE
        ink = contrast_color(rgb, bg)
        paint.rounded(self.shader, x,y,w,h,7*s,bg)
        paint.rounded(self.shader,x+2*s,y+6*s,4*s,h-12*s,2*s,(*rgb,1.))
        if o['list_key'] == 'groups':
            paint.text(ui.trim(name,w-52*s,13*s),x+12*s,y+h/2-5*s,13*s,ink)
            paint.text(o['detail'],x+w-9*s,y+h/2-4*s,11*s,ui.MUTED,'RIGHT')
            return
        left = x+10*s
        if o['list_key'] == 'instances':
            paint.text(str(o['index']+1),left+14*s,y+h/2-4*s,12*s,ui.MUTED,'CENTER')
            left += 32*s
        art = h-6*s
        previews = icons.get_asset_icons_pcoll()
        preview = previews.get(o['pid']) if previews is not None else None
        if preview:
            ui.draw_image(preview.icon_id,left,y+3*s,art,art,preview=preview)
        else:
            ui.draw_image(ui.outline_icon('box'),left+5*s,y+8*s,art-10*s,art-10*s)
        left += art+10*s
        room = x+w-left-10*s
        if o['list_key'] == 'instances' and room > 260*s:
            chip_w = min(150*s,room*.34)
            chip_x = x+w-chip_w-7*s
            chip_bg = paint.mix(bg, (*rgb,1.), .21)
            paint.rounded(self.shader,chip_x,y+h/2-12*s,chip_w,24*s,8*s,chip_bg)
            paint.text(ui.trim(i18n.interface(name),chip_w-12*s,12*s),chip_x+chip_w/2,y+h/2-4*s,
                       12*s,contrast_color(rgb,chip_bg),'CENTER')
            room -= chip_w+5*s
        elif o['list_key'] == 'instances':
            paint.text(ui.trim(name, room, 10*s), left, y+3*s, 10*s, ink)
        paint.text(ui.trim(o['text'],room,15*s),left,y+h/2+3*s,15*s,ui.TEXT)
        paint.text(ui.trim(o['detail'],room,12*s),left,y+h/2-15*s,12*s,ink)

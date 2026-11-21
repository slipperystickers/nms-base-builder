"""Inline graphical tools in the regular BBE sidebar."""
import ctypes
import math
import textwrap

import blf
import bpy
import gpu
from bpy.app.handlers import persistent

from types import SimpleNamespace

from . import i18n, menu_backend, menu_contract, menu_surface as ui

CATEGORY = 'No Mans Sky Base Builder'
INLINE_MENUS = ('builder', 'color', 'transform', 'batch', 'parts', 'cables', 'lighting', 'shapes', 'saves', 'io', 'recovery', 'proxies', 'support', 'transforms')
_views = {}
_keymaps = []
_handler = None


def walk(node):
    yield node
    for child in node.children:
        yield from walk(child)


def area_key(context):
    return context.window.as_pointer(), context.area.as_pointer()


class _PanelBounds51(ctypes.Structure):
    # Blender 5.1 DNA_screen_types.h, Panel through its block dimensions.
    # Access only during a native panel callback. The fold-state tracker
    # also uses PNL_CLOSED here. Never retain an RNA or native pointer.
    _fields_ = [(name, ctypes.c_void_p) for name in ('next', 'prev', 'type', 'layout')] + [
        ('panelname', ctypes.c_char * 64), ('drawname', ctypes.c_void_p),
        ('x', ctypes.c_int), ('y', ctypes.c_int),
        ('width', ctypes.c_int), ('height', ctypes.c_int),
        ('block_width', ctypes.c_int), ('block_height', ctypes.c_int),
        ('label_offset', ctypes.c_short), ('flags', ctypes.c_short)]


def native_panel(owner):
    owner = getattr(owner, '_owner', owner)
    if bpy.app.version[:2] != (5, 1) or not isinstance(owner, bpy.types.Panel):
        return None
    panel = _PanelBounds51.from_address(owner.as_pointer())
    name = owner.bl_idname.encode('ascii')
    if not panel.panelname.startswith(name) or panel.layout != owner.layout.as_pointer():
        return None
    return panel


def view_key(context, menu):
    return (*area_key(context), menu)


def begin_header(owner, context, menu='builder'):
    if context.region and context.region.type == 'UI' and isinstance(owner, bpy.types.Panel):
        view = _views.get(view_key(context, menu))
        if view:
            view.visible = False


def active_views(context):
    if (not _views or not context.area or context.area.type != 'VIEW_3D' or not context.window
            or context.mode != 'OBJECT' or not context.region or context.region.type != 'UI'
            or context.region.active_panel_category != CATEGORY):
        return
    from .tools_menu.base_builder_menu import _preferences
    prefs = _preferences(context)
    hidden = prefs.bbe_sidebar_hidden.split(',') if prefs else ()
    for menu in INLINE_MENUS:
        view = _views.get(view_key(context, menu))
        if view and view.visible and menu not in hidden:
            yield view


class InlineView(ui.MenuSurface):
    edit = None

    def __init__(self):
        self.hover = None
        self.pointer = None
        self.choice_key = None
        self.leaves = []
        self.visible = False

    def poll_operators(self, context):
        viewport = next(r for r in context.area.regions if r.type == 'WINDOW')
        with context.temp_override(region=viewport):
            for node, _ in self.leaves:
                node.can_click = node.is_enabled()
                if node.kind != 'operator':
                    continue
                identifier = node.options['identifier']
                node.can_click = node.can_click and ui.operation(identifier).poll()

    def rect(self, geom, node=None):
        x, top, width, height = geom
        return self.x + x*self.scale, self.top - (top+height)*self.scale, width*self.scale, height*self.scale

    def visible_row(self, node, rect):
        return rect[1] >= self.bottom - 1 and rect[1]+rect[3] <= self.top + 1

    def list_viewport(self, rect):
        return rect

    def visible_list_point(self, rect, y):
        return self.bottom <= y <= self.top

    def hit(self, x, y):
        for node, geom in reversed(self.leaves):
            rect = self.rect(geom,node)
            if (node.kind in {'operator','prop','enum_value','duplicate_menu','library_option','menu','panel'} and node.can_click
                    and self.visible_row(node,rect) and ui.inside(rect,x,y)):
                return node
        return None

    def draw(self, context):
        if not self.leaves:
            return
        region = context.region
        x, y, _, block_height = self.bounds
        self.x, self.top = region.view2d.view_to_region(x, y, clip=False)
        self.x += 6*self.scale
        self.top -= 4*self.scale
        self.bottom = region.view2d.view_to_region(x, y-block_height, clip=False)[1]
        self.hover = self.hit(*self.pointer) if self.pointer else None
        ui.use_theme(context)
        self.shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        with ui.paint.canvas(context):
            for node, geom in self.leaves:
                rect = self.rect(geom,node)
                if self.visible_row(node,rect) and rect[1] < region.height and rect[1]+rect[3] > 0:
                    self.paint_node(node, rect)


class BuilderView(InlineView):
    def __init__(self):
        super().__init__()
        self.pivot_open = False
        self.duplicate_open = False

    def layout(self, context, width):
        shell = ui.Layout()
        tools = menu_backend.style(ui.Layout(), 'BUILDER')
        common, snapping = tools.children[0].children
        # Reuse the top bar's configured operators, icons and snap arguments.
        # Only the arrangement is specific to the sidebar.
        def place(parent, *nodes):
            for node in nodes:
                node.parent = parent
                parent.children.append(node)

        actions = {node.options['identifier']: node for node in walk(common)
                   if node.kind == 'operator'}
        auto_snap, snap, target, source, _, axes, pivot, auto_duplicate, mirror = snapping.children
        if width >= 470:
            columns = shell.row(equal=True, gap=15)
            settings, editing = columns.column(), columns.column()
            column_width = (width-15)/2
        else:
            settings = editing = shell
            column_width = width

        order = actions['bbe.swap_corvette_cockpits']
        if column_width < 215:
            order.options['text'] = i18n.interface('Cockpit / Order')
        place(settings, order, actions['bbe.repair_bubble_tubes'])
        settings.separator(factor=.65)
        primary = settings.row(factor=.45) if column_width >= 200 else settings.column()
        place(primary, snap, auto_snap)
        place(settings, target, source)
        if settings is editing:
            editing.separator(factor=.65)

        copies = editing.column(decor='segments')
        split = copies.row(factor=.55, gap=1)
        place(split, actions['object.nms_duplicate'])
        split.child('duplicate_menu', text=i18n.interface('Along…'),
                    secondary=True, height=24)
        if self.duplicate_open:
            for identifier in ('bbe.duplicate_edge_path', 'bbe.duplicate_axis'):
                action = actions[identifier]
                place(copies, action)
                action.options['repeat_mode'] = True
                # Wrap the actual translated command before it would be clipped.
                blf.size(0, 13*self.scale)
                available = (column_width-46)*self.scale
                lines = []
                for word in ui.leaf_text(action).split():
                    if lines and blf.dimensions(0, lines[-1]+' '+word)[0] <= available:
                        lines[-1] += ' '+word
                    else:
                        lines.append(word)
                action.options.update(lines=lines, height=max(24, 15*len(lines)+6), font_size=13)

        editing.separator(factor=.65)
        for first, second in (('bbe.align_geometry', 'object.nms_delete'),
                              ('object.nms_group_objects', 'object.nms_ungroup_objects'),
                              ('object.nms_mirror', 'object.nms_flip')):
            place(editing.row(equal=True), actions[first], actions[second])
        place(editing, mirror, axes)
        auto_duplicate.options['text'] = i18n.interface('Duplicate')
        blf.size(0, 13*self.scale)
        pivot_label = blf.dimensions(0, ui.leaf_text(pivot))[0]/self.scale + 10
        pivot_width = pivot_label + blf.dimensions(0, ui.property_value(pivot, context))[0]/self.scale + 26
        toggle_width = blf.dimensions(0, ui.leaf_text(auto_duplicate))[0]/self.scale + 44
        gap = 3
        if column_width >= pivot_width + toggle_width + gap:
            pivot_row = editing.row(factor=1-toggle_width/(column_width-gap), gap=gap)
        else:
            pivot_row = editing.column()
        place(pivot_row, pivot, auto_duplicate)
        if self.pivot_open:
            choices = editing.column()
            for value, label, _ in ui.enum_items(pivot.options['data'], 'center_of_reflection', context):
                choices.prop_enum(pivot.options['data'], 'center_of_reflection', value, text=label)
        footer = shell.row()
        footer.alignment = 'RIGHT'
        footer.operator('bbe.function_help', text='', outline='circle-help', width=28).topic = 'BUILDER'

        if column_width < 205:
            actions['object.nms_ungroup_objects'].options['font_size'] = 12
        for node in walk(shell):
            if node.kind in {'operator', 'prop', 'enum_value', 'label'}:
                node.options.setdefault('height', 28 if node in (snap, auto_snap, pivot) else 24)
        self.leaves, height = ui.layout_tree(shell, width)
        # A single short label precedes this field in the compact form.
        pivot.options['field_label_width'] = pivot_label
        self.poll_operators(context)
        return height

    def paint_node(self, node, rect):
        if node.kind == 'duplicate_menu':
            super().paint_node(node, rect)
            x, y, w, h = rect
            cx, cy = x+w-12*self.scale, y+h/2
            offset = (2 if self.duplicate_open else -2)*self.scale
            mid = (cx, cy+offset)
            ui.paint.line(self.shader, (cx-4*self.scale, cy-offset), mid, self.scale, ui.TEXT)
            ui.paint.line(self.shader, mid, (cx+4*self.scale, cy-offset), self.scale, ui.TEXT)
            return
        lines = node.options.get('lines', ())
        if len(lines) <= 1:
            super().paint_node(node, rect)
            return
        # The normal painter supplies the same icon and hover state.
        # Draw the wrapped caption within that same hit rectangle.
        caption = node.options['text']
        node.options['text'] = ''
        try:
            super().paint_node(node, rect)
        finally:
            node.options['text'] = caption
        x, y, _, h = rect
        baseline = y+h/2+(7.5*(len(lines)-1)-4)*self.scale
        for index, line in enumerate(lines):
            ui.paint.text(line, x+30*self.scale, baseline-15*index*self.scale,
                          13*self.scale, ui.TEXT if node.can_click else ui.MUTED)




class ToolView(InlineView):
    def __init__(self, menu):
        super().__init__()
        self.menu = menu
        self.dropdown = self.number_drag = None
        self.reverse_order = False
        self.exclude_matches = False

    def filter_prefabs(self, layout, rows):
        wm = bpy.context.window_manager
        query = wm.bbe_prefab_search.strip().casefold()
        bar = layout.row(gap=3)
        bar.prop(wm, 'bbe_prefab_search', text='', placeholder=i18n.interface('Search local prefabs'))
        bar.child('library_option', text='Z–A' if self.reverse_order else 'A–Z', width=36,
                  key='reverse_order', tip='Reverse alphabetical order', center=True, secondary=True)
        if query:
            bar.child('library_option', text=i18n.interface('Exclude'), width=62, key='exclude_matches',
                      tip='Exclude matching prefabs', secondary=True, depress=self.exclude_matches)
        groups = []
        for index, item in enumerate(rows):
            if item.title or not groups:
                groups.append([])
            groups[-1].append((index, item))
        filtered = []
        for group in reversed(groups) if self.reverse_order else groups:
            header = group[0] if group[0][1].title else None
            items = group[1:] if header else group
            folder = header[1].title.casefold() if header else ''
            matches = [entry for entry in items if not query or
                       ((query in folder or query in entry[1].description.casefold()) != self.exclude_matches)]
            if matches and header:
                filtered.append(header)
            filtered.extend(reversed(matches) if self.reverse_order else matches)
        return query, filtered

    @staticmethod
    def style_save_manager(root, width):
        actions = {
            'bbe.backup_settings': 'folder-cog', 'object.nms_select_save_folder': 'folder-open',
            'object.make_savefile_backup': 'save', 'object.open_backup_folder': 'folder-clock',
            'bbe.ship_duplicate': 'copy-plus', 'bbe.refresh_save_counts': 'refresh-cw',
            'object.nms_import_base_from_save': 'file-down', 'object.nms_export_base_to_save': 'upload',
            'bbe.corvette_export': 'upload', 'bbe.optimizer_export': 'upload',
            'bbe.optimizer_settings': 'settings', 'bbe.build_metadata': 'settings',
        }
        for node in walk(root):
            o = node.options
            if o.get('key') == 'check_plugin_enabled':
                o['width'] = 142
                node.parent.parent.options.pop('top_rule', None)
            if node.kind == 'enum_value' and o['key'] == 'nms_base_type':
                o.update(secondary=True, height=24)
            if o.get('key') in {'nms_account_selected','nms_save_slot','string_base'}:
                o['field_label_width'] = 68
            if node.kind == 'operator':
                identifier = o['identifier']
                if identifier in {'bbe.ship_duplicate','object.make_savefile_backup'}:
                    node.parent.options['equal'] = True
                if identifier in actions:
                    art = actions[identifier]
                    o.update(outline=art, icon_tint=menu_contract.icon_colour(art,identifier))
                if o.get('text') == '':
                    o.update(width=25, center=True, tip=ui.operation(identifier).get_rna_type().name)
                elif width < 300:
                    o['font_size'] = 13
                    if identifier == 'bbe.buildable_unlocks':
                        o.update(text=i18n.interface('Item unlocks and currency'))
            if node.kind == 'label' and not o.get('section'):
                # Reserve vertical space for status and repair messages at this panel width.
                line_count = len(textwrap.wrap(ui.leaf_text(node), max(3,int((width-12)/5.5))))
                if line_count > 1:
                    o['height'] = max(o.get('height',22), 16*line_count+5)

    def style_build_files(self, root, width):
        """Keep related file formats and clipboard actions together as the sidebar resizes."""
        blf.size(0, 13 * self.scale)

        def fits(actions):
            # Allow for the icon, row gaps and padding used by paint_node.
            cell = (width - 5 * (len(actions) - 1)) / len(actions)
            return all(blf.dimensions(0, ui.leaf_text(action))[0] / self.scale + 38 <= cell
                       for action in actions)

        for row in list(walk(root)):
            if row.kind != 'row' or len(row.children) != 3:
                continue
            lead, second, third = row.children
            for action in row.children:
                action.options.update(font_size=13, height=25)
            if fits(row.children):
                continue
            row.kind = 'column'
            if lead.options['identifier'] == 'object.nms_import_nms_data':
                lead.options['text'] = i18n.interface('Import from Clipboard')
            if fits((second, third)):
                row.children = [lead]
                pair = row.row(equal=True)
                for action in (second, third):
                    action.parent = pair
                    pair.children.append(action)
        for node in walk(root):
            if node.kind == 'operator':
                rna = ui.operation(node.options['identifier']).get_rna_type()
                node.options['tip'] = rna.description or rna.name
                if node.options['identifier'] == 'bbe.function_help':
                    node.options.update(width=26, center=True, tip=i18n.interface('Import/Export help'))

    def home_layout(self, context, width):
        from . import icons
        root = ui.Layout()
        icons.ensure_sidebar_brand()
        banner = root.template_icon(icons.get_icons_pscroll()['sidebar_brand'].icon_id)
        banner.options.update(brand=True, height=min(320, width) * .25)
        credits = root.row(equal=True) if width >= 280 else root.column()
        for label, author in [('Base Builder', 'DjMonkey'), ('Extended', 'FuriousFurby')]:
            credits.label(text=f'{i18n.interface(label)} · {author}').options['height'] = 17
        self.contents(i18n.localized_layout(root), context, compact=width < 225)
        headings = {i18n.interface(t) for t in ('Community', 'Support DjMonkey')}
        for n in walk(root):
            o = n.options
            if n.kind == 'label':
                if o.get('text') in headings:
                    o.update(section=True, height=20)
                elif o.get('text') == i18n.interface('Switch Proxy Quality'):
                    o.update(text=i18n.interface('Proxy quality'), section=True, height=20)
                elif o.get('text') == i18n.interface('Quick Access'):
                    n.kind = 'gap'
                    o['factor'] = .8
            if o.get('identifier') == 'bbe.find_guide':
                o.update(text='', outline='circle-help', center=True, tip=i18n.interface('How-To Guide'))
            if o.get('identifier') == 'object.nms_visit_guides' and width < 320:
                o.update(text=i18n.interface('Guides'))
            if o.get('identifier') == 'object.nms_switch_proxies_to_low' and width < 350:
                o['text'] = i18n.interface('Simple')
            if o.get('identifier') == 'object.nms_switch_proxies_to_high' and width < 350:
                o['text'] = i18n.interface('Detailed')
            if o.get('identifier') == 'bbe.hd_remove':
                n.parent.alignment = 'EXPAND'
                n.parent.options['width'] = 26
            if o.get('key') == 'enum_assets_quick_access_view_mode' and n.kind == 'enum_value':
                if o['value'] == 'fav' and width < 325:
                    o.update(text=i18n.interface('Faves'), tip=ui.leaf_text(n))
            if n.kind == 'operator' and o.get('text') == '':
                o['width'] = 26
            if o.get('key') == 'asset_broser_search_query':
                o['placeholder'] = i18n.interface('Search parts')
        return menu_contract.decorate(root)

    def support_layout(self, context, width):
        root = ui.Layout()
        self.contents(i18n.localized_layout(root), context)
        actions = {
            'check_updates': ('Check for Updates', 'refresh-cw'),
            'download_update': ('Download and Install', 'file-down'),
            'auto_updates': ('Automatic Updates', 'refresh-cw'),
            'download_folder': ('Downloads Folder', 'folder-open'),
            'support_report': ('Save Support Report', 'save'),
            'online_support': ('Report an Issue Online', 'globe'),
            'error_report_prompt': ('Review / Send Last Error', 'info'),
        }
        for n in list(walk(root)):
            if n.kind == 'label' and n.options['text'] == i18n.interface('Blender Diagnostics'):
                n.options['section'] = True
            if n.kind == 'label' and not n.options.get('section'):
                blf.size(0, 12 * self.scale)
                lines = ['']
                for word in n.options['text'].split():
                    candidate = (lines[-1] + ' ' + word).strip()
                    if lines[-1] and blf.dimensions(0, candidate)[0] > (width - 12)*self.scale:
                        lines.append(word)
                    else:
                        lines[-1] = candidate
                n.options.update(support_lines=lines, height=16*len(lines)+3)
            if n.kind != 'operator':
                continue
            key = n.options['identifier'].partition('.')[2]
            if key not in actions:
                continue
            caption, art = actions[key]
            n.options.update(text=i18n.interface(caption), outline=art, font_size=13,
                             tip=ui.operation(n.options['identifier']).get_rna_type().name)
            if key == 'auto_updates':
                from . import release_updates
                n.options.update(switch=True, depress=bool(release_updates._client.settings.get('auto_check')))
            if key == 'check_updates':
                n.options['primary'] = True
            if key == 'support_report':
                section = root.label(text=i18n.interface('Support'), section=True)
                root.children.remove(section)
                root.children.insert(root.children.index(n), section)
        return menu_contract.decorate(root)

    def transform_layout(self, context):
        root = ui.draw_definition('TRANSFORM', context)
        fields = [n for n in walk(root) if n.kind == 'prop']
        if not fields:
            return root
        actions = {n.options['identifier']: n for n in walk(root) if n.kind == 'operator'}
        panel = ui.Layout()
        panel.header_help = root.header_help
        for title, key, paste in [('Position', 'location', 'location'), ('Rotation', 'rotation_euler', 'rotation'),
                                  ('Scale', 'uniform_scale', 'scale')]:
            header = panel.row()
            header.label(text=i18n.interface(title), section=True)
            button = actions['object.nms_paste_' + paste]
            button.parent = header
            header.children.append(button)
            button.options.update(width=28, outline='clipboard-paste', center=True,
                                  tip=ui.operation(button.options['identifier']).get_rna_type().name)
            row = panel.row(equal=True, gap=3)
            for n in fields:
                if n.options['key'] == key:
                    n.parent = row
                    row.children.append(n)
                    i = n.options.get('index', -1)
                    n.options.update(axis='XYZ'[i] if i >= 0 else '', tip=i18n.interface(title))
        row = panel.row()
        for verb, art in [('copy','copy'), ('paste','clipboard-paste')]:
            n = actions['object.nms_' + verb + '_transformations']
            row.children.append(n)
            n.parent = row
            n.options['outline'] = art
        row.children.append(panel.header_help)
        panel.header_help.parent = row
        panel.header_help.options.update(width=26, center=True)
        del panel.header_help
        return menu_contract.decorate(panel)

    def layout(self, context, width):
        # Use the same controls, operators, values and catalogue artwork as
        # the top bar, including the extra editing tools on a selected curve.
        viewport = next(r for r in context.area.regions if r.type == 'WINDOW')
        with context.temp_override(region=viewport):
            if self.menu == 'proxies':
                root = self.home_layout(context, width)
            elif self.menu == 'support':
                root = self.support_layout(context, width)
            elif self.menu == 'transforms':
                root = self.transform_layout(context)
            elif self.menu == 'io':
                from .tools_menu.base_builder_menu_presentation import draw_build_files
                root = ui.Layout()
                draw_build_files(i18n.localized_layout(root))
                menu_backend.style(root, 'IO')
                ui.compact_io(root)
                self.style_build_files(root, width)
            elif self.menu == 'saves':
                from . import build_timer
                from .save_editor.save_editor_presentation import draw_save_manager
                root = ui.Layout()
                root.operator_context = 'INVOKE_DEFAULT'
                draw_save_manager(i18n.localized_layout(root), context, sidebar_width=width)
                menu_backend.style(root,'IO')
                ui.compact_io(root, build_timer.next_save_action(context.scene))
                self.style_save_manager(root, width)
            else:
                root = ui.draw_definition(menu_backend.KEYS[self.menu], context,
                                          prefab_filter=self.filter_prefabs if self.menu == 'parts' else None)
        stack = [root]
        field = None
        picker = None
        component_grid = None
        section_header = None
        while stack:
            node = stack.pop()
            stack.extend(node.children)
            opts = node.options
            if self.menu == 'recovery':
                if opts.get('key') == 'bbe_recovery_mode' and width < 345:
                    node.parent.kind = 'column'
                if node.kind == 'row' and opts.get('equal'):
                    blf.size(0, 13 * self.scale)
                    widest = max(blf.dimensions(0, ui.leaf_text(c))[0] for c in node.children)
                    if width < 2 * (widest / self.scale + 38) + 5:
                        node.kind = 'column'
                    for action in node.children:
                        action.options['font_size'] = 13
                if opts.get('recovery_status_lines'):
                    status, retention = opts['recovery_status_lines']
                    section_header = node.parent
                    blf.size(0, 12 * self.scale)
                    if blf.dimensions(0, opts['text'])[0] / self.scale + 45 > width:
                        column = section_header.column()
                        section_header.children.remove(node)
                        column.children.append(node)
                        node.parent = column
                        opts['text'] = status
                        if blf.dimensions(0, status)[0] / self.scale + 45 <= width:
                            opts['height'] = 17
                        column.label(text=retention)
            if self.menu == 'batch' and opts.get('decor') == 'columns' and width < 230:
                node.kind = 'column'
                opts.pop('decor')
            if self.menu == 'batch' and 230 <= width < 330:
                short = {'object.nms_select_duplicates':'Duplicates', 'object.nms_batch_select_random':'Random',
                         'object.nms_batch_select_pattern':'Pattern', 'object.nms_select_same_objects':'Object ID', 'object.nms_select_all_groups':'All Groups'}
                if opts.get('identifier') in short:
                    opts['text'] = i18n.interface(short[opts['identifier']])
                if node.kind == 'operator':
                    opts['font_size'] = 13
            if self.menu == 'parts' and node.kind == 'operator':
                short_labels = {'object.nms_save_as_preset': 'Save Prefab',
                                'object.nms_split_preset': 'Split to Parts',
                                'object.nms_open_preset_folder': 'Open Folder',
                                'object.nms_get_more_presets': 'Get Prefabs'}
                identifier = opts['identifier']
                if identifier in short_labels and width < 380:
                    opts.update(text=i18n.interface(short_labels[identifier]), font_size=13)
                    if width < 213:
                        node.parent.kind = 'column'
                if identifier in {'object.list_edit_operator', 'object.list_delete_operator',
                                  'object.nms_refresh_prefabs'}:
                    opts['width'] = 25
                if identifier == 'object.list_build_operator':
                    opts['tip'] = opts['text']
            if self.menu == 'cables' and opts.get('tile'):
                component_grid = node.parent
                component_grid.kind = 'grid'
                cols = max(2, int(width/56))
                component_grid.options.update(columns=8 if cols >= 8 else min(cols,6), gap=3)
            if node.kind == 'grid':
                if self.menu == 'shapes':
                    opts.update(columns=max(2,min(5,int(width/84))), gap=3)
                    node.scale_y = 1
                elif self.menu == 'color':
                    opts.update(columns=min(8, max(2, int(width/32))), gap=3)
                elif self.menu == 'transform':
                    opts.update(columns=8 if width >= 216 else 4, gap=2)
                    node.scale_y = 1
            if self.menu == 'cables' and opts.get('tile'):
                opts.update(height=49, tip=ui.operation(opts['identifier']).get_rna_type().description)
            elif self.menu == 'shapes' and opts.get('tile'):
                opts.update(height=60, tip=opts['text'])
            elif opts.get('material_finish'):
                opts['height'] = 32
            elif opts.get('shape_tile'):
                # Draw the preset artwork edge to edge; the tooltip carries its name.
                opts.update(sidebar_icon=True, height=28)
            elif node.kind in {'prop','operator','menu','enum_value','library_option'}:
                opts['height'] = 26
            if self.menu == 'shapes' and opts.get('key') == 'dimension':
                section_header = node.parent
            if self.menu == 'lighting':
                if opts.get('key') == 'enabled' or (node.kind == 'label' and node.parent.kind == 'row'):
                    section_header = node.parent
                if opts.get('identifier') == 'bbe.stage_refresh':
                    opts.update(primary=True, outline='refresh-cw')
                if opts.get('key') == 'environment':
                    opts['text'] = i18n.interface('Scene')
                if opts.get('key') == 'pad_radius':
                    opts['slider'] = True
            if node.kind == 'prop':
                if (self.edit and opts['key'] == self.edit['node'].options['key']
                        and opts['data'] == self.edit['node'].options['data']
                        and opts.get('index') == self.edit['node'].options.get('index')):
                    self.edit['node'] = node
                if opts['key'] == self.choice_key:
                    field = node
                if opts['key'] == 'bbe_curve_plane':
                    draw_action = node.parent.children[0]
                    blf.size(0, 14*self.scale)
                    button = blf.dimensions(0, ui.leaf_text(draw_action))[0]/self.scale + 40
                    blf.size(0, 13*self.scale)
                    plane = blf.dimensions(0, ui.property_value(node, context))[0]/self.scale + 26
                    if button + plane + 5 <= width:
                        node.parent.options['factor'] = button/(width-5)
                    else:
                        node.parent.kind = 'column'
            if node.kind == 'menu' and opts['identifier'] == 'BBE_MT_curve_connections':
                node.kind = 'operator'
                opts.update(identifier='bbe.curve_connections', outline='link', props=SimpleNamespace())
            if node.kind == 'prop' and opts['key'] == 'color_picker':
                picker = node
                node.kind = 'operator'
                opts.update(identifier='bbe.pick_object_colour', outline='pipette',
                            text=i18n.interface('Pick Colour from Object'), props=SimpleNamespace())
        if field is not None:
            # Native sidebar scrolling also scrolls an expanded choice list.
            parent = field.parent
            if parent.kind == 'row':
                parent = parent.parent
            choices = parent.column()
            parent.children.remove(choices)
            sibling = field if field.parent == parent else field.parent
            parent.children.insert(parent.children.index(sibling)+1, choices)
            data, key = field.options['data'], field.options['key']
            for value, label, _ in ui.enum_items(data, key, context):
                choices.prop_enum(data, key, value, text=label).options['height'] = 23
        help_node = getattr(root, 'header_help', None)
        if help_node:
            help_node.options.update(width=26, height=22, outline='circle-help')
            if component_grid:
                # Put help at the right end of the last component row.
                columns = component_grid.options['columns']
                for _ in range((-len(component_grid.children)-1) % columns):
                    component_grid.separator()
                footer = component_grid.row()
                footer.alignment = 'RIGHT'
                help_node.options.update(height=49, center=True)
            elif self.menu in {'lighting', 'recovery'} and section_header:
                footer = section_header
            elif self.menu == 'shapes' and section_header:
                tabs = section_header
                footer = tabs.parent.row(gap=3)
                parent = tabs.parent
                parent.children.remove(footer)
                parent.children[parent.children.index(tabs)] = footer
                tabs.parent = footer
                footer.children.append(tabs)
            elif picker and width > 236:
                footer = picker.parent
            elif root.children[-1].kind == 'label':
                hint = root.children.pop()
                footer = root.row()
                hint.parent = footer
                footer.children.append(hint)
            else:
                footer = root.row()
                footer.alignment = 'RIGHT'
            footer.children.append(help_node)
            help_node.parent = footer
        self.leaves, height = ui.layout_tree(root, width)
        self.poll_operators(context)
        return height

    def draw_edit_text(self, x, y, w, h):
        from . import string_field
        string_field.draw(self.edit, self.shader, self.scale, x, y, w, h)

    def paint_node(self, node, rect):
        if node.options.get('support_lines'):
            x, y, w, h = rect
            for index, line in enumerate(node.options['support_lines']):
                size = 12*self.scale
                ui.paint.text(ui.trim(line, w-10*self.scale, size), x+5*self.scale,
                              y+h-(14+16*index)*self.scale, size, ui.MUTED)
            return
        if node.options.get('brand'):
            from . import icons
            x, y, w, h = rect
            size = min(w, 320 * self.scale)
            preview = icons.get_icons_pscroll()['sidebar_brand']
            ui.draw_image(preview.icon_id, x+(w-size)/2, y+h-size, size, size, preview=preview)
            return
        if 'axis' in node.options:
            x, y, w, h = rect
            scale = self.scale
            ui.paint.rounded(self.shader,x,y+scale,w,h-2*scale,5*scale,ui.HOVER if self.hover is node else ui.SURFACE)
            axis = node.options['axis']
            if axis:
                ui.paint.text(axis,x+5*scale,y+h/2-4*scale,12*scale,ui.MUTED)
            margin = (19 if axis else 5)*scale
            if self.edit and self.edit['node'] is node:
                self.draw_edit_text(x+margin,y,w-margin,h)
            else:
                value = ui.property_value(node,bpy.context)
                ui.paint.text(ui.trim(value,w-margin-3*scale,13*scale),x+margin,y+h/2-4*scale,13*scale,ui.TEXT)
            return
        if not node.options.get('sidebar_icon'):
            return super().paint_node(node, rect)
        x, y, w, h = rect
        if self.hover is node:
            ui.paint.rounded(self.shader, x, y, w, h, 4*self.scale, ui.HOVER)
        size = min(w-2*self.scale, h-2*self.scale)
        if size > 0:
            ui.draw_image(node.options.get('icon_value'), x+(w-size)/2, y+(h-size)/2, size, size)

    def draw(self, context):
        if not self.leaves:
            return
        super().draw(context)
        node = self.hover
        if not node or not self.pointer:
            return
        if node.options.get('sidebar_icon'):
            caption = ui.leaf_text(node)
        elif node.options.get('tip'):
            caption = ui.tooltip(node)
        elif node.options.get('swatch'):
            caption = node.options['props'].colour_name
        else:
            return
        s = self.scale
        blf.size(0, 12*s)
        width = min(blf.dimensions(0, caption)[0]+16*s, context.region.width-12*s)
        if width <= 0:
            return
        x = max(2*s, min(self.pointer[0], context.region.width-width-4*s))
        y = max(2*s, self.pointer[1]-28*s)
        with ui.paint.canvas(context):
            ui.paint.rounded(self.shader, x, y, width, 20*s, 5*s, ui.SURFACE)
            ui.paint.text(ui.trim(caption, width-10*s, 12*s), x+7*s, y+6*s, 12*s, ui.TEXT)


def draw_inline(owner, context, menu='builder', contents=None):
    if not context.region or context.region.type != 'UI':
        return False
    panel = native_panel(owner)
    if panel is None:
        return False
    bounds = (panel.x, panel.y + panel.height, panel.width, panel.block_height)
    key = view_key(context, menu)
    view = _views.get(key)
    if view is None:
        view = _views[key] = BuilderView() if menu == 'builder' else ToolView(menu)
    view.visible = True
    view.contents = contents
    region = context.region
    unit = abs(region.view2d.region_to_view(1, 0)[0] - region.view2d.region_to_view(0, 0)[0])
    dpi = context.preferences.system.ui_scale
    view.scale = .90 * dpi / max(.01, unit)
    view.bounds = bounds
    width = max(40, (bounds[2] / dpi - 12) / .90)
    height = view.layout(context, width)
    col = owner.layout.column()
    col.ui_units_y = (height + 6)*.90 / 20
    col.label(text='')
    # On first opening and reflow Blender resolves the new body after draw().
    # Schedule one more layout to pick up its settled bounds.
    geometry = (bounds, round(height, 1))
    if getattr(view, 'geometry', None) != geometry:
        view.geometry = geometry
        region.tag_redraw()
    return True


def draw():
    context = bpy.context
    overlay = None
    for view in active_views(context):
        view.draw(context)
        if isinstance(view, ToolView) and view.dropdown:
            overlay = view
    # Paint after all panel bodies, even when another panel covers the choices.
    if overlay:
        with ui.paint.canvas(context):
            overlay.draw_dropdown()


class BBE_OT_sidebar_builder_input(bpy.types.Operator):
    bl_idname = 'bbe.sidebar_builder_input'
    bl_label = 'Builder Sidebar Input'
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        if context.region and context.region.type == 'UI':
            return any(active_views(context))
        if not _views or not context.window or not context.area:
            return False
        return any(view.pointer for menu in INLINE_MENUS
                   if (view := _views.get(view_key(context, menu))) is not None)

    @staticmethod
    def run_operator(context, view, node, mode='INVOKE_DEFAULT', **overrides):
        region = next(r for r in context.area.regions if r.type == 'WINDOW')
        with context.temp_override(region=region):
            op = ui.operation(node.options['identifier'])
            if not op.poll():
                return
            result = op(mode, **(vars(node.options['props']) | overrides))
            if node.options.get('repeat_mode') and 'CANCELLED' not in result:
                view.duplicate_open = False
            cls = bpy.types.Operator.bl_rna_get_subclass_py(op.get_rna_type().identifier)
            if result == {'FINISHED'} and 'UNDO' in getattr(cls, 'bl_options', ()):
                bpy.ops.ed.undo_push(message=cls.bl_label)

    @staticmethod
    def write_number(node, value):
        options = node.options
        data, key = options['data'], options['key']
        index = options.get('index', -1)
        if index < 0:
            setattr(data, key, value)
        else:
            if data.bl_rna.properties[key].subtype == 'EULER':
                value = math.radians(value)
            getattr(data, key)[index] = value

    def start_field(self, context, view, node, mouse, operator_items=None):
        view.area, view.region = context.area, context.region
        view.mouse = mouse
        self.field_view = view
        self.field_key = view_key(context, view.menu)
        if view.menu == 'transforms':
            self.transform_object = context.active_object
        if operator_items:
            view.open_choices(node, operator_items, None)
        else:
            data, key = node.options['data'], node.options['key']
            value = getattr(data, key)
            if data.bl_rna.properties[key].type == 'FLOAT':
                geom = next(geom for leaf, geom in view.leaves if leaf is node)
                width = view.rect(geom)[2]
                view.number_drag = dict(node=node, start=mouse[0], value=ui.numeric_value(node), width=width, moved=False)
            elif data.bl_rna.properties[key].type == 'INT':
                text = str(value)
                view.edit = dict(node=node, text=text, original=value, anchor=0, caret=len(text),
                                 number=True, integer=True)
            elif data.bl_rna.properties[key].type == 'STRING':
                view.edit = dict(node=node, text=value, original=value, anchor=0, caret=len(value))
            else:
                view.open_choices(node, ui.enum_items(data, key, context), None)
                view.dropdown['selected'] = value
        context.window_manager.modal_handler_add(self)
        view.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        area = context.area
        if not context.region or context.region.type != 'UI':
            if event.type == 'MOUSEMOVE':
                for menu in INLINE_MENUS:
                    view = _views.get(view_key(context, menu))
                    if view and view.pointer:
                        view.pointer = None
                        context.area.tag_redraw()
            return {'PASS_THROUGH'}
        mouse = (event.mouse_region_x, event.mouse_region_y)
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            for candidate in active_views(context):
                if not isinstance(candidate, ToolView) or candidate.menu != 'parts' or not hasattr(candidate, 'top'):
                    continue
                for node, bounds in candidate.leaves:
                    if node.kind == 'list_scroll' and ui.inside(candidate.rect(bounds), *mouse):
                        step = 1 if event.type == 'WHEELDOWNMOUSE' else -1
                        opts = node.options
                        offset = max(0, min(opts['total']-opts['rows'], opts['offset']+step))
                        if offset != opts['offset']:
                            context.window_manager.bbe_prefab_offset = offset
                            context.region.tag_redraw()
                            return {'FINISHED'}
            return {'PASS_THROUGH'}
        hit = None
        for candidate in active_views(context):
            if not hasattr(candidate, 'top'):
                continue
            if (event.type == 'LEFTMOUSE' and isinstance(candidate,ToolView) and candidate.menu == 'parts'
                    and candidate.grab_list(*mouse)):
                self.field_view = candidate
                self.field_key = view_key(context, candidate.menu)
                candidate.area, candidate.region = context.area, context.region
                candidate.scroll_list_to(context, mouse[1])
                context.region.tag_redraw()
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
            node = candidate.hit(*mouse)
            if event.type == 'MOUSEMOVE':
                candidate.pointer = mouse
                if candidate.hover is not node:
                    context.region.tag_redraw()
            if node:
                hit = candidate, node
        if event.type == 'MOUSEMOVE' or hit is None:
            return {'PASS_THROUGH'}
        view, node = hit
        o = node.options
        if node.kind == 'library_option':
            setattr(view, o['key'], not getattr(view, o['key']))
            context.window_manager.bbe_prefab_offset = 0
        elif node.kind == 'duplicate_menu':
            view.duplicate_open = not view.duplicate_open
        elif node.kind in {'menu', 'panel'}:
            port = next(r for r in area.regions if r.type == 'WINDOW')
            with context.temp_override(region=port):
                bpy.ops.bbe.custom_menu('INVOKE_DEFAULT', menu=node.kind.upper()+':'+o['identifier'])
        elif node.kind == 'operator':
            if getattr(view, 'menu', None) in {'io', 'recovery', 'proxies', 'support', 'transforms'}:
                # Opening a confirmation on press would send the same click's release into it.
                self.pending_action = (o['identifier'], vars(o['props']).copy())
                self.field_view = view
                self.field_key = view_key(context, view.menu)
                view.area, view.region = context.area, context.region
                context.window_manager.modal_handler_add(self)
                return {'RUNNING_MODAL'}
            if o['identifier'] == 'object.nms_connect':
                from . import cable_connections
                power = context.scene.nms_main.line_switch == 'POWER'
                selected = cable_connections.power_devices(context.selected_objects) if power else context.selected_objects
                if len(selected) >= (2 if power else 3):
                    routing = ui.operation(o['identifier']).get_rna_type().properties['routing']
                    items = [(v.identifier, i18n.interface(v.name), v.description) for v in routing.enum_items]
                    return self.start_field(context, view, node, mouse, items)
            mode = node.inherited('operator_context','INVOKE_DEFAULT') if getattr(view,'menu',None)=='shapes' else 'INVOKE_DEFAULT'
            self.run_operator(context, view, node, mode)
        elif node.kind == 'enum_value':
            setattr(o['data'], o['key'], o['value'])
            if isinstance(view, BuilderView):
                view.pivot_open = False
            view.choice_key = None
        elif o['data'].bl_rna.properties[o['key']].type == 'BOOLEAN':
            setattr(o['data'], o['key'], not getattr(o['data'],o['key']))
        elif o['data'].bl_rna.properties[o['key']].type in {'INT', 'FLOAT'}:
            if getattr(view, 'menu', None) in {'lighting', 'recovery', 'transforms', 'proxies'}:
                return self.start_field(context, view, node, mouse)
            field = {'points':'control_count', 'free_count':'control_count',
                     'active_curve_number_of_objects':'objects_count',
                     'active_curve_radius_multiplier':'radius_multiplier'}.get(o['key'], o['key'])
            # The label is a drag handle; the displayed number opens exact entry.
            rect = next(view.rect(g) for n, g in view.leaves if n is node)
            label_width = min(rect[2]*.43, o.get('field_label_width', 60)*view.scale)
            op = bpy.ops.bbe.curve_value if mouse[0] < rect[0]+label_width else bpy.ops.bbe.curve_number
            op('INVOKE_DEFAULT', field=field)
            return {'FINISHED'}
        elif getattr(view,'menu',None) in {'saves', 'recovery', 'proxies'} or o['key'] in {'material_category', 'line_switch', 'bbe_prefab_search', 'environment'}:
            return self.start_field(context, view, node, mouse)
        elif isinstance(view, ToolView):
            view.choice_key = None if view.choice_key == o['key'] else o['key']
        else:
            view.pivot_open = not view.pivot_open
        if node.kind in {'prop','enum_value'}:
            from . import settings_memory
            settings_memory.flush()
        area.tag_redraw()
        return {'FINISHED'}

    def cancel(self, context):
        view = self.field_view
        view.dropdown = view.edit = view.number_drag = view.list_drag = None
        if view.area in context.window.screen.areas[:]:
            view.area.tag_redraw()

    def modal(self, context, event):
        view = self.field_view
        pending = getattr(self, 'pending_action', None)
        if (_views.get(self.field_key) is not view or not (pending or view.dropdown or view.edit or view.list_drag or view.number_drag) or not view.visible
                or view.area not in context.window.screen.areas[:]
                or view.region not in view.area.regions[:] or view.region.active_panel_category != CATEGORY
                or event.type == 'WINDOW_DEACTIVATE'):
            self.cancel(context)
            return {'CANCELLED'}
        if pending:
            if event.type in {'ESC', 'RIGHTMOUSE'}:
                return {'CANCELLED'}
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                node = view.hit(event.mouse_x - view.region.x, event.mouse_y - view.region.y)
                if node and node.kind == 'operator' and (node.options['identifier'], vars(node.options['props'])) == pending:
                    with context.temp_override(area=view.area, region=view.region):
                        self.run_operator(context, view, node)
                return {'FINISHED'}
            return {'RUNNING_MODAL'}
        if view.list_drag:
            if event.type == 'MOUSEMOVE':
                view.scroll_list_to(context, event.mouse_y-view.region.y)
                view.region.tag_redraw()
            if event.type in {'ESC','RIGHTMOUSE'} or (event.type == 'LEFTMOUSE' and event.value == 'RELEASE'):
                self.cancel(context)
                return {'FINISHED'}
            return {'RUNNING_MODAL'}
        if view.menu == 'transforms' and (view.edit or view.number_drag):
            if context.active_object != self.transform_object or not context.active_object or not context.active_object.select_get():
                self.cancel(context)
                return {'CANCELLED'}
        if view.number_drag:
            drag = view.number_drag
            opts = drag['node'].options
            data, key = opts['data'], opts['key']
            delta = event.mouse_x-view.region.x-drag['start']
            if event.type in {'RIGHTMOUSE','ESC'}:
                self.write_number(drag['node'], drag['value'])
                self.cancel(context)
                return {'CANCELLED'}
            if event.type == 'MOUSEMOVE' and (drag['moved'] or abs(delta)>3*view.scale):
                drag['moved'] = True
                prop = data.bl_rna.properties[key]
                step = (prop.hard_max-prop.hard_min)/max(1,drag['width'])
                if view.menu in {'transforms', 'proxies'}:
                    step = 1 if key == 'rotation_euler' else max(.01, abs(drag['value']) * .01)
                self.write_number(drag['node'], drag['value'] + delta*step*(.1 if event.shift else 1))
                view.region.tag_redraw()
            if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                view.number_drag = None
                if drag['moved']:
                    if view.menu == 'transforms':
                        bpy.ops.ed.undo_push(message='Edit Transform')
                    from . import settings_memory
                    settings_memory.flush()
                    self.cancel(context)
                    return {'FINISHED'}
                value = format(drag['value'], '.7g')
                view.edit = dict(node=drag['node'], text=value, original=drag['value'],
                                 anchor=0, caret=len(value), number=True)
                view.region.tag_redraw()
            return {'RUNNING_MODAL'}
        if view.edit:
            if event.value == 'PRESS':
                edit = view.edit
                data, key = edit['node'].options['data'], edit['node'].options['key']
                if event.type in {'ESC', 'RIGHTMOUSE', 'RET', 'NUMPAD_ENTER', 'TAB', 'LEFTMOUSE'}:
                    if event.type in {'ESC', 'RIGHTMOUSE'}:
                        if not edit.get('number'):
                            setattr(data, key, edit['original'])
                    elif edit.get('number'):
                        try:
                            text = edit['text'].strip()
                            if edit.get('integer'):
                                prop = data.bl_rna.properties[key]
                                value = min(prop.hard_max, max(prop.hard_min, int(text)))
                            else:
                                value = float(text.replace(',', '.'))
                                if not math.isfinite(value):
                                    raise ValueError
                        except ValueError:
                            self.report({'WARNING'}, 'Enter a number or press Esc to cancel.')
                            return {'RUNNING_MODAL'}
                        self.write_number(edit['node'], value)
                        if view.menu == 'transforms':
                            bpy.ops.ed.undo_push(message='Edit Transform')
                        from . import settings_memory
                        settings_memory.flush()
                    self.cancel(context)
                    return {'FINISHED', 'PASS_THROUGH'} if event.type == 'LEFTMOUSE' else {'FINISHED'}
                from . import string_field
                string_field.handle_key(edit, context, event)
                if not edit.get('number') and edit['text'] != getattr(data, key):
                    setattr(data, key, edit['text'])
                view.region.tag_redraw()
            return {'RUNNING_MODAL'}
        if event.type in {'ESC', 'RIGHTMOUSE'}:
            self.cancel(context)
            return {'CANCELLED'}
        if event.type not in {'MOUSEMOVE', 'LEFTMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}
        x, y = event.mouse_x-view.region.x, event.mouse_y-view.region.y
        view.mouse = (x, y)
        left, top, width, count = view.choice_geometry()
        choices = view.dropdown
        row = int((top-y) // (31*view.scale))
        inside = left <= x <= left+width and 0 <= row < count
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if inside:
                node = choices['node']
                value = choices['items'][row+choices['offset']][0]
                if node.kind == 'operator':
                    self.run_operator(context, view, node, 'EXEC_DEFAULT', routing=value)
                else:
                    field = node.options
                    setattr(field['data'], field['key'], value)
                    from . import settings_memory
                    settings_memory.flush()
            self.cancel(context)
            return {'FINISHED'}
        if event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            if not inside:
                self.cancel(context)
                return {'CANCELLED', 'PASS_THROUGH'}
            offset = choices['offset'] + (1 if event.type == 'WHEELDOWNMOUSE' else -1)
            choices['offset'] = max(0, min(len(choices['items'])-count, offset))
        view.region.tag_redraw()
        return {'RUNNING_MODAL'}


@persistent
def clear(*_):
    _views.clear()


@persistent
def invalidate(*_):
    for view in _views.values():
        view.leaves = []


def register():
    global _handler
    bpy.utils.register_class(BBE_OT_sidebar_builder_input)
    _handler = bpy.types.SpaceView3D.draw_handler_add(draw, (), 'UI', 'POST_PIXEL')
    config = bpy.context.window_manager.keyconfigs.addon
    if config:
        for event in ('LEFTMOUSE', 'MOUSEMOVE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'):
            name = 'View2D Buttons List' if event.startswith('WHEEL') else 'Screen'
            km = config.keymaps.new(name=name, space_type='EMPTY', region_type='WINDOW')
            item = km.keymap_items.new(BBE_OT_sidebar_builder_input.bl_idname, event,
                                       'ANY' if event == 'MOUSEMOVE' else 'PRESS', head=True)
            _keymaps.append((km,item))
    bpy.app.handlers.load_pre.append(clear)
    for handlers in (bpy.app.handlers.undo_pre,bpy.app.handlers.redo_pre):
        handlers.append(invalidate)


def unregister():
    global _handler
    clear()
    bpy.app.handlers.load_pre.remove(clear)
    for handlers in (bpy.app.handlers.undo_pre,bpy.app.handlers.redo_pre):
        handlers.remove(invalidate)
    for km,item in _keymaps:
        km.keymap_items.remove(item)
    _keymaps.clear()
    bpy.types.SpaceView3D.draw_handler_remove(_handler,'UI')
    _handler = None
    bpy.utils.unregister_class(BBE_OT_sidebar_builder_input)

"""Local, read-only explanations shared by tool dialogs and both BBE menus."""
import textwrap
import bpy


TOPICS = {
    'CURVES': ('HOW TO - Curve Tools', (
        ('Draw or choose a shape', 'Draw Smooth Curve uses the chosen plane. The colored shape buttons create a circle, ellipse, arc, spiral, helix or wave. Select the curve to edit its dimensions and points.'),
        ('Edges and faces', 'Curve from Edges / Faces opens in Edges mode. Hover near a visible boundary to preview an edge section, then click to add it. Faces selects a broad patch and centers a path between its outer edges. Click a selected section again to remove it.'),
        ('Draw on Surface', 'Use a short stroke as a highlighter to indicate direction. The tool creates a clean surface-following path. It does not trace every wobble of your stroke.'),
        ('Rotate and create', 'For a face or drawn path, drag the ring or diamond with the hand cursor. Type degrees while holding it, or use Rotate 90 degrees. Ctrl+Z undoes, Ctrl+Y redoes. Create Curves or Enter makes editable curves; Esc cancels. You can reopen the tool to create another curve.'),
        ('Edit and place parts', 'Select a curve or its linked object to reveal controls below. Diamonds move points; round tips shape bends. Smooth, Open / Close, Insert Point and Remove Point edit the curve. Use Duplicate Along Curve to arrange selected parts on it.'),
    )),
    'COCKPIT': ('Swap Cockpit/Object order', (
        ('What changes', 'Choose Cockpits or an object type with duplicate Object IDs, then choose two named instances. Swap Order immediately exchanges their positions in the exported object list. Their physical positions, rotations, sizes and colors stay the same.'),
        ('When it takes effect', 'The scene order changes when you click Swap Order. Both ordinary and optimized exports use that order. The game save changes only when you export to it. Cockpit encounter order can affect the roles assigned by the game.'),
        ('Keeping or undoing it', 'Save the .blend to keep the order with this project. Ctrl+Z undoes the scene edit. Other projects keep their own order; this is not a global setting.'),
        ('Separate from optimizer settings', 'Canceling Optimizer Settings does not undo an object-order swap you already confirmed. Use Ctrl+Z to undo that swap.'),
    )),
    'OPTIMIZER': ('Corvette Optimizer', (
        ('What changes', 'Optimize & Export arranges exported parts by category and priority. Earlier entries come first. Your Blender objects stay in place.'),
        ('Which exports use it', 'Only Optimize & Export applies these priorities and optional duplicate removal. Ordinary Export to Save uses the scene order. The relative order of placed cockpits and landing bays is preserved by optimization.'),
        ('Editing the list', 'Add, Remove and Rename change priority entries, not the parts in your scene. Exact duplicate removal requires every saved field to match, including transform, color and other saved data.'),
        ('Keeping settings', 'Save Settings stores priorities for future optimized exports across projects. Cancel keeps the previously saved settings. Reset to Default changes the settings draft until you save it.'),
        ('Cockpit swaps', 'Swap Cockpit/Object order is a separate, immediate scene edit. It is saved in the .blend and is not canceled when you cancel optimizer settings.'),
    )),
    'EXPORT': ('Export Corvette to Save', (
        ('Source and destination', 'Exports the current Blender scene into the chosen game save, in Main or Expedition. Review the ship slot before confirming. Exporting a .nmsship file is separate and does not write a game save.'),
        ('Ship Name', 'Type the name below Select Corvette in I/O or the sidebar Save Manager. This is the same name as the Metadata field and stays with the Blender project. Both Export to Save and Optimize & Export apply it when you confirm; .nmsship export uses it too. Leave it blank to keep the destination ship name when overwriting. A gray placeholder shows that saved name when the field is blank.'),
        ('Advanced build metadata', 'The settings icon beside Ship Name or Base Name edits the build Owner record and last-editor fields. Apply changes the Blender project. Full build JSON, clipboard and base exports retain metadata; BBE Corvette packages retain it in a versioned BBE metadata entry. Other tools may ignore that entry. Objects-only exports contain only parts. Game-save exports keep the destination Owner unless you explicitly enable Include this Owner, Apply, then confirm the export. That permission resets when opening a .blend or enabling BBE.'),
        ('Overwrite Selected Ship', 'Replaces that ship’s build with your scene parts. Readable inventory, technology, hyperslots, class, stats and appearance are retained. A non-Corvette destination is converted to a Corvette.'),
        ('New Empty Ship Slot', 'Creates a Corvette with minimal default inventory, technology and stats, then uses exactly your scene parts. No template parts are added. Occupied slots and slots reserved by orphan builds are unavailable.'),
        ('Warnings and recovery', 'A missing cockpit warns that the ship will be unflyable; export is still allowed and no cockpit is inserted. Any unreadable data reset needs separate confirmation. Verified backups are made before writing; Blender Undo cannot undo a game-save write.'),
    )),
    'SHIP_FILE': ('Export Corvette Package (.nmsship)', (
        ('What is saved', 'Writes your current Blender parts into a standalone .nmsship file. The file browser starts with the .nmsship extension. This operation does not write a game save.'),
        ('Ship data', 'An imported ship keeps its inventory, technology, stats and appearance. Otherwise, choose Use selected save Corvette to copy those fields from the Corvette selected in I/O, or choose a complete .nmsship template in the file browser options.'),
        ('Designs started in Blender', 'With no imported ship, selected-save option or template, BBE uses new Corvette defaults. Your exact scene parts are kept. No cockpit or template parts are added; a missing cockpit warns that the exported ship is unflyable.'),
    )),
    'COLOUR': ('Palette Colors and Inverse Finishes', (
        ('Where colors appear', 'A part’s model and color mask determine which surfaces use each palette color. Choosing red does not make every surface red; some surfaces use the secondary color or retain their original texture.'),
        ('Inverse finishes', 'Inverse Gloss and other inverse finishes swap primary with secondary, and tertiary with the fourth palette color. Use an inverse finish when the color you want is on the wrong surface. This finish choice is included in exported part data.'),
    )),
    'REPAIR': ('Repair — Keep My Build', (
        ('What is repaired', 'Repairs the selected saved build’s Corvette record and ship-slot link. It uses the objects already in the game save, not the current Blender scene.'),
        ('What is preserved', 'Keeps the build objects, their order, transforms and colors, plus readable inventory, technology, hyperslots, class, stats and appearance. Unreadable data resets are listed and need separate confirmation. Duplicate linked builds require you to choose which build to keep.'),
        ('No cockpit added', 'A cockpitless build stays cockpitless. Repair and export are allowed with an unflyable-ship warning. Add a cockpit yourself when the design is ready.'),
        ('When it saves', 'In I/O, confirming Repair Corvette writes the reviewed repair. In Ship Management, Repair Build stages a draft until Save Changes. Verified backups precede writes. Other ships and the freighter are preserved; restore a backup to undo a game-save write.'),
    )),
    'REPLACE': ('Replace From File', (
        ('Full ship replacement', 'A complete .nmsship supplies the replacement build, ship record, inventories, stats and appearance. This can replace the selected ship’s existing data. Use Repair — Keep My Build when you want to retain that data.'),
        ('Objects-only replacement', 'Inside Ship Management, replacing only objects retains the ship record and requires one correctly linked Corvette. It cannot resolve an uncertain ownership link.'),
        ('Review and save', 'Review the destination and package before confirming. Duplicate linked builds require explicit confirmation. I/O writes after confirmation; Ship Management stages until Save Changes. Verified backups precede writes, and other slots are preserved.'),
    )),
    'RECOVERY': ('Project Recovery', (
        ('What is backed up', 'Saves separate recovery .blend copies of your Blender project. It does not overwrite your original project or serve as an export to the game save.'),
        ('When backups run', 'Choose a time interval or a quantity of newly placed parts. Back Up Now makes a manual recovery copy. The status line shows the countdown, deferral or error so you can check whether a backup was made.'),
        ('Three consecutive saves', 'Keeps the latest three recovery saves per project. Each new recovery replaces the oldest of those three; they are successive versions, not duplicate copies of one save.'),
        ('Finding and restoring', 'Open Recovery lists available copies. Save any current work before opening one. Open Backup Folder and Change Folder access the shared backup root; backup types may use subfolders.'),
    )),
    'NAVIGATION': ('WASD Navigation', (
        ('Moving around', 'Enable WASD Navigation, then hold right mouse in the 3D View to look and move with WASD or arrow keys. Q/E moves down/up, Shift is faster, Ctrl is slower, and the mouse wheel adjusts speed.'),
        ('Stopping', 'Release right mouse or press Escape to stop. A quick right-click still opens the context menu. This moves the viewport, not your model or camera object.'),
        ('Availability and settings', 'Works in Object and Mesh Edit modes with left-click selection. The toggle and speed settings are add-on preferences, shared across projects. Disabling it returns input to the normal Blender controls.'),
    )),
}
TOPIC_ITEMS = tuple((key, title, paragraphs[0][1]) for key, (title, paragraphs) in TOPICS.items())


def help_button(layout, topic='COCKPIT', text='How this works'):
    row = layout.row(align=True)
    row.operator_context = 'INVOKE_DEFAULT'
    row.operator('bbe.function_help', text=text, icon='QUESTION').topic = topic


class BBE_OT_function_help(bpy.types.Operator):
    bl_idname = 'bbe.function_help'
    bl_label = 'BBE Feature Help'
    bl_description = 'Read what this tool changes, when it takes effect, what is preserved, and how to undo or recover'
    topic: bpy.props.EnumProperty(name='Feature', items=TOPIC_ITEMS)

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=590)

    def draw(self, context):
        self.layout.prop(self, 'topic', text='Feature')
        for heading, paragraph in TOPICS[self.topic][1]:
            box = self.layout.box()
            box.label(text=heading)
            col = box.column(align=True)
            for line in textwrap.wrap(paragraph, width=78):
                col.label(text=line)

    def execute(self, context):
        return {'FINISHED'}


def register():
    bpy.utils.register_class(BBE_OT_function_help)


def unregister():
    bpy.utils.unregister_class(BBE_OT_function_help)

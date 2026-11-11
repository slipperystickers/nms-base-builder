"""Local, read-only explanations shared by tool dialogs and both BBE menus."""
import textwrap
import bpy
from ..bbe_chat_state import CHAT_HELP


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
        ('Saving to a selected ship', 'Select the account, save slot and Corvette in I/O. Optimize & Export backs up the slot and saves immediately. Slot Backups opens the backup folder. With no ship selected, choose a destination in the export dialog.'),
        ('Which exports use it', 'Only Optimize & Export applies these priorities and optional duplicate removal. Ordinary Export to Save uses the scene order. The relative order of placed cockpits and landing bays is preserved by optimization.'),
        ('Editing the list', 'Add, Remove and Rename change priority entries, not the parts in your scene. Exact duplicate removal requires every saved field to match, including transform, color and other saved data.'),
        ('Keeping settings', 'Save Settings stores priorities for future optimized exports across projects. Cancel keeps the previously saved settings. Reset to Default changes the settings draft until you save it.'),
        ('Cockpit swaps', 'Swap Cockpit/Object order is a separate, immediate scene edit. It is saved in the .blend and is not canceled when you cancel optimizer settings.'),
    )),
    'EXPORT': ('Export Corvette to Save', (
        ('Source and destination', 'Exports the current Blender scene into the chosen game save, in Main or Expedition. Review the ship slot before confirming. Exporting a .nmsship file is separate and does not write a game save.'),
        ('Ship Name', 'Enter the ship name in I/O or the sidebar Save Manager. This is the same name as the Metadata field and stays with the Blender project. Both Export to Save and Optimize & Export apply it when they write the save. Standalone .nmsship export uses it too. Leave it blank to keep the destination ship name when overwriting. A gray placeholder shows that saved name when the field is blank.'),
        ('Advanced build metadata', 'The settings icon beside Ship Name or Base Name edits the build Owner record and last-editor fields. Apply changes the Blender project. Full build JSON, clipboard and base exports retain metadata; BBE Corvette packages retain it in a versioned BBE metadata entry. Other tools may ignore that entry. Objects-only exports contain only parts. Game-save exports keep the destination Owner unless you explicitly enable Include this Owner, Apply, then export to the save. That permission resets when opening a .blend or enabling BBE.'),
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
        ('Apply a color', 'Select the parts to paint, choose a palette, then click a swatch. The current color and material appear above the palette when BBE recognizes the active part.'),
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
TOPICS.update({
    'BBE': ('BBE tools and parts', (
        ('Find a part', 'Open Assets to search the catalog. In Quick Access, choose Recent or Favourites and click a part to place it. In Search, enter at least three characters.'),
        ('Change the preview', 'Choose Simple Proxies for a lighter viewport or Detailed Proxies to show textured models. Open Themes to change the Blender interface colors.'),
    )),
    'IO': ('Import and export', (
        ('Work with a file', 'Use Import Build from File to open a build. Save BBE Project JSON keeps an editable project. Export Corvette or Export Base writes a standalone file.'),
        ('Copy objects', 'Copy Objects to Clipboard copies the current build as an Objects JSON array for pasting into a save editor. Import from Clipboard loads a copied build or replaces its parts from an Objects array.'),
        ('Clear the scene', 'Choose Clear Build Scene and confirm to remove objects and collections from the current Blender scene. Undo restores the build.'),
        ('Work with a game save', 'Choose an account and save slot, then a base type and a ship or base. Import from Save loads that build into Blender. Under Corvette, Add Minimal Corvette creates a starter ship in the chosen save.'),
        ('Save your ship', 'Check the selected destination before clicking Optimize & Export to Save. With a Corvette selected, that button backs up the slot and writes the ship immediately. Slot Backups opens the backup folder.'),
    )),
    'BUILDER': ('Builder tools', (
        ('Snap parts', 'Turn Auto-Snap on to snap compatible parts as you place them. For manual snapping, select the two parts and choose a connection. Use the Target and Source arrows to cycle their attachment points.'),
        ('Edit a selection', 'Use Duplicate or Delete on the selected parts. Group lets you move several parts together. Ungroup makes them individually editable again.'),
        ('Change build order', 'Open Swap Cockpit/Object order to exchange the export order of two instances. The dialog has its own guide to choosing the pair.'),
    )),
    'BATCH': ('Batch tools', (
        ('Build the selection', 'Select a sample part. Same Colour or Same ObjectID selects matching parts. Find Duplicates selects duplicates for inspection. Check the selection in the viewport before replacing anything.'),
        ('Replace the selection', 'Open Batch Replace, choose the replacement object or ObjectID, then click Replace. Use Blender Undo to reverse the replacement.'),
    )),
    'PREFABS': ('Prefabs', (
        ('Reuse a build', 'Select the parts you want to reuse and choose Save As Prefab. Open the Prefab Folder to find your saved files. Get More Prefabs opens a choice of community sources.'),
        ('Online catalogue', 'Click Browse or search by title, creator, description, or tag. Download a prefab to your local library, then click Place to add it to the scene. Upload Prefab shares a build file and optional thumbnail. Browsing, downloading and submitting do not require Discord.'),
        ('Edit a placed prefab', 'Select the prefab and use Split Prefab to Parts to work on its pieces. Use Group when you want selected scene parts to move together.'),
    )),
    'LOGIC': ('Cables and logic', (
        ('Place Cables', 'Choose Electrical, Teleport, or ByteBeat, then click Place Cables. Click a start and an end for each cable. Right-click, press Esc, or choose another tool, asset, or menu to finish. Electrical targets are green, teleport targets are blue, and ByteBeat targets are pink. Electrical and ByteBeat ends can also be placed in empty space.'),
        ('Hide a cable type', 'In the Outliner, click the eye beside Electrical Connections, Teleport Connections, ByteBeat Connections, or Supply Pipes. Its cables and endpoint controls hide together. Click the eye again to show them.'),
        ('Proximity-controlled door', 'Select a power door and click +Prox Control. The inverter closes the powered door until the proximity switch senses a player. BBE connects the feed to the closest visible socket on a battery, generator, solar panel, or their wired grid. If there is no supply, click a socket to finish the feed.'),
        ('New Point', 'For Electrical or ByteBeat, click New Point, then click a cable where you want a junction. Both spans stay connected. Click a destination to branch, or press Esc to keep just the junction. Click empty space to start a fresh path.'),
        ('Connect electrical devices', 'Select two or more devices, click Connect, and choose Chain (Series) or Fan (Parallel). At the cursor prompt, click a power socket or click empty space to create a shared starting point. Esc cancels before any wiring is placed.'),
        ('Chain and Fan', 'Chain runs from your start to the nearest remaining device and continues from the socket it just connected. Fan runs directly from your start to each device. Ordinary devices use their closest socket. Logic devices receive and pass the group supply through IN.'),
        ('Logic socket labels', 'IN marks the BBE supply terminal. OUT is available for switched power and TRIGGER for a control signal. BBE uses IN and OUT as wiring conventions on the two power terminals. On an inverter a powered TRIGGER turns the output off. On an auto switch it turns the output on. Use Place Cables to wire a specific OUT or TRIGGER manually.'),
        ('Disconnect', 'Select devices or junctions, choose the cable type, then click Disconnect to remove direct links between them.'),
        ('Divide', 'Select a cable of the chosen type and click Divide. Choose the number of branches and either Evenly spaced or Shared midpoint. Click a destination for each branch.'),
    )),
    'LIGHTING': ('Lighting and scenes', (
        ('Set the scene', 'Install the detailed proxy pack if prompted, then enable the scene preview. Choose an environment and quality level.'),
        ('Adjust the lighting', 'Set the brightness, sun direction and height. Turn on ship lights or glow as needed. Click Refresh Scene Preview to apply slider changes.'),
    )),
    'TOOLBAR': ('Toolbar settings', (
        ('Show and arrange menus', 'Use the checkbox beside a menu to show or hide it. The arrows move it left or right in the viewport toolbar.'),
        ('Keep the layout', 'Click Save Layout to save your Blender preferences. Reset Layout restores the default order and visibility.'),
    )),
    'THEMES': ('BBE themes', (
        ('Apply a theme', 'Click a Blender theme to apply its colors. Customize Colors & Gradients lets you edit a palette. Saved custom palettes appear under My themes.'),
        ('Keep the theme', 'Save Blender Preferences to keep the active theme after restarting.'),
    )),
    'ASSETS': ('Asset browser', (
        ('Find and place parts', 'Search by name or browse a category. Click a part image to place it. If a part offers variants, choose the one you want. Icon Size and Columns adjust the grid.'),
        ('Work with favourites and replacements', 'Open a part’s options to add or remove a favourite. Replace Selected Objects uses that asset for the selected scene parts. Use Reorder Categories to arrange the list below your favourites.'),
    )),
    'PICK_SHIP': ('Select a Corvette', (
        ('Choose the destination', 'Find the ship under Main save or Expedition and click its slot and name. Back in I/O, check the selection before importing or exporting. Clear Selection resets the destination.'),
        ('Review a warning', 'A warning beside a ship describes a problem with its saved build or slot link. Open its repair action to review the available choices.'),
    )),
    'PART_DISPLAY': ('Part display', (
        ('Open an interior', 'Enable Hide Ceiling / Roof on the selected part. Lower Opening Height to cut farther down sloped roofs or upper walls while decorating.'),
        ('Preview a beam', 'Use Show Magnetic Beam to toggle the beam on the selected module. These controls affect the Blender preview. The game export keeps the complete part.'),
    )),
    'CHAT': ('BBE Chat', CHAT_HELP),
})
TOPIC_ITEMS = tuple((key, title, paragraphs[0][1]) for key, (title, paragraphs) in TOPICS.items())


def help_button(layout, topic='COCKPIT', text='How this works'):
    row = layout.row(align=True)
    row.operator_context = 'INVOKE_DEFAULT'
    row.operator('bbe.function_help', text=text, icon='QUESTION').topic = topic


def corner_help(header, topic):
    button = header.row(align=True)
    button.alignment = 'RIGHT'
    button.ui_units_x = 1.25
    button.operator_context = 'INVOKE_DEFAULT'
    button.operator('bbe.function_help', text='', icon='QUESTION').topic = topic


class BBE_OT_function_help(bpy.types.Operator):
    bl_idname = 'bbe.function_help'
    bl_label = 'BBE Feature Help'
    bl_description = 'Read what this tool changes, when it takes effect, what is preserved, and how to undo or recover'
    topic: bpy.props.EnumProperty(name='Feature', items=TOPIC_ITEMS)

    @classmethod
    def description(cls, context, properties):
        return 'How to use ' + TOPICS[properties.topic][0]

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

"""Local, read-only explanations shared by tool dialogs and both BBE menus."""
from functools import lru_cache

import bpy
from ..bbe_chat_state import CHAT_HELP
from .. import i18n


TOPICS = {
    'CURVES': ('HOW TO - Curve Tools', (
        ('Draw or choose a shape', 'Draw Smooth Curve uses the chosen plane. The colored shape buttons create a circle, ellipse, arc, spiral, helix or wave. Select the curve to edit its dimensions and points.'),
        ('Connect Endpoints', 'Connect with Line joins two endpoints with a straight segment. Move & Connect Curves moves the entire first curve onto the second endpoint and joins them. Start New Curve Here starts a preset or a drawn path at the chosen point.'),
        ('Rotate along the curve', 'In the curve piece controls, adjust rotation along the guide to progressively roll each repeated part around the path. Reduce the amount to unwind the run.'),
        ('Taper', 'Taper keeps the first copy at full size and gradually shrinks each following copy. Set it to zero to restore their sizes.'),
        ('Edges and faces', 'Curve from Edges / Faces opens in Edges mode. Hover near a visible boundary to preview an edge section, then click to add it. Faces selects a broad patch and centers a path between its outer edges. Click a selected section again to remove it.'),
        ('Draw on Surface', 'Use a short stroke as a highlighter to indicate direction. The tool creates a clean surface-following path. It does not trace every wobble of your stroke.'),
        ('Rotate and create', 'For a face or drawn path, drag the ring or diamond with the hand cursor. Type degrees while holding it, or use Rotate 90 degrees. Ctrl+Z undoes, Ctrl+Y redoes. Create Curves or Enter makes editable curves; Esc cancels. You can reopen the tool to create another curve.'),
        ('Edit and place parts', 'Select a curve or its linked object to reveal controls below. Diamonds move points; round tips shape bends. Smooth, Open / Close, Insert Point and Remove Point edit the curve. Use Duplicate Along Curve to arrange selected parts on it.'),
    )),
    'COCKPIT': ('Swap Cockpit/Object order', (
        ('What changes', 'Choose Cockpits or an object type with duplicate Object IDs, then choose two named instances. Swap Order immediately exchanges their positions in the exported object list. Their physical positions, rotations, sizes and colors stay the same.'),
        ('When it takes effect', 'Swap Order changes ordinary export order immediately. Automatic optimization also preserves cockpit order. If you set a manual order in the optimizer, edit its Ship parts list to change the optimized export. Cockpit encounter order can affect the roles assigned by the game.'),
        ('Keeping or undoing it', 'Save the .blend to keep the order with this project. Ctrl+Z undoes the scene edit. Other projects keep their own order; this is not a global setting.'),
        ('Separate from optimizer settings', 'Canceling Optimizer Settings does not undo an object-order swap you already confirmed. Use Ctrl+Z to undo that swap.'),
    )),
    'OPTIMIZER': ('Corvette Optimizer', (
        ('What changes', 'Optimize & Export arranges exported parts by category and priority. Earlier entries come first. Your Blender objects stay in place.'),
        ('Saving to a selected ship', 'Select the account, save slot and Corvette in I/O. Optimize & Export backs up the slot and saves immediately. Slot Backups opens the backup folder. With no ship selected, choose a destination in the export dialog.'),
        ('Ship parts', 'Find an instance by name or Object ID. The number is its position in the full export. Select it and use the arrows to move it one place or directly to the first or last position. Reordering cockpits or landing bays can change their in-game roles.'),
        ('Keeping ship order', 'Apply Settings keeps the manual order with this build. Save the .blend to keep it after closing Blender. Newly added parts follow manually ordered parts. Use priority rules returns this build to automatic ordering.'),
        ('Priority rules', 'Categories and part types set the automatic order across projects. Automatic ordering preserves the relative order of cockpits and landing bays. Exact duplicate removal requires every saved field to match.'),
        ('Which exports use it', 'Optimize & Export uses these settings. Ordinary Export to Save uses scene order. Cancel discards edits in this dialog.'),
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
        ('Build timer', 'Read elapsed build time beside the selected build in Save Manager. In Workspace Settings, open Display to set the idle interval or turn the timer off.'),
        ('Find a part', 'Open Assets to search the catalog. In Quick Access, choose Recent or Favourites and click a part to place it. In Search, enter at least three characters.'),
        ('Change the preview', 'Choose Simple Proxies for a lighter viewport or Detailed Proxies to show textured models. Open Themes to change the Blender interface colors.'),
    )),
    'IO': ('Import and export', (
        ('Work with a file', 'Use Import Build from File to open a build. Save BBE Project JSON keeps an editable project. Export Corvette or Export Base writes a standalone file.'),
        ('Copy objects', 'Copy Objects to Clipboard copies the current build as an Objects JSON array for pasting into a save editor. Import from Clipboard loads a copied build or replaces its parts from an Objects array.'),
        ('Clear the scene', 'Choose Clear Build Scene and confirm to remove objects and collections from the current Blender scene. Undo restores the build.'),
        ('Work with a game save', 'Choose an account and save slot, then a base type and a ship or base. Import from Save loads that build into Blender. Under Corvette, Add Minimal Corvette creates a starter ship in the chosen save.'),
        ('Save changes', 'Export to Save checks for changes on disk. If the game saved since you chose a base, BBE refreshes the list and keeps the same destination when it can identify it.'),
        ('Build timer', 'Read elapsed build time beside the selected build in Save Manager. In Workspace Settings, open Display to set the idle interval or turn the timer off.'),
        ('Save your ship', 'Check the selected destination before clicking Optimize & Export to Save. With a Corvette selected, that button backs up the slot and writes the ship immediately. Slot Backups opens the backup folder.'),
    )),
    'BUILDER': ('Builder tools', (
        ('Snap parts', 'Turn Auto-Snap on to snap compatible parts as you place them. For manual snapping, select the two parts and choose a connection. Use the Target and Source arrows to cycle their attachment points.'),
        ('Edit a selection', 'Use Duplicate or Delete on the selected parts. Group lets you move several parts together. Ungroup makes them individually editable again.'),
        ('Mirror across an origin', 'Select the parts to mirror in Builder. Choose the axis and pivot, including Object Origin when needed. Enable Auto Duplicate to keep the originals.'),
        ('Change build order', 'Open Swap Cockpit/Object order to exchange the export order of two instances. The dialog has its own guide to choosing the pair.'),
        ('Duplicate parts', 'Click Duplicate to copy the selection once. In the sidebar, open Along… for two more ways to copy. Duplicate Along Edge Path follows the edges you pick. Duplicate Along Axis repeats the selection along X, Y, or Z.'),
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
        ('Place Cables', 'Choose Electrical, Teleport, ByteBeat, or Supply Pipe, then click Place Cables. Click a start and an end for each cable, then repeat. Right-click, press Esc, or choose another tool, asset, or menu to finish. Electrical targets and cables are blue, teleport cyan, ByteBeat pink, and supply orange. Green targets are structural snaps. Electrical, ByteBeat, and supply ends can also be placed in empty space.'),
        ('Supply pipes', 'Connect gas or mineral extractors to supply depots using orange supply sockets. These are separate from electrical sockets. You can also place free endpoints or branch an existing supply pipe.'),
        ('Show or hide connectors', 'Use the eye button in the viewport toolbar to show or hide connectors. Place Cables shows compatible sockets while you work and restores your visibility setting when you finish. To hide the cables themselves, use their collection in the Outliner.'),
        ('Hide a cable type', 'In the Outliner, click the eye beside Electrical Connections, Teleport Connections, ByteBeat Connections, or Supply Pipes. Its cables and endpoint controls hide together. Click the eye again to show them.'),
        ('Proximity-controlled door', 'Select a power door and click +Prox Control. The inverter closes the powered door until the proximity switch senses a player. BBE connects the feed to the closest visible socket on a battery, generator, solar panel, or their wired grid. If there is no supply, click a socket to finish the feed.'),
        ('New Point', 'For Electrical, ByteBeat, or Supply Pipe, click New Point, then click a matching cable where you want a junction. Both spans stay connected. Click a destination to branch, or press Esc to keep just the junction. Click empty space to start a fresh path. Teleport cables cannot branch.'),
        ('Connect electrical devices', 'Select two or more devices, click Connect, and choose Chain (Series) or Fan (Parallel). At the cursor prompt, click a power socket or click empty space to create a shared starting point. Esc cancels before any wiring is placed.'),
        ('Chain and Fan', 'Chain runs from your start to the nearest remaining device and continues from the socket it just connected. Fan runs directly from your start to each device. Ordinary devices use their closest socket. Logic devices receive and pass the group supply through IN.'),
        ('Logic socket labels', 'IN marks the BBE supply terminal. OUT is available for switched power and TRIGGER for a control signal. BBE uses IN and OUT as wiring conventions on the two power terminals. On an inverter a powered TRIGGER turns the output off. On an auto switch it turns the output on. Use Place Cables to wire a specific OUT or TRIGGER manually.'),
        ('Disconnect', 'Select devices or junctions, choose the cable type, then click Disconnect to remove direct links between them.'),
        ('Divide', 'Select an electrical, ByteBeat, or supply cable of the chosen type and click Divide. Choose the number of branches and either Evenly spaced or Shared midpoint. Click a destination for each branch.'),
    )),
    'LIGHTING': ('Lighting and scenes', (
        ('Set the scene', 'Install the detailed proxy pack if prompted, then enable the scene preview. Choose an environment and quality level.'),
        ('Adjust the lighting', 'Set the brightness, sun direction and height. Turn on ship lights or glow as needed. Click Refresh Scene Preview to apply slider changes.'),
    )),
    'TOOLBAR': ('Toolbar settings', (
        ('Show and arrange menus', 'Open Workspace Settings in BBE. Choose Top Bar or Sidebar, drag menu handles to set their order, and use each switch to show or hide its menu. Display controls the Part Count and Active Object Properties overlays.'),
        ('Keep the layout', 'Click Save Layout to save your Blender preferences. Reset Layout restores the default order and visibility.'),
    )),
    'THEMES': ('BBE themes', (
        ('Apply a theme', 'Click a Blender theme to apply its colors. Customize Colors & Gradients lets you edit a palette. Saved custom palettes appear under My themes.'),
        ('Keep the theme', 'The selected theme is saved automatically.'),
    )),
    'ASSETS': ('Asset browser', (
        ('Browse and reorder categories', 'In the pop-out, select a category on the left to see its subcategories. Search and both category fields are also at the top. Click Reorder to move categories with the arrows, or Reset to A–Z to restore alphabetical order within the pinned and unpinned groups.'),
        ('Find and place parts', 'Search by name or browse a category. Click a part image to place it. Click the two-bar badge to see variant thumbnails. Click the thumbnail you want to place, or return with the back arrow beside the first variant. In the horizontal browser, click Close variants. Icon Size and Columns adjust the grid.'),
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
TOPICS.update({
    'SNAP': ('Snap two selected parts', (
        ('Snap at a socket', 'Show connectors. Select the part to move, then Shift-select the receiving part so it is active. Click Snap beside the selection. Click a green target to change the connection; click it again to cycle source sockets.'),
    )),
    'WORKSPACE': ('Simplify and restore the workspace', (
        ('Switch layouts', 'Open the BBE menu in the sidebar and click Simplify Blender Workspace. The building tab stays visible and Properties focuses on Object when available. Detached editors stay in place. Click Restore Blender Workspace to bring back your tabs and settings.'),
    )),
    'DUPLICATE': ('Duplicate along an axis or edge path', (
        ('Along Axis', 'Select the part or group to repeat. In Builder, choose Duplicate Along Axis, choose Global or Part Local, then click X, Y or Z. Part Local follows the orientation of the active selected part. Adjust Copies, Spacing or Distance in the axis panel.'),
        ('Along Edge Path', 'Select the parts to repeat, choose Duplicate Along Edge Path in Builder and click a straight or rounded section. Click adjoining sections to extend the path. Click a selected end to remove it. Clicking a middle section trims the highlighted side back to that point. Before creating copies, drag the Keep edge range handles or click Keep longest straight section to remove rounded corners. Click Continue to Copies when the highlighted section looks right. Pick an edge on the part itself to continue it edge to edge. The first copy starts one part-width along the path. Use Spacing to leave a gap or overlap the parts. You can adjust the range again in the repeat controls. Increasing the run afterward continues along its final tangent.'),
    )),
    'ALIGN': ('Align points, edges or faces', (
        ('Align two features', 'Open Builder and choose Align. Edges opens first. Pick the feature on the piece to move, then its destination. The actual piece moves into contact. Rotate about the face normal or edge with the 90° buttons, drag the angle, or click it to type degrees. For points, choose a world axis. Flip piece turns a face over. Place keeps the result. Cancel restores the starting pose.'),
    )),
    'SELECTED_PART': ('Selected part controls', (
        ('Edit Message', 'Select a Message Module and click Edit Message beside it. Confirm the text to update the Message custom property.'),
        ('Interior and Beam Options', 'Select an enclosed hab to open Interior and adjust how much of its roof is visible. On a compatible beam module, open Beam Options to change its preview.'),
        ('Attach a cable', 'Show connectors and select a compatible device. Use the attachment button beside it to start from its socket, then click the destination. Power doors also offer proximity control.'),
        ('Pipe Roll', 'Select the supply pipe and use its rotation ring, or press R and type an angle. The two tubes turn around the line between the endpoints. Move either free endpoint to change the pipe direction.'),
    )),
    'STRIP': ('Horizontal asset browser and variants', (
        ('Open the asset strip', 'Click the arrow beside Assets in the top bar. Choose a category and subcategory or search across categories. Scroll sideways through parts and click a thumbnail to place it. Drag the bottom grip to resize the row.'),
        ('Open a variant family', 'Click the two-line badge on a thumbnail with variants. Choose a variant from the row or close the family to return to your previous category.'),
    )),
    'SHAPES': ('Shapes and Shape Studio', (
        ('Create and edit a shape', 'Open Shapes, choose 2D shape or 3D shell, then click a thumbnail. In Shape Studio click the part ID to type an ID or pick a part from the viewport or asset browser. Select a generated part again to edit the shape.'),
        ('Control the surface', 'Use Outline or Fill for 2D shapes. For shells, Choose Faces controls which surfaces get pieces. Outside Face chooses which side of each piece faces outward. Adjust piece scale and Fill Gaps, then bend, pinch or twist the shape.'),
        ('Place a second shape', 'Choose New Shape in the studio to reuse the current part. Choose the 3D cursor or align by point, edge or face, then follow the source and target prompts.'),
    )),
    'REPEAT': ('Repeat Along from a snap target', (
        ('Repeat one part or a row', 'Select a supported wall, floor, roof or a row of compatible parts. Click Repeat Along beside the selection, click a socket, then drag a direction arrow and release to place the copies. Shared wall junctions can start a perpendicular row.'),
        ('Habs and straight runs', 'Choose a hab opening to repeat end to end, side by side or vertically where supported. Straight pipe and bubble-tube sections extend along the run.'),
        ('Add stairs between stacked habs', 'Select two vertically connected habs. Click Add Stairs, then choose a shared landing if more than one is available.'),
    )),
    'CUTAWAY': ('Viewport Cutaway', (
        ('Look inside a build', 'In Workspace Settings, open Display and enable Viewport Cutaway. Drag either end of an X, Y or Z slider inward. Click the corner switch to see the whole build and click again to resume. Use Refit to Build after extending the build.'),
    )),
    'TRANSFORM': ('Transform', (
        ('Move, rotate, scale and copy', 'Open Transform in the sidebar or show its top tab in Workspace Settings. Select a part to edit its transform. Copy its transform and use Paste on the destination selection.'),
    )),
    'SAVE_MANAGER': ('Save Manager', (
        ('Import and export', 'In I/O or the Save Manager sidebar, turn the manager on. Pick account, slot, type and named build, then Import from Save. When ready, export to the selected destination. For Corvettes use Optimize & Export to Save.'),
    )),
    'PILOT': ('Cockpit pilot reference', (
        ('Preview a pilot', 'Select a single supported cockpit. Choose a pilot in the viewport controls to preview its size and seat position. Hide, show or remove the reference from the same controls.'),
    )),
    'SUPPORT': ('Updates and support', (
        ('Find the installed version or report a problem', 'Open Updates & Support in the sidebar to check the installed release and access support and Blender diagnostics.'),
    )),
    'BOUNDARY': ('1000u base boundary', (
        ('Show rings or a wire sphere', 'After importing a supported base, expand Build Boundary in the Outliner. Use the eye beside Rings or Wire Sphere to show that guide. The collection eye controls both.'),
    )),
    'DECALS': ('Position a decal', (
        ('Place on Surface', 'Select a decal and click Place on Surface beside it. Click the desired surface. Use Rotate, Closer or Away to fine-tune its position. Projection Preview switches the projected appearance on or off.'),
    )),
    'TUBES': ('Bubble tube openings and branches', (
        ('Choose opening direction', 'Select a supported tube junction. Use the arrows on its viewport controls to preview another opening direction. Finish connecting open elbows before exporting a Corvette.'),
    )),
})
ADDITIONAL_STEPS = {
    'THEMES': (
        ('Change button styling', 'Open Themes and look under Blender Button Style. Choose Flat or Rounded for Blender controls. Choose Use theme to restore the styling supplied with your theme.'),
    ),
    'CUTAWAY': (
        ('Keep a slice while changing view', 'Move the handles inward from the outer edges of your ship, base or station. Switch between Solid, Material Preview and Wireframe to inspect the same slice. The corner switch temporarily shows the complete build.'),
    ),
    'ASSETS': (
        ('Check Corvette part bonuses', 'Hover over a compatible Corvette part in an asset browser to see its bonus ranges before placing it. The final values depend on the build.'),
        ('Place a local prefab', 'Choose Presets in the sidebar or pop-out browser. In the horizontal browser, choose Presets / Prefabs and a folder. Click a tile to place the whole group.'),
        ('Prefab Previews', 'Open the presets category and switch on Prefab Previews to generate thumbnails for visible items. All three browsers share the setting. Switch it off to stop rendering and keep browsing by name.'),
        ('Auto-Snap', 'Click the floating Auto-Snap switch to change how the next part is placed. Scroll over the grid to browse the tiles underneath it.'),
    ),
    'PREFABS': (
        ('Find your local prefabs', 'Open Local Prefab Library, type in the search field, or scroll the list. Click a name to place it. Enable Prefab Previews here to see the same thumbnails in your asset browsers.'),
        ('Browse a community', 'Open Online Community Prefabs and choose a server icon. Click a thumbnail to enlarge it and close the image to return to the same spot. Use its download icon to add it to your library. The server name opens its Discord invite when one is available.'),
        ('Resize the catalogue', 'Drag the bottom grip to change how many cards you can see. Scroll through the cards or search for a prefab by name.'),
    ),
    'WORKSPACE': (
        ('Arrange the menus', 'Open BBE, then Workspace Settings. Choose Top Bar or Sidebar. Drag a menu by its handle to reorder it, use the switch to change its visibility, then choose Save Layout. Each list has its own order.'),
        ('Viewport information', 'On the Display page, enable Part Count or Active Object Properties and choose Top or Bottom for each. Select a build part to see its properties.'),
        ('Language and navigation', 'Open Workspace Settings and choose Display. Select a language or Follow Blender. Use the WASD switch and the speed and sensitivity controls to adjust viewport navigation.'),
    ),
    'CURVES': (
        ('Draw in a plane', 'Choose Top / Down for a flat outline, then Draw Smooth Curve. Adjust Control points after drawing to change how many handles you can move.'),
        ('Keep tapered copies touching', 'Start with full-size copies. Set Spacing so the first two touch, then increase Taper. Spacing shrinks with each copy. Increase the copy count if the run ends early.'),
        ('Twist along curve', 'Use Twist along curve to roll the copies progressively. Enter 360 degrees for one turn or a negative angle to reverse it.'),
        ('Taper a corkscrew or spiral', 'Choose a Corkscrew or Spiral preset. Increase Radius taper to narrow the last winding, or use a negative value to widen it.'),
        ('Use Blender Tools', 'In the piece controls, enable Use Blender Tools to keep your Blender transform gizmo. Reselect the curve or a linked part to return to the studio.'),
    ),
    'SHAPES': (
        ('Fit a filled outline', 'Choose a 2D shape and select Fill. Set the outside face of the part first. Increase Edge detail to refine corners and set Part limit to control the number of pieces.'),
        ('Preserve edges', 'For a faceted shell such as a pyramid, enable Preserve edges to keep pieces inside each face boundary. Adjust Piece scale with Fill Gaps enabled to refit the surface.'),
        ('Pick the outside face', 'Click Pick outside face, drag to rotate the part preview, then click the side that should face outward. Use Populate shell faces to choose which surfaces of the whole shape receive parts.'),
        ('Edit the pieces', 'Select a generated part to reopen Shape Studio. Open Pieces to move or rotate the repeated parts together. Enable Use Blender Tools to work with your usual transform gizmo.'),
    ),
    'LOGIC': (
        ('Copy a cable', 'Select the cable itself and use Ctrl+C, then Ctrl+V in the viewport. Select a free endpoint on the pasted cable to move it, or use the axial rotation ring on a supply pipe to turn both tubes together.'),
        ('Move or attach an endpoint', 'Move a free endpoint with the Move tool. To attach it, move it over a compatible socket and click Snap Endpoint. A snapped endpoint follows its device.'),
        ('Pair short-range teleporters', 'Choose Teleport Wire and Place Cables. Click the cyan socket on each short-range teleporter. On a Corvette, the teleporters can operate without a separate power cable.'),
    ),
    'TUBES': (
        ('Finish a chain for export', 'Check the unfinished opening named in the export message. Connect a matching tube at that opening or remove the unfinished junction. Run the export again when the chain is complete.'),
    ),
    'COLOUR': (
        ('Choose a material finish', 'Choose the palette family, then use the material icons above the swatches to switch finishes. Click a swatch to apply it to the selected parts.'),
        ('Sample a part', 'Choose Pick Colour from Object and click a painted part in the viewport to sample its colour.'),
    ),
    'SAVE_MANAGER': (
        ('Find GOG saves', 'On Windows, choose the HelloGames/NMS folder or open DefaultUser directly. Select GOG (DefaultUser) and your save slot. Steam accounts can appear alongside GOG.'),
        ('Read the export highlights', 'After choosing a different ship or base, use the green Import from Save button to load it. After editing, check the destination again. Blue highlights Optimize & Export for a Corvette or Export to Save for a base.'),
        ('Manage backups', 'Use the folder settings beside the Save Manager heading to choose a backup location and how many generations to keep per save slot. Open the backup folder to find earlier copies.'),
    ),
    'IO': (
        ('Name your build', 'Enter a Build Name before using Copy All or saving a project, base or Corvette file. The Corvette name field in Save Manager edits the same name. Copy Objects includes only parts.'),
        ('Find the imported build', 'After importing, the viewport frames the build and clears the selection. Click a part in the viewport or the Outliner to start editing.'),
        ('Choose a clipboard format', 'Use Copy All for a full build with metadata. Use Copy Objects when the destination expects only an array of parts. Paste into the matching field in your save editor and check the destination before saving.'),
    ),
    'PART_DISPLAY': (
        ('Preview a Corvette fitting', 'Snap a compatible utility module or window to its hab socket. Use Detailed Proxies to inspect how the fitting and the hab wall meet.'),
    ),
    'DUPLICATE': (
        ('Adjust the run', 'Set the number of copies, then adjust spacing in the duplication controls. On an edge path, increasing the run past its last point continues in the final edge direction.'),
    ),
}
for topic_id, extra in ADDITIONAL_STEPS.items():
    title, sections = TOPICS[topic_id]
    TOPICS[topic_id] = title, sections + extra

@lru_cache(maxsize=8)
def _topic_items(locale):
    return tuple((key, i18n.for_locale(locale, title), i18n.for_locale(locale, steps[0][1]))
                 for key, (title, steps) in TOPICS.items())


def topic_items(_self, context):
    return _topic_items(i18n.interface_locale() if context else '')


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



@lru_cache(maxsize=8)
def _localized_guide_items(locale):
    def translate(message):
        return i18n.for_locale(locale, message)
    return tuple((f'{key}.{index}', f'{translate(title)}  /  {translate(heading)}', translate(body))
                 for key, (title, steps) in TOPICS.items()
                 for index, (heading, body) in enumerate(steps))


def guide_items(_self, context):
    return _localized_guide_items(i18n.interface_locale() if context else '')


class BBE_OT_find_guide(bpy.types.Operator):
    bl_idname = 'bbe.find_guide'
    bl_label = 'How-To Guide'
    bl_description = 'Search menus and tools by name, including buttons shown beside selected parts'
    bl_translation_context = i18n.CONTEXT
    bl_property = 'entry'
    entry: bpy.props.EnumProperty(name='Find a tool', items=guide_items)

    def invoke(self, context, event):
        if context.area and context.area.type == 'VIEW_3D' and not bpy.app.background:
            result = bpy.ops.bbe.function_help('INVOKE_DEFAULT', browse=True)
            return {'FINISHED'} if 'RUNNING_MODAL' in result else result
        context.window_manager.invoke_search_popup(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        key, section = self.entry.split('.')
        bpy.ops.bbe.function_help('INVOKE_DEFAULT', topic=key, section=int(section), source_topic=key)
        return {'FINISHED'}


class BBE_OT_function_help(bpy.types.Operator):
    bl_idname = 'bbe.function_help'
    bl_translation_context = "BBEExtendedInterface"
    bl_label = 'BBE Feature Help'
    bl_description = 'Read what this tool changes, when it takes effect, what is preserved, and how to undo or recover'
    topic: bpy.props.EnumProperty(translation_context="BBEExtendedInterface", name='Feature', items=topic_items)

    section: bpy.props.IntProperty(default=-1)
    source_topic: bpy.props.StringProperty()
    browse: bpy.props.BoolProperty(options={'SKIP_SAVE'}, default=False)
    query: bpy.props.StringProperty(name='Search the guide', options={'SKIP_SAVE'})

    @classmethod
    def description(cls, context, properties):
        return i18n.tooltip('How to use {feature}').format(feature=i18n.tooltip(TOPICS[properties.topic][0]))

    def invoke(self, context, event):
        if context.area and context.area.type == 'VIEW_3D' and not bpy.app.background:
            from .guide_browser import GuideBrowser
            self._editor = GuideBrowser(self)
            self._editor.scene = context.scene
            return self._editor.invoke(context,event)
        return context.window_manager.invoke_popup(self, width=590)

    def modal(self, context, event):
        return self._editor.modal(context,event)

    def cancel(self, context):
        editor = getattr(self,'_editor',None)
        if editor and not editor.closed:
            editor.finish()

    def draw(self, context):
        i18n.localized_layout(self.layout).prop(self, 'topic', text='Feature')
        self.layout.operator_context = 'INVOKE_DEFAULT'
        layout = i18n.localized_layout(self.layout)
        layout.operator('bbe.find_guide', text=i18n.interface('Search How-To Guide'), icon='VIEWZOOM')
        sections = TOPICS[self.topic][1]
        if self.source_topic == self.topic and 0 <= self.section < len(sections):
            sections = (sections[self.section],)
        for heading, paragraph in sections:
            box = i18n.localized_layout(self.layout).box()
            box.label(text=i18n.interface(heading), translate=False)
            col = box.column(align=True)
            for line in i18n.wrapped(paragraph, 78):
                col.label(text=line, translate=False)

    def execute(self, context):
        return {'FINISHED'}


def register():
    bpy.utils.register_class(BBE_OT_find_guide)
    bpy.utils.register_class(BBE_OT_function_help)


def unregister():
    bpy.utils.unregister_class(BBE_OT_function_help)
    bpy.utils.unregister_class(BBE_OT_find_guide)

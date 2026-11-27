# Base Builder Extended 18.3.4

## New since 18.3.3

- **Connected cable cleanup** — Delete one part or a selection and choose whether to remove its snapped electrical wires, supply pipes, teleport cables, and ByteBeat cables. Cleanup removes unused connection points and keeps junctions that still serve another cable.
- **NMS performance impact** — Hover over the bar beneath an asset in any browser for its estimated cost. The score includes models, textures, animations, lights, and particle effects.
- **Analyze Build** — In Builder Tools, select **Analyze Build** to colour the parts in your viewport by estimated game cost. Select **Exit Build Analysis** to return to your build colours.
- **Horizontal asset options** — Click the upper-left menu or right-click an asset for placement, favourites, and replacement.
- **ByteBeat cable thickness** — Scale a free-placed cable to change its thickness. Cables snapped to a device retain their socket width.

## Performance and fixes

- **Group** now waits for you to choose a pivot and confirm in the Builder and Prefabs menus.
- **Batch → Same Colour** now selects matching paint across part IDs and material finishes. **Object ID** still selects by part type.
- Collapsing the sidebar to its vertical tabs now hides BBE’s panel icons and controls.
- **Sidebar Quick Access** opens on Recent. Favourites shows up to five parts at a time. Use the mouse wheel or drag the scrollbar to reach the rest.
- Faster startup, asset browsing, and large build imports. Idle viewports do less background work.
- **Cables & Logic → Divide** splits a selected cable and creates a junction.
- Placing a prefab no longer opens Curve Studio when its outline is selected.

# Base Builder Extended 18.3.3

## New in 18.3.3

- The asset browsers include the new Corvette parts, decorations, decals, and red and green Prismatic Cores. Newly added parts are highlighted until first selected.
- Simple proxies ship with BBE. Existing Detailed Proxy installations automatically fetch the updated HD additions when Blender allows online access.

## Fixes

- The decal projection preview remembers your choice across decals.
- Whole-build moves include selected cable endpoints and junctions.
- Curve-linked builds preserve their saved placement when opened without BBE.
- Deleting a cockpit also removes its attached pilot reference.

# Base Builder Extended 18.3.2

## Changes since 18.3.1

- Move, Rotate, and Scale show one live measurement below the BBE top bar or the open horizontal asset browser. Hiding the top bar keeps Blender’s native readout.
- The graphical sidebar now appears on Blender 5.2 LTS and 5.3. Theme application on 5.3 and detailed supply pipe previews on 5.2 and 5.3 have also been fixed.
- Save Manager recognizes GOG’s `DefaultUser` account on Windows. Choose `HelloGames/NMS` or the account folder directly.
- **Build Name** is available in the top-bar I/O menu and the Import/Export sidebar. It shares the existing Save Manager name field. Copy All, project JSON, base files, and Corvette packages carry the name. Copy Objects copies parts only.

# Base Builder Extended 18.3.1

- Align previews the actual part against a picked point, edge or face. Face and edge alignment allow rotation around the connection.
- Duplicate Along Edge Path lets you add or remove connected sections and trim the route before making copies. Repeating a part on its own straight edge continues it edge to edge.
- Duplicate Along Axis supports switching between world axes and the selected part's axes.
- Viewport action buttons leave more clearance around transform gizmos.
- Automatic updates check the Blender extension repository before closing BBE tools. A busy repository delays installation and the downloaded package is retried. Updating an enabled extension no longer saves global Blender preferences.

# Base Builder Extended 18.3.0

## New features since 18.2.48

### Build and place parts

- [Smart edge tracing tolerance](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#smart-edge-tracing-tolerance)
- [Shape Studio for 2D shapes and 3D shells](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#shape-studio-for-2d-shapes-and-3d-shells)
- [Repeat Along at snap sockets](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#repeat-along-at-snap-sockets)
- [Stack Corvette habs and add stairs](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#stack-corvette-habs-and-add-stairs)
- [Duplicate along an axis or edge path](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#duplicate-along-an-axis-or-edge-path)
- [Align by point, edge or face](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#align-by-point-edge-or-face)
- [Object-origin mirroring and transform copying](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#object-origin-mirroring-and-transform-copying)
- [Curve connections, tapered runs and progressive twist](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#curve-connections-tapered-runs-and-progressive-twist)
- [Hab-specific utility walls and windows](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#hab-specific-utility-walls-and-windows)
- [Edit Message Modules in the viewport](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#edit-message-modules-in-the-viewport)

### Inspect a build

- [Viewport cutaway on three axes](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#viewport-cutaway-on-three-axes)
- [1000u base boundary rings and sphere](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#1000u-base-boundary-rings-and-sphere)
- [Supply pipes and editable cable endpoints](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#supply-pipes-and-editable-cable-endpoints)
- [Color-coded connectors and a visibility switch](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#color-coded-connectors-and-a-visibility-switch)
- [Bubble-tube chain checks before export](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#bubble-tube-chain-checks-before-export)

### Find assets and prefabs

- [Horizontal asset browser and visual variants](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#horizontal-asset-browser-and-visual-variants)
- [Corvette part bonus tooltips](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#corvette-part-bonus-tooltips)
- [Local prefab thumbnail previews](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#local-prefab-thumbnail-previews)
- [Community prefab galleries by Discord channel](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#community-prefab-galleries-by-discord-channel)
- [Material finish icons and viewport color sampling](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#material-finish-icons-and-viewport-color-sampling)

### Save and customize

- [Offline interface languages](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#offline-interface-languages)
- [Remembered decal and workspace settings](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#remembered-decal-and-workspace-settings)
- [Shared backup folder and retention settings](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#shared-backup-folder-and-retention-settings)
- [Guided imports and exports in Save Manager](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#guided-imports-and-exports-in-save-manager)
- [Manual Corvette part ordering and cockpit swaps](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#manual-corvette-part-ordering-and-cockpit-swaps)
- [Build timer and idle tracking](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#build-timer-and-idle-tracking)
- [Customizable menus, workspace and language](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#customizable-menus-workspace-and-language)
- [Searchable and draggable How-To browser](https://github.com/slipperystickers/nms-base-builder/blob/v18.3.0/docs/releases/18.3.0/guide.md#searchable-and-draggable-how-to-browser)

## Fixes for previously published features

- Fix Windows installs failing while unpacking Qt artwork in long Blender extensions paths.

- Preserve decal projection and orientation when replacing a decal.
- Keep every wire connected when rebuilding a shared cable junction.
- Restore the previous Blender transform tool and gizmos when leaving Curve Studio.
- Keep Curve Studio number fields open for editing and use whole numbers for copy counts.

## Installation

Users on 18.2.118 can update normally. BBE reuses the verified Detailed pack from that release.

Install **no_mans_sky_base_builder-18.3.0.zip** through Blender or use the BBE updater. Simple Proxies come with the extension. For textured models, select **BBE → Detailed Proxies** and allow Blender online access. If you already use the HD library, BBE checks its components and downloads the updated additions automatically. The HD additions ZIP is a library component managed by BBE.

# Base Builder Extended 18.2.118

## New features since 18.2.48

### Build and place parts

- [Smart edge tracing tolerance](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#smart-edge-tracing-tolerance)
- [Shape Studio for 2D shapes and 3D shells](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#shape-studio-for-2d-shapes-and-3d-shells)
- [Repeat Along at snap sockets](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#repeat-along-at-snap-sockets)
- [Stack Corvette habs and add stairs](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#stack-corvette-habs-and-add-stairs)
- [Duplicate along an axis or edge path](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#duplicate-along-an-axis-or-edge-path)
- [Align by point, edge or face](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#align-by-point-edge-or-face)
- [Object-origin mirroring and transform copying](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#object-origin-mirroring-and-transform-copying)
- [Curve connections, tapered runs and progressive twist](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#curve-connections-tapered-runs-and-progressive-twist)
- [Hab-specific utility walls and windows](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#hab-specific-utility-walls-and-windows)
- [Edit Message Modules in the viewport](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#edit-message-modules-in-the-viewport)

### Inspect a build

- [Viewport cutaway on three axes](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#viewport-cutaway-on-three-axes)
- [1000u base boundary rings and sphere](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#1000u-base-boundary-rings-and-sphere)
- [Supply pipes and editable cable endpoints](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#supply-pipes-and-editable-cable-endpoints)
- [Color-coded connectors and a visibility switch](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#color-coded-connectors-and-a-visibility-switch)
- [Bubble-tube chain checks before export](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#bubble-tube-chain-checks-before-export)

### Find assets and prefabs

- [Horizontal asset browser and visual variants](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#horizontal-asset-browser-and-visual-variants)
- [Corvette part bonus tooltips](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#corvette-part-bonus-tooltips)
- [Local prefab thumbnail previews](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#local-prefab-thumbnail-previews)
- [Community prefab galleries by Discord channel](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#community-prefab-galleries-by-discord-channel)
- [Material finish icons and viewport color sampling](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#material-finish-icons-and-viewport-color-sampling)

### Save and customize

- [Offline interface languages](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#offline-interface-languages)
- [Remembered decal and workspace settings](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#remembered-decal-and-workspace-settings)
- [Shared backup folder and retention settings](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#shared-backup-folder-and-retention-settings)
- [Guided imports and exports in Save Manager](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#guided-imports-and-exports-in-save-manager)
- [Manual Corvette part ordering and cockpit swaps](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#manual-corvette-part-ordering-and-cockpit-swaps)
- [Build timer and idle tracking](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#build-timer-and-idle-tracking)
- [Customizable menus, workspace and language](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#customizable-menus-workspace-and-language)
- [Searchable and draggable How-To browser](https://github.com/slipperystickers/nms-base-builder/blob/v18.2.118/docs/releases/18.2.118/guide.md#searchable-and-draggable-how-to-browser)

## Fixes for previously published features

- Preserve decal projection and orientation when replacing a decal.
- Keep every wire connected when rebuilding a shared cable junction.
- Restore the previous Blender transform tool and gizmos when leaving Curve Studio.
- Keep Curve Studio number fields open for editing and use whole numbers for copy counts.

## Installation

Install **no_mans_sky_base_builder-18.2.118.zip** through Blender or use the BBE updater. Simple Proxies come with the extension. For textured models, select **BBE → Detailed Proxies** and allow Blender online access. If you already use the HD library, BBE checks its components and downloads the updated additions automatically. The HD additions ZIP is a library component managed by BBE.

# Base Builder Extended 18.2.48

- **Import from Clipboard** is back beside **Copy Objects to Clipboard** in the top-bar I/O menu and the sidebar Import/Export panel.
- Browse the **Online Prefab Catalogue** from the Prefabs menu. Search community builds, download and place them, or share your own prefab. No Discord login is required.

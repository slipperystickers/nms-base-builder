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

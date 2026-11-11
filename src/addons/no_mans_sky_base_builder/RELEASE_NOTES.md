# 18.2.48

- **Import from Clipboard** is back beside **Copy Objects to Clipboard** in the top-bar I/O menu and the sidebar Import/Export panel.
- Browse the **Online Prefab Catalogue** from the Prefabs menu. Search community builds, download and place them, or share your own prefab. No Discord login is required.

# 18.2.47

**Copy Objects to Clipboard** is back in the top-bar I/O menu and the sidebar Import/Export panel. It copies the current build's objects as a JSON array ready to paste into a No Man's Sky save editor.

Install the extension ZIP below or use BBE's updater. Existing Detailed Proxy packs carry over.

# 18.2.46

- Place electrical, teleport and pink ByteBeat cables with a live preview. Branch an electrical or ByteBeat cable at a clicked point and hide each cable type using its collection.
- Wire several devices in a chain or fan from a starting point you choose. Logic sockets show IN, OUT and TRIGGER where applicable. Add a proximity-control circuit to a power door from the viewport.
- Snap Corvette parts at native sockets and preview which hab and Vantage walls open around attachments. Pick each cockpit variant directly from the Asset Browser.
- Draw curves on a surface, trace edges or faces, and repeat a selection of parts along a curve. Curve tools restore your previous pivot and transform orientation.
- Choose the bases and ships to keep when duplicating a save. Optimize and export straight to the selected Corvette slot with an automatic backup.
- Preview the native colours and finishes of the Venom Spitter and Vile Proboscis with Detailed Proxies. Existing HD installations fetch the updated additions pack when Blender has online access.

Install **no_mans_sky_base_builder-18.2.46.zip** in Blender. Detailed Proxies are optional. First-time users can enable them from the BBE menu.

# 18.2.45

- Fix Windows updater downloads failing when a reader temporarily locks progress.json. Progress updates are optional, throttled and retried; final status writes retry transient locks, and download activity remains visible even if progress reporting is unavailable. Download size and SHA-256 verification remain mandatory.
- Check Blender's session temporary directory before the BBE updater invokes installation. If it is missing or unwritable, stop with restart instructions before Blender disables BBE.
- No HD pack changes. Reuse the verified 18.2.44 additions pack and existing core, effects and character packs.

# 18.2.44

- Open connected hab end walls at their native snap points and restore them when detached. Include native doorway frames, corrected magnetic wall assemblies and the Pocket Reality Generator correction in the add-on ZIP.
- Make Keep Editing, Create Curves and Discard Lines act immediately in the temporary-curve prompt; remove the redundant Continue/Cancel row.
- Return the chat preview to the main room after reading or replying to DMs, prewarm chat on startup, and close the changed-save refresh popup without duplicating the I/O menu.

- Keep an Auto-Snap ON/OFF control fixed over both asset browser grids. Remember the choice across restarts; OFF copies the selected object's exact transform. Show magnetic modules in hab wall openings, using the native 1x1 wall assemblies and the 1x2 mounting orientation; restore the closed wall and loose proxy on disconnect.

- Add a compact corner help button and keep/create/discard prompt for temporary surface curves. Auto-snap compatible browser parts into green target placement and offer a nearby Snap button for selected pairs. Show green electrical and cyan teleport placement cursors. Add reversible interior roof cutaways with adjustable opening height, and default-off magnetic beam toggles for B_MAG_1X1 / B_MAG_1X2. Proxy display controls preserve original geometry and game export records.

- Add colored Curve Tools icons and a HOW TO popup; rename surface tracing to Curve from Edges / Faces, open in Edges mode, put Edges/Faces first, and show a hand cursor over the rotation ring and diamond.

- Preview Curve from Surface face paths and edge chains on hover, distinguish hovered and selected paths, and restore the pointer over controls. Reuse prepared topology and face previews across successive traces until geometry changes. Smooth boundary-derived centerlines and project their samples back onto the surface.
- Extend point-and-click snapping to base and freighter parts using the installed game's placement graphs. Preserve socket child offsets and rotations; support named and unsuffixed connection locators, shared scene caching, and one marker per compatible position. Fixed bubble ducts expose only their visible, unoccupied openings through the same click UI.
- Automatically check an existing Detailed Proxy pack against the current HD manifests after enabling/updating/reinstalling BBE and loading a project. Download missing or updated components with Blender Online Access enabled, even when the current scene uses Simple Proxies. Refresh Detailed scenes after verification without changing Simple scenes; preserve the old pack on failure and expose Retry Download.
- Extend clickable viewport snapping to Corvette wings, structures, engines, landing gear, interior fittings, stairs, magnetic attachments and other parts with compatible native sockets. Use the installed game's placement scenes, including individual socket rotations and offsets.
- Show only compatible connections on the selected target. Click again to cycle the moving part's connection; existing Previous/Next controls and Undo remain available.
- Keep special connection types separate and reject incompatible pairs instead of falling back to an unrelated generic connection. The Corvette teleporter remains surface placed because its native locator has no matching Corvette socket.
- Cache local connection calculations so viewport markers remain inexpensive to redraw. Preserve base/HD model geometry, materials, icons, save data and existing scene placement until the user snaps a part.

# 18.2.43

- Restore native geometry, default orientation and textured detailed models for the new Corvette parts. Vantage includes all three rear connection openings and changes the displayed walls when connections are used.
- Add clickable Corvette snap targets in the viewport for the selected target part, alongside the existing connection controls.
- Correct sign/table mirroring and mirrored bubble-tube previews; improve junction checks and continued editing of mirrored tube systems.
- Keep U_PARAGON visible and movable so builders can adjust its exported position for the ship's third-person view.
- Align character pilot references with the shared cockpit placement calculation. Add selectable standing and seated character scale references, excluded from ship exports, with colored thumbnails and an optional textured HD character pack.
- Expand Advanced account unlock tools beyond buildable items, including expedition rewards, common names and item IDs, categories, and currency editing.
- Add the Advanced Raw Save JSON editor with a default Quick View, named and categorized bases, separate Main/Expedition trees and an adjacent JSON editor. Include game-running protection, changed-file detection, backup-backed saves, unsaved-change prompts and a green enabled Save button.
- Support pasting clipboard images and text into chat. Restore missing settlement icons and freighter-window previews.
- Reduce placement overhead and standardize new-part texture sizes against the existing HD library. Preserve full detailed meshes; prepare duplicate-face cleanup before distribution. The additions download is 251.5 MB, previously 408.2 MB.
- Keep base models and all asset-browser icons in the base download. Detailed models/textures and HD characters remain separate downloads managed by Detailed Proxies. Preserve the verified compatible additions pack while its replacement update is pending.

# 18.2.42

- Restore the pilot reference's earlier forward position for very small cockpits such as U.S.O. Keep the height adjustment from 18.2.41; the backward shift did not match the in-game view.
- Refresh pilot previews saved by older versions when a Blender project opens. The reference remains visual only and is excluded from game exports.

# 18.2.41

- Align the full-size pilot preview with the Corvette cockpit's chair locator and player offset, including very small cockpits such as U.S.O. The character still follows the first cockpit and remains excluded from game exports.
- Update older saved pilot previews when their Blender project is reopened. Placement is ready for comparison against in-game seating.

# 18.2.40

- Preview Light Fissure beams in their red/orange in-game colour rather than the green extracted texture mask. Correct already-saved HD previews on load without changing part placement or export data.
- Replace the Holo-Arena Game Table's misleading sail icon with a transparent render of its native table model.

# 18.2.39

- Reduce the base download by about 352 MB (34%) by moving detailed addition models and textures into the optional High Detail Proxy pack. Geometry, textures and icon resolution are unchanged. The pack is stored outside the extension so updates keep it installed.
- Download and install verified updates automatically when the update checkbox is enabled. Manual Download and install also completes installation. Wait for editing, dialogs and renders to finish, briefly pause the Asset Browser, and reload the updated extension.
- Show update failures in Updates & Support and verify archive identity, version, minimum Blender version and SHA-256 before installation.

# 18.2.38

- Copy a saved Corvette's complete Owner record from Advanced Build Metadata. Review the copied fields before applying; the donor ship is never changed, and writing ownership to the destination save remains a separate opt-in.
- Explain empty USN fields without inventing a username from an account ID. Reject ownership copies if the source save changes during review.
- Retain ownership and placement from third-party .nmsship packages that wrap their parts in build metadata. Keep selected-save/template metadata when a parts-only project has no corresponding metadata of its own.
- Preserve the full ship record, technology/cargo contents and slot positions, supercharged slots, appearance, legacy-colour flag, build placement and unknown package entries through .nmsship export and project reload. Save replacement continues to keep the destination ship's world placement.

# 18.2.37

- Fix unwanted horizontal scrolling in mini chat. Fit message bubbles to the window, wrap long names, filenames and URLs, and shorten attachment/reply button captions without changing the text being copied or sent.
- Keep expanded images within the message bubble when resizing. Preserve vertical history scrolling, automatic scrolling to new messages and the full-width composer.

# 18.2.36

- Correct Venom Spitter, Limos-Class Generator, Vile Proboscis Generator and 24 plating proxies using their current game models. Refresh outdated previews while preserving part IDs, placement and colours.
- Make Thunderbird Landing Thrusters easier to find under Access and Docking. Correct native names and categories, consolidate redundant Argonaut variants, and keep distinct plating shapes separate. Identify hidden and unfinished native parts in their hover descriptions.
- Replace 82 missing, marked or misleading icons with clean, transparent 512-pixel previews of the verified game models. Keep original game artwork everywhere else and retain yellow new-part borders.
- Speed up repeated detailed-part placement and share identical materials without reducing geometry, textures, UVs or smooth normals. Preserve individually coloured parts and edited shaders.
- Open warm chat windows immediately on request instead of waiting for the polling timer, with a fallback for missed file notifications.
- Add Advanced Build Metadata beside the build-name field for Owner and last-editor details. Preserve extra metadata in full build files and clipboard exports. Changing destination-save ownership is a separate explicit option shown on export confirmation; opening a project or importing a build never enables it.
- Validate native exports, Undo recovery and NMScribe shape generation in Blender 5.1 and 5.2. NMScribe requires no changes.

# 18.2.35

- Restore 2,347 original game-provided asset icons, including all 214 Forsaken additions. Preserve their native colors, camera angles and full 256-pixel source resolution; remove the pink/orange rendered replacements.
- Use the same catalog icons in the main browser, sidebar and legacy browser. Preserve yellow first-click borders.
- Record native icon provenance and pixel checks. Keep game-supplied placeholder artwork intact; Deathwrought's pyramid model and unfinished icon are present in the original NMS 7.10 files.

# 18.2.34

- Highlight new Forsaken parts with a yellow border until first clicked. Remember viewed parts per user across restarts, in the main browser and sidebar.
- Restore native smooth normals on all 214 Forsaken detailed proxies. Refresh older saved display meshes without changing part IDs, colors or placement.
- Replace Forsaken thumbnails with consistently framed, transparent 512-pixel previews of the textured native models. Correct the older Cell Joint, Cargo Box and two placeholder hull thumbnails.
- Stop DM flashing when the incoming message is read; keep the unanswered-message queue and alert again for later DMs.
- Allow .nmsprefab sharing and recognize .nmsship as a packaged build. Support build/text files up to BBE's 64 MB interchange limit. Requires chat server 18.2.34; existing expiry, account quota and shared storage limits remain in effect.
- Verified against installed NMS 7.10 assets. Deathwrought Amplifier currently shares Aeron Pyramid geometry in the game files; its preview and tooltip reflect that native assignment without substituting its export ID.

# 18.2.32

- Add 214 supported Forsaken part IDs and variants, including the new Corvette cockpits, hull sections, wings, reactors, decorations and gravity floor/ramp/wall. Include native icons, lightweight proxies, detailed meshes and portable textures.
- Retain native part IDs and placement transforms for exports. Detailed additions work with the existing HD library; lightweight models remain available without that download.
- Verify native exports and NMScribe shape generation in Blender 5.1 and 5.2. The two native records B_LND_D and B_TRU_I are excluded because their models are absent from the installed 7.10 game archives.

# 18.2.31

- Distinguish Pipe â€” Automatic from Pipe â€” Fixed in the Asset Browser, search, favourites, recents and part names. Explain the in-game shape changes in hover help, including that automatic pipes currently have a straight Blender preview. Existing part identities and exports are unchanged.

# 18.2.30

- Close Messenger automatically when its connected Blender sessions exit or crash, including when chat is hidden in the toolbar. Keep it open for another connected Blender session; cancel active transfers and bound shutdown if a network worker is stuck.
- Includes the 18.2.29 Scene Preview Undo crash fix.

# 18.2.29

- Fix a reproducible Undo crash after moving selected parts with Scene Preview enabled. Protect generated preview materials and lights during Undo/Redo, and keep decal updates away from scene data while history is being restored.
- Preserve selection, transform gizmos and Redo history without adding extra undo steps or changing saved preferences.

# 18.2.28

- Fix colour and material changes on intact prefabs and their split parts. New prefabs retain the selected model quality, textures and saved colours; recolouring a prefab updates its native parts without changing their placement.
- Repair unchanged legacy prefab/proxy appearances when reopening detailed scenes, preserving edited meshes. Apply proxy colour changes immediately through Scene Preview instead of leaving its old display material over the new colour.
- Clear Build Scene and replacement file imports now remove leftover empties and nested collections from the current scene. Keep the Asset Browser, workspace and collections used by other scenes or library instances.

# 18.2.27

- Fix missing Move, Rotate and Scale gizmos after reopening a project with Scene Preview enabled. Restore the scene preview without forcing a redraw inside Blender's file-load callback, so Blender can initialize its tools normally. Interactive preview refreshes retain their progress display.

# 18.2.26

- Restore Blender's Move gizmo when selected power, ByteBeat, supply or portal cables have both endpoint controls selected. Cable locations remain driven by those controls; incomplete selections retain their cable locks. Base anchors and rotation/scale locks are unchanged.
- Refresh BBE's cached modules when Blender reloads an updated, disabled add-on. Prevent old modules from causing missing-operator import errors during an in-session upgrade, including `BBE_OT_backup_settings`.

# 18.2.25

- New incoming DMs take over the chat bar and remain highlighted until answered, even after reading them. A successful reply advances to the oldest remaining unanswered DM; once none are waiting, the bar returns to Main Room.
- Add a slow theme-native attention pulse, updating only Blender's toolbar region. Main Room updates remain unhighlighted; no extra network polling is used for the pulse.
- Clicking the bar opens the displayed conversation. Incoming DMs do not switch the conversation being composed, and an unfinished draft prevents a toolbar click from silently changing its recipient.
- Preserve pending replies across restarts. Failed sends and newer DMs arriving during a send retain their alerts. Your outgoing messages are never displayed as the preview.

# 18.2.24

- The chat toolbar follows the selected conversation: latest incoming response in the active DM, otherwise latest incoming Main Room message. Your own messages never replace the preview.
- Switching or closing a DM updates the preview immediately. Unread DMs highlight the toolbar without replacing the selected conversation's message; Main Room messages remain unhighlighted.
- Quoted replies preview the new response instead of repeating the older quoted message. Current poll contents are available to notifications immediately.

# 18.2.23

- Update Steam companion metadata during base and pinned Corvette exports, including Optimize & Export. Recorded compressed/uncompressed sizes now match the exported data.
- Synchronize save and metadata file timestamps with one metadata timestamp for each export transaction. Preserve save identity and each save point's unrelated progress.
- Use verified staging, concurrent-change checks and backups across these export routes. Failed writes restore both data and metadata, including original timestamps.
- Validated on disposable saves. The reported in-game cross-save conflict still requires confirmation; this does not suppress genuine cloud conflicts or claim to fix game-loading crashes.

# 18.2.22

- Enabled chat updates online counts and the latest received message without opening Messenger, including after loading another Blender file. Disabled chat remains offline.
- Fix sparse inbox notifications replacing message text with a generic attachment notice. Image links stay readable in Mini mode, failed previews show an error, and new messages scroll into view.
- Add quoted replies and distinct unread/reply-or-DM notifications. Replies remain readable in older chat versions.
- Compact conversations and single-line online users; the aligned drawer grows with its contents and retains scroll position during refreshes.
- Close individual DMs with the inline Ã—. History is retained; clicking the person or receiving a new DM reopens the conversation.
- Startup profiling found about 1.6 seconds of total BBE overhead in isolated background launches, with chat registration around 5 ms. This release does not claim a general Blender startup speed fix.

# 18.2.21

- Preserve the selected save build by identity when refreshing; clear missing or ambiguous destinations instead of silently selecting a different ship. Apply this to remembered selections in other save tabs too.
- Export to Save and Optimize & Export no longer default to a new ship when none is selected. Ask users to explicitly create a new ship in an empty slot or choose an existing ship, then confirm that destination before writing.
- Show a red overwrite warning with the existing ship name, save context and slot when the destination differs from the scene source. Remember source information on save imports and successful exports; older scenes with unknown provenance show a red verify-target notice. Changing destination clears prior confirmation.
- These safeguards do not diagnose or repair reported in-game loading crashes.

# 18.2.20

- Replace the chat toolbar icon with a person and a corner badge showing other builders online. Counts match the online list, cap visually at 99+ with an exact-count tooltip, and disappear when disabled, disconnected or stale. Keep the single toolbar chat control and unread message preview.

# 18.2.19

- Align the users and conversations sidebar with the top of mini chat. Keep both aligned when moving or resizing the chat, and shorten the sidebar near the screen bottom.

# 18.2.18

- Consolidate chat into one reorderable toolbar control: Chat opens the Enable chat dropdown while disabled; when enabled it becomes the latest received message preview. Remove the duplicate chat launcher and online-users toolbar button. Toolbar settings always remain last.
- Clicking the message preview opens the rich mini chat beneath the clicked toolbar. The expanded chat includes Enable chat, its existing users/DM drawer, attachments and composer. Returning focus to Blender dismisses the attached chat without discarding the draft.
- Fix Windows monitor matching when Qt reports friendly display names, so chat attaches to the Blender client window instead of falling back to the monitor bounds. Native focus, placement and dismissal checked on the primary and secondary monitors.
- The rich chat remains a separate Qt window presented as an attached dropdown; it is not embedded inside a native Blender popover. The disabled Enable chat menu is native Blender UI.

# 18.2.17

- Reuse ordinary decals' existing display mesh and material slots when refreshing projection. This removes the Material Preview rebuild pause after a drag or Projection Preview toggle in testXE2.blend. Shared displays and history restores retain guarded handling.
- Preserve ordinary decal coverage, surface placement, signed rotation, export transforms and the calibrated NMScribe / White Border projection path. Repeated toggle/rotate/delete Undo and Redo passed in Blender 5.1 and 5.2.
- Put the enabled chat's shortened latest-message preview, unread count and users/DM button inside Blender's native BBE toolbar. The toolbar follows Blender's height and theme; clicking opens the conversation below it. The old floating collapsed strip is hidden in toolbar mode. Explicit corner and floating placement remain available.

# 18.2.16

- Keep decal projection rebuilding out of native move/rotate/scale drags. Reconcile after confirm or cancel, and reuse flat artwork during movement.
- Batch ordinary decal triangles that are fully inside the existing projection volume, clip only boundary triangles, and cache unchanged receiver geometry and transform stamps. Preserve the same coverage and UVs, with unchanged NMScribe / White Border stair calibration.
- Replace the fixed +/-5 degree buttons with Rotate and a signed Degrees input. Surface placement, offsets, preview toggle and Undo/Redo remain available.
- Tested with testXE2.blend: all 15 decals retain equivalent geometry/UVs; the native drag test completes without projection rebuilds or new display meshes during the drag.

# 18.2.15

- Ordinary decal previews cover intersecting raised and recessed surfaces without jumping to one centre-selected depth. Existing projection bounds and saved part transforms are retained.
- Add a per-decal Projection Preview toggle: projected artwork remains the default; Flat mode changes only Blender's preview, not the exported placement.
- Add stationary, draggable decal controls with optional click-on-surface placement, free movement, artwork rotation and surface offset. Controls appear for a single selected decal.
- Preserve the calibrated NMScribe / White Border stair projection, depth limits, wrapping and UV mapping. Regression geometry and UVs match 18.2.14 exactly in Blender 5.1 and 5.2.

# 18.2.14

- Export editable Charon Forge point-based shapes using their saved part placements, including objects whose normal group cache is empty. Preserve source part IDs, colors, world transforms and parent poses without splitting or modifying the shape.
- Works from the saved layout with Forge disabled. Unsupported procedural placement data produces a named error instead of silently omitting the shape.
- CreepyCrawly regression: all 573 parts export, including 290 previously omitted abdomen panels; existing 283 records remain unchanged. Includes the pending 18.2.13 Mini chat and gradient editor fixes.

# 18.2.13

- Mini chat uses a genuinely rounded native window shape with transparent corners. The sidebar chevron is centered geometrically, and the attachment / message / emoji row spans the bottom.
- Mini defaults to a collapsed strip aligned with Blender's tool-header row. The strip follows the toolbar height, previews the latest received message with ellipsis, and expands for chat. Placement and full-window preferences remain available and are remembered after this layout migration.
- Removed duplicate Dock top right / Dock bottom right actions; placement options remain under Attach Mini to Blender.
- Theme customization is labeled Customize Colors & Gradients, with Solid, Vertical gradient and Vignette, two viewport colors, and grid color. Installation repairs the previously stale theme-editor module in both profiles.

# 18.2.12

- Bubble tube controls choose a clear viewport edge and stay in place when selecting or adding pieces. Drag their header to reposition them. Rotation and placement controls keep their top anchor as the panel changes height.
- Mini chat has an attachment menu to the left of the message field and an emoji picker to the right. A larger middle-left handle opens the rounded users / rooms / DM drawer; redundant Messenger branding is removed.
- Top-right and bottom-right docking follows Blender's viewport boundaries. Expanded image previews remain bounded, and message rows keep their space in small windows.
- A changed-save warning opens a dismissible notice with a large highlighted REFRESH SAVE button and dimmed I/O controls. Refresh Save also has a visible label in the normal menu. Existing freshness checks remain in force.
- The Color palette follows the active part's saved color and material, displays its current color, and highlights the matching swatch without recoloring the selection.
- Client UI update; compatible with the existing 18.2.11 chat service and its file limits.

# 18.2.11

- Share BLEND, ZIP and PDF files up to 2 GiB using 4 MiB chunks, with checksum verification, progress and Cancel file transfer in chat options. Small structured/text files and media retain their existing limits.
- Files expire two hours after upload completes. One active non-media file or pending upload per identity, shared across aliases. Abandoned partial uploads expire after 30 minutes idle or two hours total and are cleared on server restart.
- The global 5 GiB cap includes full reservations for pending uploads. Downloading uses bounded ranges and writes to a temporary file; cancellation or failed verification removes that partial file.
- Requires the matching chat server update. Existing media uploads and older clients remain supported.

# 18.2.10

- Mini Messenger can attach to Blender corners or its top/bottom edge and collapse to a 32-pixel strip. Hover or click to expand; typing, menus and dialogs keep it open.
- Images become expandable links in Mini mode. Preview size follows the window width. The arrow opens a separate online-users and DM drawer.
- New-message counts appear on the strip and conversation list. Always on top defaults on, is checked against the native Windows window state, and remembers your choice.
- Share BLEND, ZIP, PDF, JSON, NMSBASE, NMSSHIP, TXT and LOG files up to 20 MB. One active non-media file per identity, including all its claimed names; remove it from chat options or wait for two-hour expiry.
- File sharing and inbox notifications require the updated chat service. Server storage is capped at 5 GiB shared by all users, with automatic expiry and oldest-first eviction. Media expires after seven days; expired attachments remain labeled in history.

# 18.2.9

- Fixed Mirror, Flip, and Turn being ignored for BBE groups and ordinary Blender objects.
- Preserved parenting when a mirror swaps and renames a native counterpart.
- Tested group export/reimport and reflected Rockhopper fin geometry in Blender 5.1.2 and 5.2.2.

# 18.2.8

- Fixed bubble previews interrupting gizmo drags in loaded and reopened ships.
- Added automatic tube inspection on load and **Builder > Check & Repair Bubble Tubes** for old metadata and previews. Tube placements and valid unfinished bends are preserved; unresolved connections are reported.
- Rejected unsupported connected-branch angles, including 45 degrees and cumulative small-turn bypasses.
- Added six local starting-direction buttons for an unconnected straight tube; the next straight or elbow follows that choice.

# 18.2.7

- Theme colors now cover the timeline header, time ruler, status bar, and Asset Browser surfaces.
- Pop-out and sidebar asset cards, labels, hover highlights, footer, scrollbar, and loading screen follow the current Blender palette.
- Existing custom themes work unchanged; reapply the preset after updating.

# 18.2.6

- Moved chat enablement, name claims, identity switching, and recovery-key controls into Messenger account settings. Removed the BBE chat-settings entry. Opening Chat without joining stays offline.

- Removed the old Join Selected Bubble Ducts entry from the BBE dropdown and sidebar. Tube connections remain in the contextual tube interface.
- Added BBE > Themes > Customize Theme with interface, button/header, accent, text, and viewport color controls.
- Save named custom theme presets and reapply them from My themes. Chat follows applied colors.

# Base Builder Extended 18.2.5

- Compact Mini mode, hideable users/conversations sidebar, and remembered layout choices.
- Native Windows Always on top, narrow side placement, and message layout cleanup.

---

# Base Builder Extended 18.2.4

- One-click Chat and Assets toolbar buttons; chat account settings move into BBE.
- Messenger follows Blender's interface colors and adds persistent pin and left/right placement controls. Its Online users list opens a direct message when a name is clicked.
- BBE offers ten optional Blender themes. Save Blender Preferences to retain the chosen theme across restarts.

---

# Base Builder Extended 18.2.3

- Chat now opens in a separate messenger window with Enter-to-send, a buddy list, direct messages and inline image previews. Snapshot queues a Blender screenshot for review before sending. Images can be reduced before upload; short videos remain downloadable files.
- Chat stays optional. Use the small arrow beside Chat to enable it and manage names.

---

# Base Builder Extended 18.2

## Bubble tube building
- Build straight tubes, elbows, T and + junctions, three-way and four-way corners, five-way and six-way junctions with controls beside the selected tube.
- Add one new pathway at a time. Finish its straight or attached elbow before adding another opening. Redirect or remove an unused opening from the same panel.
- Offer T and draft + when an elbow reaches the side of a straight. Highlight the tube that will change and preserve existing connected arms.
- Show distinct draft previews until their required openings connect. Hide tube controls during multiple selection so they do not interfere with moving a structure.
- Keep rotation, direction previews and part icons beside the workpiece. Improve placement undo/redo and refresh restored curve state after history operations settle.
- Load the Asset Browser with its loading surface and show elbow help in context.

## Export and warning fixes
- Remove false proximity warnings caused solely by two closed tube sides. The 30-tube layout confirmed working in game now has no such warnings, with exactly the same exported placement frames.
- Bubble connection warnings are advisory. Clipboard, file and save exports remain available for in-game testing, including unfinished layouts.
- Retain checks for actual visible openings and incomplete branches. Legacy Blender-only curved proxies still have an explicit conversion workflow.

## Installation
Windows x64; Blender 5.1 or newer. Download `no_mans_sky_base_builder-18.2.0.zip`, install it through Blender's **Install from Disk**, then restart Blender. The optional HD pack remains separate. Existing settings, projects and save backups are preserved.

**Base Builder by DjMonkey. Extended by Furiousfurby.**

Validation: Blender 5.1.2 and 5.2.2 LTS. Includes a regression fixture for the user-confirmed in-game layout. Individual regression checks are Blender/serialization tests, not a claim that every possible junction layout was tested in game.

---

## 18.1.84

### Corvette picker
- Close the Corvette selection menu after choosing a ship. Keep its button labeled Select Corvette and show the selected ship below it.
- Remove freighters from selectable ship lists and selection lookup in both Main and Expedition saves. Preserve Corvette health warnings and repair actions.

## 18.1.83

### WASD navigation and export responsiveness
- Fixed WASD being blocked by the sidebar Asset Browser's background listener, including restored workspaces. Active transforms and controller sessions still retain input ownership.
- Kept the progress overlay visible from export confirmation through scene checks, ship validation, verified writes and list refresh.
- Reduced repeated save copying during comparison checks and stopped rebuilding the save-key translation table for every nested value. Preservation checks, backups and stale-save protection remain in place.

## 18.1.82

## Cockpit selector stability and feature help

- Fix changing/garbled cockpit selector labels by retaining their strings for the dialog and undo/redo lifetime. The reviewed cockpit list stays stable; changed or removed entries require reopening instead of redirecting a selection.
- Add Swap Cockpit Order to both BBE menus, retaining the Optimizer Settings shortcut. The swap changes scene export order immediately, never physical placement. Ordinary and optimized exports use that order; saving the .blend keeps it with the project, and Undo/Redo works.
- Add clearer hover descriptions, contextual How this works popups and BBE Feature Help. Topics explain cockpit order, optimizer settings, Corvette export, keep-build repair, file replacement, recovery and WASD navigation, including when changes take effect and what can undo them. Help is local and does not modify data.

## Ship warnings, keep-build repair and new-slot export

- Check Corvette health as soon as a save is loaded. The shared I/O selector highlights affected builds in red, explains the problem and identifies ship slots consistently as 1â€“12. Missing-build Corvettes are also listed; the freighter stays separate.
- Add Repair â€” Keep My Build directly below the selected build in I/O, in both the top bar and sidebar, and Repair Build in Ship Management. Repair retains the saved objects, transforms, colors and readable inventories, technology, hyperslots, class, stats and appearance. Invalid data resets are listed and require separate confirmation. A missing build can be supplied through scene export or Replace From File.
- Add Overwrite Selected Ship / New Empty Ship Slot to ordinary and optimized Corvette Export to Save. New slots use the minimal Corvette ship record with exactly the scene objects; no template parts are added. Slots reserved by orphan builds are never treated as empty. Both Main and Expedition contexts are supported.
- Never add a missing cockpit during repair or export. Show an unflyable-ship warning and allow the operation. Repairs without a cockpit keep their warning in the selector until the user adds one.
- Stale selections, changed scenes or optimizer settings, changed save files and competing Ship Management drafts are rejected; verified backups precede writes. Preserve unrelated ships and freighter data.
- Keep ordinary and optimized objects-only exports from overwriting or renaming a non-Corvette ship through an uncertain build link. Complete reviewed replacement remains available to correct the slot.
- Preserve ship inventory, class and appearance when importing a Corvette from a game save, so Export Corvette works without first importing a .nmsship template. The source metadata survives saving and reopening the Blender project. Older projects can explicitly use the original Corvette selected in I/O while retaining their current edited parts.
- Use the same save-point selection in the list, importer and Ship Management, including equal timestamps.
- Show mismatched ship slots in red, with a brief reason and full details in Link Status. Keep the manager open and safe inventory edits available.
- Keep Replace From File as a separate explicitly reviewed option. A complete .nmsship replaces ownership, inventories, appearance and the linked build together; objects-only replacement requires one correctly linked Corvette.
- Require confirmation for duplicate build replacement. Preserve unrelated ships, builds, contexts and freighter data. Save Changes revalidates the draft, checks external changes, creates verified backups and rolls back failed writes.
- Verified with English/obfuscated synthetic saves, the supplied report in memory, backup/rollback tests and Blender 5.1.2 / 5.2.2. No in-game repair validation is claimed.

## Optional WASD navigation

- Matching WASD Navigation toggles in the BBE dropdown and sidebar. Off by default; settings follow Blender add-on preferences.
- Hold right mouse for look and WASD/arrow movement; Q/E moves vertically, Shift speeds up, Ctrl slows down and wheel adjusts speed. Release right mouse or Esc stops. Quick right-click retains the context menu.
- Works in Object and Mesh Edit modes with left-click selection. Changes only the viewport, leaving camera view before movement; does not transform objects or the camera. Existing modal tools/controller sessions retain input.
- Timers run only during navigation and stop on release, disable, file load or unregister. Native keymap and lifecycle checks passed in Blender 5.1.2 / 5.2.2.

## Saved Asset Browser compatibility

- Restore the thumbnail grid for older saved Asset Browser layouts that used an unlinked cube helper. Keep normal model objects out of automatic helper cleanup.

## Opt-in Blender diagnostic tickets

- Send captured BBE errors to the owner inbox as Blender Diagnostics after explicit approval, without Discord, an account, email, a private reporter link, replies or attachments.
- Respect Blender Online Access and offline mode. Automatic prompts wait for online access and an idle 3D View. Preview the error and review the full local report before sending; reporting never enables networking.
- Include BBE/Blender versions, platform and detailed proxy-pack availability. Redact common personal paths, credential fields and email addresses. No project, game save, screenshot or attachment is uploaded.
- Use a separate bounded Python helper so sending does not block Blender. Failed sends remain local for manual retry; per-report identifiers prevent duplicates after a lost response. Status and Review / Send Last Error appear in Updates & Support.
- Capture handled errors in Ship Management, import/export, recovery and other BBE operators, as well as uncaught execute/invoke exceptions. This does not collect native Blender crash dumps.

Requires website support 2.1.0. Keep this installer staged until that endpoint is deployed. Local client/server integration, consent/offline tests and Blender 5.1.2 / 5.2.2 checks passed. Normal website support conversations remain available separately.

## 18.1.81

## Ship Management with uncertain Corvette links

- Open Ship Management when an existing Corvette build link is missing, duplicated, invalid or points to an unrecognized ship. A fresh install no longer makes these existing save conditions look like a failure to open the manager.
- Keep inventory, cargo, technology, ship class, saved stats and existing hyperslot edits available. Before saving, compare the complete draft with the original snapshot and preserve all uncertain ownership, build and surrounding context records exactly.
- Lock Move Up/Down and Add Minimal Corvette only in affected Main or Expedition contexts. Healthy contexts remain editable independently. Duplicate Save / Clear Builds still requires valid links in every context.
- Add an Ownership notice / Link Status dialog explaining the affected context and slots locally. No save upload is required and no ownership link is guessed or automatically rewritten.
- Start on the selected Corvette and context when available, otherwise the active or first owned ship.

Verified with synthetic English-key and obfuscated saves and Blender 5.1.2 / 5.2.2 LTS operator tests. The notice and disabled controls were also inspected in Blender 5.2.2. This protects existing uncertain links; it does not repair them or claim in-game validation of the reported user's save. The existing verified-backup writer is unchanged.

## 18.1.79 - Group default color and Charon activation check

- Reset a selected group's color from its cached child part colors, including simple proxy materials, instead of reading the group's absent ObjectID.
- When Charon Forge is enabled or configured to load at startup, ask before BBE registers its overlapping controls. Continue disables Charon; Cancel leaves BBE inactive.
- Warn if Charon is enabled after BBE. Save and restart with one add-on enabled; BBE cannot intercept Charon's installer or safely undo already overlapping registrations in that session.
- Blender 5.2's `acquire(): cookie doesn't exist!` error originates in Blender's extension installer before BBE runs. Restart Blender and retry the install if it occurs.

## 18.1.78 - Independent recovery timer and visible status

- Prevent other add-ons' save-copy operations and normal saves from restarting BBE's recovery countdown or clearing its placement count. Only a project-path change starts a new schedule.
- Keep the load-time deadline when Blender delays the first safe idle tick.
- Show the countdown, placement progress, waiting reason, or backup error in Recovery. Retry failed backups after one minute rather than silently waiting another full interval.
- Wait for active transform/sculpt/paint operations before saving; retain three consecutive independent recovery generations.

## 18.1.77 - Import designs without a base type

- Accept shared JSON/TXT designs with missing, blank, or unsupported base-type metadata using the selected fallback for Blender's scene metadata.
- Preserve supported base types, all part records, and the original source file. Normalize metadata before changing the current scene.
- Verify the reported 676-part TXT design imports completely.

## 18.1.76 - Direct prefab catalogue

- Restore the prefab catalogue below the prefab actions in both the top bar and sidebar.
- Remove the Parts selector/list and nested Legacy Asset Browser panel; rename the sidebar section Prefabs.
- Cache the catalogue outside scene undo data, refresh on startup/file load and prefab save/delete, and provide a refresh button for externally added files.

## 18.1.75 - Focused Prefabs and compact recovery controls

- Remove the legacy Parts/Prefabs browser block from the top-bar Prefabs dropdown while keeping prefab actions and the separate Asset Browser.
- Narrow Scene Preview to 14 UI units and Project Recovery to 16.
- Put the recovery mode and Minutes/Qty value side by side in the top bar and sidebar. Retain the existing time, placement and rotation behavior.

## 18.1.74 - Compact dropdowns and colored action icons

- Reduce individual toolbar dropdown widths by 8-30 percent while retaining the Color palette width and natural header label sizes.
- Add 43 transparent action icons covering 74 existing symbol names throughout shared toolbar/sidebar controls, Save Manager, recovery, optimizer, and support menus. Keep native state indicators and unmapped icons available through a safe fallback.
- Reuse the toolbar symbols in toolbar customization.

## 18.1.73 - Compact credits, colored sidebar and Recovery menu

- Give Project Recovery its own top-bar menu beside BBE, sharing the sidebar recovery controls.
- Tighten the two native-text credit lines and their punctuation spacing while preserving the purple EXTENDED word size.
- Turn the hammer striking face downward without moving the handle. Reuse colored toolbar symbols in matching sidebar headers; add distinct recovery, save and shield/update symbols.
- Default Import/Export, Save Manager and Transformations to collapsed, so fresh workspaces start with only BBE expanded. Preserve Blender saved workspace panel states.

## 18.1.72 - Native credit text

- Render creator names, Base Builder and credit punctuation with Blender native text for sharp UI rendering. Keep only the purple EXTENDED credit word as artwork and align both colons with their names on the text baseline.

## 18.1.71 - Hammer, RGB icon and clear BBE branding

- Use a recognizable hammer for Builder and three additive RGB circles with a white center for Color.
- Replace the cramped branding row with crisp, stacked Base Builder / EXTENDED artwork, the existing logo and smaller creator credits. Keep the sidebar compact at different widths and UI zoom levels using a native preview, without adding project images or textures.
- Put BBE on the left of its panel header and the short version label on the right.

## 18.1.70 - Clearer toolbar icons and save selection

- Keep the familiar top-bar symbol shapes, draw their colors in the symbols themselves on transparent backgrounds, and strengthen their small-size strokes. Remove the colored circular badges.
- Label Account and Save Slot as separate steps in both Save Manager views. Until a slot is chosen, explain where ship imports will appear and show their button disabled instead of silently omitting it.

## 18.1.69 - Ship Management loading progress

- Show progress while Ship Management reads, verifies, backs up and writes game save files, including creation of a new save slot. Keep the existing verified write and rollback behavior.

## 18.1.68 - Visible import and export progress

- Show staged progress for Optimize & Export to Save, including part collection, save loading, verification, backup and replacement. Start the confirmed export after the dialog closes so its progress bar is visible.
- Show progress when reading builds, loading the save list, importing from a game save, and exporting to the clipboard or standalone project, base and Corvette files. The existing model import and proxy loading bars remain in place.
- Refresh the four corrected B_STR_T NW display meshes when an older BBE project opens, in Detailed or Simple proxy mode. Leave user edited meshes alone. These display meshes do not change the game's native model; the correction makes Blender's preview match it.

## 18.1.67 - Fuel pod rim proxies and BBE navigation

- Load the four authored NW fuel-pod cover rim meshes instead of rebuilding them from the NE rim. The rebuilt meshes disagreed with the individual assets. Switching Simple Proxies to Detailed Proxies refreshes these parts in existing projects.
- Move Project Recovery from I/O to the BBE top-bar menu and its own panel in the BBE sidebar category. Keep backup folder controls with recovery.
- Compact the sidebar brand block, show BBE and the version in its panel header, and retain DjMonkey and FuriousFurby credits and support links. Add a purple Extended badge.
- Add distinct colored symbol icons to the top toolbar menus for faster visual scanning.

## 18.1.66 - One configurable backup folder

- Store new project recovery copies and game-save backups under one shared backup folder, separated into Projects and Game Saves subfolders. The default is NoMansSkyBaseBuilder/Backups in the user home folder.
- Add Open Backup Folder and Change Folder controls to both I/O menus and add-on preferences. Folder changes apply to both backup types; earlier backups stay in their original locations. Recovery copies in the prior Blender configuration location remain available in the recovery menu.
- Keep the save-slot backup shortcut scoped to that slot's subfolder, and update its labels and help text.

## 18.1.65 - Three rotating recovery slots

- Use three fixed recovery slots for each project. The first, second, and third backup fill them in order; the fourth atomically replaces the first, then the fifth replaces the second.
- Convert the newest three timestamped recovery copies from 18.1.64 to rotating slots on the next backup. Ignore incomplete temporary copies in the recovery menu.

## 18.1.64 - Undo stability and project recovery

- Keep generated hab-window display meshes available to Blender undo; pause decal, window, and lighting refresh while undo/redo settles. Preserve the original undo preference settings during rapid history operations.
- Add independent `.blend` recovery copies with a default 10-minute interval, an optional 5-part trigger, and a limit of three copies per project. Recovery controls and recent copies appear in both I/O menus. Copies do not overwrite the open project or NMS game saves.
- Clarify Save Manager counts: the save-slot total covers owned builds in that slot, while the selected Corvette count covers one saved build. Show the current Blender scene count and source save point, with a read-only refresh button.

## 18.1.63 - First-run update consent

- Ask once whether to enable automatic update checks. Yes enables and saves Blender Online Access and the startup-update setting, then checks for updates.
- No or dismissal keeps automatic checks off and remembers the choice across restarts and upgrades. An existing disabled setting is respected.
- The prompt explains that Blender's global internet access also applies to other add-ons. Forced offline mode stays offline; background sessions do not prompt or start automatic checks.
- Updates & Support can enable checks later using the same Yes/No prompt. Installation of downloaded updates remains user-controlled.
- Includes the complete Colour & Materials sidebar restored in 18.1.62.

## 18.1.62 - Restore the sidebar Colour & Materials section

- Restore the complete Colour & Materials section in the Base Builder sidebar, including the material palette selector, colour swatches, and colour picker.
- Keep the top-toolbar Color menu available alongside the sidebar controls.
- Preserve all fixes and assets from 18.1.61.

## 18.1.61 - Large-room glass placement

- Correct misplaced corner panes on Square Rooms and Square Deepwater Chambers, and floating roof panes on Cylindrical Rooms and Deepwater Chambers. Solid and Material Preview now use the same correctly assembled glass geometry.
- Apply the correction to recognised Detailed Proxy meshes when placing parts, switching quality, or opening older shared projects. Preserve part transforms, export records, texture coordinates, and other geometry; leave custom glass meshes alone.

## 18.1.60 - Sidebar Asset Browser input and visibility

- Keep thumbnail and scrollbar input inside the browser content, allowing Blender's vertical sidebar tabs and resize border to receive clicks normally.
- Hide the thumbnail overlay when its native panel is collapsed, including collapsed panels restored from shared projects. Reset panel visibility when a file loads.
- Use the same bounds for drawing and input, and ignore clipped tiles that are not visible.

## 18.1.59 - Textures in shared Blender projects

- Resolve saved Detailed Proxy textures from another user's downloaded HD library against the local installed pack. This fixes pink decals and materials when opening shared `.blend` projects.
- Match only known BBE library paths and manifest textures; preserve packed artwork and unrelated user images. Loading textures does not save or overwrite the project file.

## 18.1.58 - Category navigation and fossil preservation

- Allow the active Asset Browser category to collapse. Category and group navigation clear the search instead of leaving category headers disabled.
- Keep each fossil's exact variant through Simple/Detailed proxy switches and group/ungroup operations, including group export and restoration.
- Restore damaged fossil proxies when opening older projects if their variant is still recorded. Preserve unidentified fossils and user-edited meshes.

## 18.1.57 - Sidebar build file import

- Make the sidebar's file import button open the same Corvette, base, prefab, and JSON/TXT importer as the I/O menu.

## 18.1.56 - Standalone Corvette and base files

- Add direct import for `.nmsship`, `.nmsbase`, `.nmsprefab`, and build JSON/TXT in the I/O menu, including parts-only files with a selectable base type.
- Export Corvette `.nmsship` packages while retaining their class, inventory, technology, appearance, and other package entries. New ships can use an existing `.nmsship` as a metadata template.
- Export planet, freighter, space, and station bases as `.nmsbase` without changing their BaseType. Clarify that the older File controls work with BBE project JSON and that Save Manager writes to a game save.

## 18.1.44 - Clickable sidebar thumbnails

- Place parts by clicking their full-size images in the NMS Asset Browser sidebar, with the same variant and right-click actions as the separate browser.
- Restore Presets beside Favorites and Recent in the sidebar and keep category, group, and search controls available above the grid.

## 18.1.43 - Detailed proxies and saved Asset Browser recovery

- Allow Detailed Proxies to use the installed model pack while the separate HD scenes/effects component is missing or downloading.
- Repair image paths embedded in newly appended HD models so textures resolve from the installed library instead of the original build machine.
- Point the HD scenes/effects updater to the verified archive on the public release.
- Restore the clickable thumbnail grid when a saved Asset Browser window opens with Blender, and give the sidebar a direct button to open that browser.

## 18.1.42 - Ship Management scene isolation

- Open Ship Management in an independent Blender main window so its empty preview scene cannot replace the ship-building scene or black out Scene Preview.
- Restore the source scene when the manager closes, including OS-window close, and recover older orphaned preview scenes on add-on enable or file load.

## 18.1.41 - Visible import progress from toolbar menus

- Start Save Manager imports after the toolbar click returns, allowing Blender to close the I/O popover before the import progress appears. Cancel if the selected scene or save changes in the meantime.
- Place the viewport progress panel near the bottom so the BBE and Lighting popovers cannot cover it during other long operations.

## 18.1.37 - Browser responsiveness and calibrated preview beams

- Restore class-marker beams to the established FF calibration: 31.1 local units, with placement scale applied once. Existing shortened preview meshes migrate without editing build records.
- Refresh category/search/favourite views immediately. Reuse browser revisions instead of scanning every part on each timer event.
- Bulk-copy thumbnail pixels and use compact RGBA8 GPU textures while retaining the bounded cache and existing image resolution.
- Replace Heavy Landing Gear's placeholder with a transparent render of its bundled model. Move U_PARAGON to Uncategorised / No Build Menu Group.
- Remove Base Files, Build Metadata and Clipboard sections from the I/O popover; retain Save Manager and the existing sidebar workflows.

## 18.1.27 - Save Manager gating and unified backups

- Remove the estimated technology auto-optimizer and DPS projection. Ship Management still displays saved base rolls and supports manual slot editing.
- Restore a right-click menu in the inventory grid for item edits and moving an existing hyperslot.
- Put Duplicate Save immediately below Backup Saves in the sidebar and I/O Save Manager; it no longer depends on an open Ship Management window.
- Reset stale account/ship selection when a save changes. Start each selected save on Planet so Corvette controls require choosing the Corvette tab; import/export and Corvette optimization require a selected build, while Ship Management requires the Corvette tab.
- Back up both save points and available metadata before every export or save edit. The Select Save gear configures backup location and retention per account/save slot. Only new, verified BBE backup generations roll over; previous-version backups are untouched.

## 18.1.26 - Ship Management window and inventory safeguards

- Open Ship Management in its own resizable window with square, paged grid cells and a confirmation before discarding edits. A closed window with an unsaved draft offers recovery.
- Batch grid drawing and use an empty preview scene to keep ship-menu interaction responsive even with complex Blender builds in the main window.
- Read the installed game's Chargeable and StackMultiplier fields: hide internal counts on nonchargeable technology, respect one-per-slot products, and distribute larger cargo quantities across available unlocked cells.
- Make hyperslot text and double outline purple. Place Ship Management beneath Optimize & Export in the Corvette Save Manager.
- Add a primary/secondary technology layout search that keeps modules, rolls and hyperslots intact. Show saved base rolls and relative layout scores; optionally record an observed in-game weapon DPS for a clearly marked projection. Exact game-calculated final stats remain an in-game measurement.

## 18.1.12 - Projected decals and warm pill lighting

- Standalone HD decals conform to receiving hull triangles and stop at gaps and edges; their placement boxes no longer display six copies of the artwork. Existing saved scenes refresh automatically.
- Preserve decal IDs, transforms and export records through projection, saves and proxy changes.
- Restore surrounding orange spill from embedded red/yellow pill lights; combine nearby colored stacks before applying the light budget. White accents, blue reactor/booster lights and self-lit markers remain.
- Existing HD model and scene downloads are unchanged.

## 18.1.10 - Marker alignment and balanced glow

- Shortened all class-marker projections from 40 to 31.1 model units, matching the meeting point measured from FF's three emitters.
- Enlarged the soft emitter halo around the complete marker and made hologram layers additive so stacked bodies do not cut dark silhouettes into the orb.
- Increased reactor and landing-booster spill, reduced generic warm spill, and preserved shadow-free light budgets.
- Evaluate transforms before creating lamps after load; changing part scale refreshes spill strength automatically.
- Updated optional HD scenes/effects component; the main HD model library remains unchanged.

## 18.1.9 - Optional HD scenes, object lighting and landing effects

- Scene pads, space backdrop, hologram display meshes and effect data now install with the persistent HD library; HD icons and all simple proxies remain in the core add-on.
- Existing HD users download only the 8 MB scenes/effects component. New installs download both components through the same Download & Enable confirmation. No model re-download on ordinary add-on updates.
- Delete HD Pack removes both managed components after confirmation. Missing optional assets leave the core functional and show a download button in Lighting & Scenes.

- Audited all 2,275 available HD assets; enabled local spill for emissive items throughout the library, including decorations and technology.
- Added native lamp colour and unlit-material profiles for 573 mapped parts. Lighting retains a bounded 32/64 local-light budget.
- Restored both native hover meshes on Mag-Field Landing Thrusters with animated emission and local light. Animation follows Blender timeline playback.
- Renamed Ship Lights to Object Lights. Display effects follow part transforms and never export as buildable parts.
- Added simple geometry fallbacks for four empty legacy FBX assets: Pipe, Freighter Face Wall, Industrial Room and Settlement Landing Pad.
- Audit coverage is not full game-renderer parity: particles, gameplay-triggered effects and unmapped native scenes remain separately tracked in QA.

## 18.1.8 - Marker projections and reactor lighting

- Longer one-sided A/B/S hologram beams start at the visible emitter; particles no longer protrude behind it.
- Soft additive emitter halos build up when markers overlap, matching the bright stacked-marker effect.
- Ray Tracing is an independent on/off control beside Smooth/Photo quality settings. Existing preview files retain their prior ray tracing state.
- Blue reactor and thruster emissives and local light spill, including Zenith, Medusa, Azimuth and Ceto reactors.
- Display-only changes preserve object IDs, placement, export data and existing HD downloads. Holograms remain lightweight Blender approximations.

# 18.1.7 - Ship glow, ray tracing and open space pad

- Restores coloured ship light spill and emissive glow using original BBE code,
  with the existing local NMS Preview viewer as the visual reference.
- Smooth mode keeps 16 samples and up to 32 shadow-free part lamps. Ray Traced
  mode enables Blender EEVEE ray tracing, 64 samples and up to 64 part lamps.
  Both modes retain all emissive surfaces and only one shadow-casting rig light.
- Uses the fast Bloom compositor rather than FFT Fog Glow.
- Ship Lights, Light Spill and Glow controls; lights follow their parent parts.
  Adding, removing or switching part proxies refreshes their display effects.
- Removes the outpost gravity capsule and flat shield effect cards from scenery.
  The actual platform is open to space, with the build surface at Z=0.
- A/B/S markers now include a soft 10m projection beam, matched to the native
  particle size range, plus electrical motes. These are Blender approximations.
- Updates embedded marker/pad caches when opening older saved previews.
- Display material overrides, compositor and render settings restore when the
  preview is disabled. Original mesh assets, IDs and exported transforms stay intact.
- Small core update; the existing HD proxy library needs no redownload.

# 18.1.6 - Independent BBE scene preview

- Replaces the Charon Forge lighting integration with an original BBE renderer setup.
- Station Corvette Pad, Space Outpost Pad and Deep Space scenes; native standalone
  pads meet Z=0. Space uses a single small static background image.
- Smooth preview: 16 samples, three area lights, one shadow light, no ray tracing,
  screen-space GI or volumetric effects. Photo mode increases viewport samples.
- Grid, axes and light-guide overlays hide automatically, while selection outlines
  and editing gizmos remain available. Previous viewport/world/render settings
  return when Scene Preview is disabled.
- Retires old BBE per-part lamps when opening older scenes; user lights are preserved.
- Adds all three settlement class-marker HD meshes, transparent hologram lettering,
  projection scan lines and a fixed budget of electrical motes/streaks. Scan lines
  animate with timeline playback; effects are a Blender approximation of NMS.
- Marker corrections are tiny core resources; existing HD packs need no redownload.
- Scene objects never enter exported builds. Part transforms and IDs are unchanged.

## 18.1.5 preview - compact removal button

- Place an icon-only trash button to the right of Detailed Proxies. Keep its hover tooltip and deletion confirmation.

## 18.1.4 preview - remove the optional HD pack

- Add a compact Delete HD Pack button below Detailed Proxies, with confirmation and Cancel selected by default.
- Switch all scenes in the current file to simple proxies before removal; keep the pack if any part cannot switch. Only delete the managed downloaded pack, never bundled models or icons.
- Disable removal during downloads and when no downloaded pack is installed. Detailed Proxies offers the normal download again after removal.

## 18.1.3 preview - first-install feedback

- Offer Enable Online Access & Download directly in the HD confirmation, explaining that this changes Blender's global preference. Cancelling leaves the preference unchanged; an explicit offline launch remains respected.
- Keep overall progress moving forward across download, checksum verification and installation. Show phase details and percentage in the viewport header and download panel; avoid a stale progress bar in Blender's cached menu popover.
- Highlight the active Simple or Detailed proxy mode in the Builder menu.
- Reuse the existing verified HD pack; models, textures and icons are unchanged.

## 18.1.2 preview - simpler Detailed Proxies

- Detailed Proxies automatically detects the installed model pack. If missing, one Download & Enable confirmation downloads, verifies, installs and enables it inside Blender.
- Remove folder/ZIP management buttons from the normal prompt and remove the idle library sidebar panel. Show progress and cancellation only during downloads; retain offline ZIP installation in operator search.
- Refresh manifest detection after an on-disk add-on update. Cancelling a download, switching to Simple Proxies or opening another file prevents a pending automatic quality switch.
- Vesper in-game check confirmed by the user; no additional orientation changes in this version.

## 18.1.1 preview - complete simple-model coverage

- Bundle geometry-only fallbacks for 191 parts that previously depended on the optional HD library, including Stag Alloy Annexe and station parts. All HD icons remain bundled.
- Use the same model resolver for browser placement, Save Manager, clipboard imports and proxy quality changes. Re-selecting a proxy quality refreshes older placeholders without changing placements.
- Use the native game placement transforms for 24 Vesper Aerofoil/Cowling variants; correct the approximate upside-down offsets. The reported NE reversal still requires reproduction from the affected build: the NE asset itself matches the native placement.
- Existing HD library installations are retained; this update does not require downloading HD assets again.
- Regression: the FF Corvette imports all 525 records through both import paths, with and without the optional library; export preserves IDs, UserData, timestamps and placement vectors.

# Base Builder Extended 18.1.0 â€” preview

- Optional HD library installs through Builder > Detailed Proxies, with progress,
  cancellation, checksum verification and an offline ZIP installer.
- Persistent asset storage is shared between Blender versions and survives BBE
  updates. Existing saved scenes can relink their old bundled texture paths.
- Main installer includes Game Lighting & Scenes: game-data planet/space skies,
  time of day, sun direction, scene presets and optional native part lamps.
- Lighting adapted from Charon Forge 0.1.2 with credit; BBE adds independent
  per-scene resources and restoration of previous viewport shading and worlds.
- Lossless HD library cleanup preserves geometry, UVs, normals, materials and
  textures. No mesh decimation or texture downsampling.
- Simple/Detailed preference also applies to subsequent asset placement.
- Existing mirror, pipe endpoint snapping and exported part IDs are preserved.

Save and restart all Blender windows after installing this preview.
The separate HD download becomes public with the corresponding release.

# Base Builder Extended 18.0.18

- Adding a pipe or bubble duct from the native asset browser now mates real
  endpoints with the selected pipe, using the sidebar Snap continuation history.
- Added the textured high-resolution Curved Bubble Duct under its existing
  BASE_BUBPIPE_L ID, preserving the low-proxy origin, orientation and sockets.
- The alternate Qt asset browser now uses the high-resolution asset loader too.
- Existing curved bubble ducts can be upgraded with Builder > High-res Proxies.
  No saved scene or game IDs are automatically changed.

Save and restart all Blender windows after installing.

# Base Builder Extended 18.0.17

- Removed the 14 internal-ID junction experiments and alternate straight/T/X
  bubble entries from the browser after the user's standalone-placement test.
- Kept the established PIPE, PIPESHAPE, CURVEPIPESHAPE, BASE_BUBPIPE and
  BASE_BUBPIPE_L entries. Curved Bubble Duct is back in Structural Adornments
  without an experimental label. Existing snapping and mirror fixes remain.
- Retained model assets, IDs and snap data for loading existing Blender scenes.
  The standalone-junction test files remain available for future investigation.
- This cleanup does not establish new in-game compatibility for any part.

Save and restart all Blender windows after installing.

# Base Builder Extended 18.0.16

- Added all 14 native regular-pipe and bubble-duct junction models under
  Decoration > Pipe Junction Tests: elbow, T, cross, 3-way corner, 4-way corner,
  5-way and 6-way. Each exports its exact internal part ID for user testing.
- Added sockets at every opening, compatibility with existing pipes, and local
  reflection rules for the new geometry. Both mesh quality settings are included.
- Relabelled the previous four bubble variants as Alternate ID Test parts and
  grouped them separately. The ordinary Bubble Duct remains the default straight.
- Native junction models are verified in Blender. Standalone in-game placement
  is deliberately unverified; these entries are for the user's requested tests.

Save and restart all Blender windows after installing.

# Base Builder Extended 18.0.15

- Restored curved (L), straight (S), T and X bubble ducts in both asset browsers,
  with their bundled models and thumbnails, labelled as legacy variants.
- Added end-to-end sockets for every restored shape, including all T/X branches,
  source/target cycling, mixed bubble/ordinary-pipe connections, and rotated parts.
- Corrected low-resolution BASE_BUBPIPE snapping: its centred Z-axis FBX needs
  different sockets from the high-resolution Y-axis native mesh.
- Preserved original object IDs and existing scene geometry. Legacy variant IDs
  are absent from the locally audited current-game object table; Blender snapping
  and serialization do not establish that these IDs work in an unmodified game.
- Retained the user-confirmed 18.0.14 mirror and ordinary-pipe fixes.

Save your work and restart all Blender windows after installing.

# Base Builder Extended 18.0.14

- Replaced Euler mirror guesses with full world/local reflection matrices.
  Audited 779 IDs and supplied geometry-based relations for 695 IDs, including
  native Corvette counterparts, diagonal walls, triangular floors and curved
  walls. Variant rotations and off-centre origins are included. Native detailing
  is retained; intrinsically asymmetric parts still cannot become exact mirror
  images through NMS rotation/Up/At alone and retain legacy handling.
- Mirror keeps native part identity, synchronizes SnapID after counterpart swaps,
  preserves proxy quality and shared source meshes, and supports all three axes.
- Added missing PIPE snap membership, end-to-end defaults for curved/straight
  pipes, and cross-ID pipe matching. Unsupported snaps leave objects in place.
- Sidebar now shows Base Builder Extended and the installed manifest version.
  Base Builder credit remains prominent for DjMonkey; Extended credit is
  Furiousfurby. Original guides, Patreon, Discord and Steam Games remain.
- Updates & Support has a small blue header icon within Blender's normal theme.
- Automated Blender 5.1.2 and 5.2.2 checks cover export roundtrips, double mirrors,
  oblique transforms, actual high/low meshes and physical pipe socket alignment.
  In-game validation remains separate.

Save your work and restart Blender after updating. Existing mirrored placements
are not automatically rewritten; mirror the original parts again to repair them.

# Community update 18.0.9

- Fixed Corvette weapon placement/import using the textured high-resolution
  models while retaining turret handlers and proxy quality switching.
- Rebuilt all six hab/walkway high-resolution models and the Thunderbird
  landing bay with native mesh transforms, correcting detached wall details.
  The bay retains its native hab-style exterior and floor opening.
- Replaced B_TUR_F's placeholder with an actual model thumbnail; both asset
  browsers now resolve the physical icon.
- Fixed bulk colouring of repeated proxy parts: every selected copy now updates
  its visible viewport colour and colour/material labels, rather than only the
  first copy. The colour picker now refreshes every selected copy as well.
- Mixed high-resolution and proxy selections keep their original geometry and
  textures. Colouring preserves each part's reserved UserData bits, transforms
  and selection; unselected parts retain their existing colours.
- Fixed the update handler during extension startup when Blender temporarily
  has no active view layer. Colour changes request a normal viewport redraw.
- Included the previously local shared-builder, material-provider and runtime
  part-handler integration hooks. They use the built-in implementation by
  default and do not require a companion add-on.
- Retained the reactor/girder mirror mappings, curve starting alignment and
  path-following rotation, fossil imports, cuboid models and station references
  from 18.0.8. Models, textures and dependency wheels remain bundled.
- Tested the final package in isolated Blender 5.1.2 and 5.2.2 LTS processes.
  These are Blender/serialization checks; no new in-game validation is claimed.

Install the attached plugin ZIP through Install from Disk, then restart Blender.
Parts previously changed to the wrong design must be restored separately.

# Community update 18.0.8

- Restored normal Duplicate Along Curve rotation: copies turn with the path
  and form a flower around a circle. Supersedes 18.0.7's parallel-copy behavior.
- Corrected only the starting alignment: the first copy at the curve's start
  matches the selected source's orientation, replacing the forced 180-degree
  X rotation. Following copies keep that relative alignment as the path turns.
- Retained curve radius, tilt, Objects Size and curve-transform behavior.
  Part IDs are repeated unchanged; counterpart swaps remain Mirror-only.
- To repair an array made in 18.0.7, restart Blender, select the original source
  part plus that curve, then run Duplicate Along Curve again. Reseeding removes
  the old world-orientation locks. Existing saved layouts are not auto-migrated.
- Verified five-petal circles, tilted circles, Euler/quaternion sources, open
  Bezier and NURBS paths, quantity changes, copying/reseeding arrays, save/reopen,
  export IDs, unlinking, and repair of a saved 18.0.7 array. Visually checked a
  Blender render using B_STR_J_NE. No in-game test claimed.

# Community update 18.0.7 (curve behavior superseded by 18.0.8)

- New Duplicate Along Curve arrays preserve the source part's world rotation,
  orientation and scale. The curve supplies positions only: copies do not turn
  with the path or inherit its tilt, point radius or object scale.
- The explicit Objects Size control remains available as a multiplier of the
  original scale. Ordinary duplication never selects a mirrored counterpart.
- Closed curves place copies around the loop without stacking the last copy
  over the first. Replacing a curve's source uses the new source's transforms
  and the requested quantity instead of reusing the old array's values.
- Existing saved curve arrays retain their previous layout. To use the new
  behavior on one, select the original source part and that curve, then run
  Duplicate Along Curve again. Save your work and restart Blender after updating.
- Mirror counterpart fixes from 18.0.6 are retained. Blender regression checks
  cover open/circular/NURBS paths, transformed curves, three rotation modes,
  parent/delta transforms, quantity changes, duplication, export vectors,
  unlinking, save/reopen and legacy layout compatibility. No in-game test claimed.

# Community update 18.0.6

- Replaced guessed mirror suffixes with an explicit registry of 266 native
  Corvette counterpart pairs. Unknown/unpaired IDs keep their original design.
- Reactors B_GEN_0 through B_GEN_3 no longer change design when mirrored.
  Numbered B_CON2 hull links also retain their design.
- Corrected the four B_CON_L_n / B_CON_R_n connector pairs; restored the Osprey,
  Arcadia heavy booster and both numbered Rockhopper wing counterpart mappings.
  Kept genuine numbered Streamlined Trim Cap and Aeron Diffuser pairs.
- Updated mirror metadata to match the registry. This also fixes the shared
  counterpart resolver used by groups and curves, not just the sidebar button.
- Auto-duplicate and mirror now changes the new copy, leaving the original
  object and mesh unchanged. In-place curve mirrors update follower meshes and
  exported part IDs, not only the curve's seed ID.
- Regression checks cover all 266 pairs in both directions, exported IDs,
  positive object transforms, double-mirror restoration, all four reactors,
  hull-link designs, groups and curve followers. No in-game test claimed.
- Restart Blender after updating. Parts already changed to the wrong design
  are not automatically identifiable; restore those from an unaffected build
  or manually select the intended original part.

# Community update 18.0.5

- Fixed Builder Tools > Duplicate passing a Part wrapper to Blender's selection
  API. Part, prefab and curve duplicates now return selectable Blender objects.
- Duplicate Along Curve now stores the requested quantity before update handlers
  run and synchronizes the curve controls. A count of one stays one instead of
  growing to two during the spacing refresh.
- Removed the launch buttons from Workspace and Parts & Prefabs. The NMS Asset
  Browser sidebar remains available; existing browser operators are retained.
- Rebuilt CUBEROOM and CUBEGLASS from native standalone placement rules and
  Part_* locators, with matching high-resolution and legacy FBX geometry.
  Preserved native UVs, normals and existing high-resolution materials/textures.
  Only the highest-detail shell is included, not stacked LODs, invisible proxy
  volumes or animated power overlays. Adjacent-room wall removal is not simulated.
- Restart Blender and re-import the affected rooms to replace cached old meshes.
  Existing open scenes are not automatically rewritten. No save-data transforms
  or in-game files are changed by this fix.

# Community update 18.0.4

- Fixed fossil imports returning a deleted placeholder object. Clipboard,
  Save Manager, Open Base and prefab import now receive the replacement object.
  Fossil transforms, palette data, timestamps and ordering are retained.
- Regression coverage includes all 143 fossil variants with repeated placements,
  and a 424-part Corvette containing a FOS_SKULL / FOS_HEAD_HD fossil.
- Compatibility audit against installed game executable 179666 (September 22,
  2026): current saves decode and round-trip through private copies; all 2,124
  build-object IDs and 1,344 part IDs remain present. Building globals are
  byte-identical to the previous audit.
- The game changed some placement flags, freighter styles/palettes and station
  scene definitions. The bundled model/reference library is retained in this
  bug-fix release; visual parity with every updated scene and in-game placement
  have not been revalidated. See GAME_UPDATE_COMPATIBILITY.md.

# Community update 18.0.3

- Added a separate **Vanilla Hidden Station Parts > Interior** Asset Browser
  category for audited native game assets that are valid station build objects
  but hidden from the normal construction menu.
- Restored `GAMETABLE` as **Holo-Arena Game Table**. The current 7.01 game table
  marks it placeable in station interiors and back sections and retains its
  native model, scaling and 3-D rotation. This update claims visible placement,
  not automatic initialization of the multiplayer game interaction.
- Re-audited the 7.01 build tables against Cosmos 7.0: no station ObjectID,
  part-model mapping or station placement flag changed in the hotfix.

# Community update 18.0.2

- Import from Clipboard and Open Base (.json) now automatically load the station
  reference when the imported record identifies a PlayerSpaceStationBase.
- Those imports expose a collapsed Station Reference section under Import/Export,
  without requiring Save Manager or access to a local save slot.
- Parts-only JSON remains a parts-only import. Arrays are accepted as well as
  Objects dictionaries; station detection never uses a previous import's type.
- Station records without GalacticAddress load with an isolated appearance key.
- Checked the real clipboard operator with a 318-part station, JSON-file imports,
  repeat imports, reference refresh, and ordinary base/Corvette imports.

# Community update 18.0.1

Based on Kuma's 18.0.0 release of DjMonkey's No Man's Sky Base Builder.

- New parts use their default origin and scale when the active object is deselected. Selected-object placement still works across high-res, proxy, and special-part paths.
- Station imports automatically add the compact reference: all six hull families, large optional attachments, and six interior cutaways. Repeated geometry is shared and cutaways are prebuilt.
- Station and orbital Space bases have separate Save Manager tabs. Station reference controls appear only under Station.
- Reference refresh preserves player parts and eye choices. Remembered station visibility and compact Outliner defaults are retained.
- All 22 custom settlement icons and the three missing settlement class-marker catalog entries are included in both browsers.
- Mixed special/ordinary parts retain save order on export. Station identity includes its system address. Renaming a station does not rename a ship; Corvette rename accepts valid ship slots.
- Dependencies are bundled for Windows / Blender 5.1, without first-use pip downloads.
- DjMonkey's branding and support links are preserved. Contributor credits for Kuma and FuriousFurby are in Preferences and CONTRIBUTORS.txt.

Kuma's high-resolution assets, native movable Asset Browser, favorites and recents, proxy switching, material system, group tools, and Cosmos save translation are retained. The station reference files contain their own geometry; the reference's dimensions and surfaces have not been simplified.

For habs or the Thunderbird bay already placed in an older saved scene, select
those parts and switch to Low-Res, then back to High-Res to refresh their meshes.

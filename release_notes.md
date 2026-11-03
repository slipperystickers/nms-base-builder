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

- Show Light Fissure beams in red/orange in Blender's detailed preview while retaining the game part and export data.
- Give the Holo-Arena Game Table an icon rendered from its actual game mesh.

# 18.2.39

- Reduce the base download by about 352 MB (34%) by moving detailed addition models and textures into the optional High Detail Proxy pack. Geometry, textures and icon resolution are unchanged. The pack is stored outside the extension so updates keep it installed.
- Download and install verified updates automatically when the update checkbox is enabled. Manual Download and install also completes installation. Wait for editing, dialogs and renders to finish, briefly pause the Asset Browser, and reload the updated extension.
- Show update failures in Updates & Support and verify archive identity, version, minimum Blender version and SHA-256 before installation.

# 18.2.38

- Add ownership copying from another saved Corvette in Advanced Build Metadata, with preview, stale-save protection and a separate opt-in for destination-save ownership changes.
- Explain empty saved USN names. Preserve wrapped .nmsship ownership and source metadata during package exports, including the ship's legacy-colour flag.
- Verify complete ship records, tech/inventory slot placement, appearance, build placement and unknown fields through package and Blender-project round trips.

# 18.2.37

- Fix mini chat's horizontal scrollbar, long-message wrapping and image clipping when resizing. Keep vertical history scrolling and the full-width message field.

# 18.2.36

- Correct outdated Corvette models, names, categories and misleading icons. Thunderbird Landing Thrusters now appear under Access and Docking; distinct plating shapes have separate previews.
- Keep original game icons by default, with clean transparent HD replacements for broken or missing artwork.
- Improve detailed-proxy placement speed without reducing geometry or texture detail, and remove chat's polling delay when opening its window.
- Add an advanced ownership/metadata editor beside the build name. Full build files preserve attribution; destination-save ownership changes require a separate explicit option.
- Preserve NMScribe compatibility, with native generation and export tests on Blender 5.1 and 5.2.

# 18.2.33

- Correct Forsaken variant menus using each part's native game GroupID, keeping Hornet, Viper, Mantis and hull families separate.
- Add 87 native mirror pairs for new wings and hull sections, with measured placement geometry for Blender's mirror tool.
- Replace 20 game-supplied red-X thumbnails with clean renders from the native meshes.
- Explain in the Asset Browser that NMS 7.10 assigns the Deathwrought Amplifier the same geometry as Aeron Pyramid; its correct part ID remains intact for export. The new rim and cap meshes also rely on game parallax shading for their detail.

# 18.2.32

- Add 214 supported Forsaken 7.10 part IDs and variants, including Corvette cockpits, hull sections, wings, reactors, decorations and gravity floor, ramp and wall. Include native icons, lightweight proxies, detailed models and portable textures. Preserve native IDs and placement transforms for export.
- Test all 214 parts for loading and export in Blender 5.1 and 5.2. Confirm NMScribe shape generation and native export in both versions. Full in-game placement still needs testing.
- Two new native records, `B_LND_D` and `B_TRU_I`, have no matching model files in the installed game archives and are excluded from the supported catalog.
- Includes the chat, theme, save export, decal, asset browser, prefab and building fixes detailed below since public 18.2.0.

# 18.2.31

- Distinguish Pipe — Automatic from Pipe — Fixed in the Asset Browser, search, favourites, recents and part names. Explain the in-game shape changes in hover help, including that automatic pipes currently have a straight Blender preview. Existing part identities and exports are unchanged.

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
- Close individual DMs with the inline ×. History is retained; clicking the person or receiving a new DM reopens the conversation.
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

- Fixed Mirror, Flip, and Turn doing nothing to BBE groups. Group orientation actions now reflect the cached parts about a common local plane and rebuild the group for export.
- Preserved parent links, parent inverses, and world placements when mirroring swaps a part to a renamed native counterpart.
- Fixed orientation actions being ignored for ordinary Blender objects.

Verified reflected Rockhopper fin surfaces on all three world axes, parented and with either scale sign, plus grouped orientation and export/reimport in Blender 5.1.2 and 5.2.2. This does not add a native mirrored Hyperspace Beacon asset or change negative-scale export behavior.

# 18.2.8

- Fixed bubble preview updates repeatedly resetting viewport selection and preventing gizmo drags, including after reopening a saved ship.
- Inspect tube shapes on import and project load. Repair missing or malformed shape metadata and stale snap references while preserving placements and valid unfinished bends.
- Added **Builder > Check & Repair Bubble Tubes** for older projects. Remaining connection problems are reported for correction.
- Connected branch turns reject unsupported joint angles, including 45 degrees and cumulative small turns beyond the supported range.
- An unconnected straight tube now offers six local starting directions. The next straight or elbow follows the chosen end, and the choice survives saving and reopening.

Validated in Blender 5.1.2 and 5.2.2 LTS, including native mouse-event gizmo drags in the supplied affected ship before and after a save/reopen cycle in 5.2.2. Game saves were not modified; fresh in-game validation is still needed.

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

- Mini mode shows messages and a compact message field. The small options menu keeps users, attachments, snapshots, and window settings available.
- The users and conversations sidebar can be hidden independently. Mini mode and sidebar visibility are remembered.
- Always on top now applies the native Windows window position flag. Side placement preserves the window title bar and keeps Mini mode narrow.
- Changing conversations clears old message layouts completely.

---

# Base Builder Extended 18.2.4

## Chat, themes, and toolbar
- Chat is one toolbar button. Account and opt-in controls are under **BBE > Chat & account settings**; the old chat popup is no longer part of daily messaging.
- The Messenger can be resized, pinned above Blender, or placed against the left or right side of the screen. Its position and pin setting are restored when reopened. A separate Online users list shows who is present; click a name to start a direct message.
- Messenger colors follow Blender's active interface theme, including themes changed while it is open.
- **BBE > Themes** has ten choices: Blender Dark, Blender Light, Slate, Midnight, Ocean, Forest, Ember, Violet, Rose, and Sand. Theme choices affect Blender only when selected; save Blender Preferences to retain one across restarts.
- **Assets** is a one-click top toolbar button with its own icon.

## Installation
Windows x64; Blender 5.1 or newer. Install `no_mans_sky_base_builder-18.2.4.zip` through Blender's **Install from Disk**, then restart Blender. Existing chat names, keys, messages, and opt-in settings remain valid.

---

# Base Builder Extended 18.2.3

## Messenger window
- Chat opens in a separate, responsive messenger window with a buddy list, conversation history, direct messages, and images shown inside the conversation.
- Enter sends a message; Shift+Enter adds a new line. The Snapshot button queues the Blender window image for review before sending.
- Screenshot images and other supported still images can be reduced before upload. Uploads and image previews run outside Blender's UI thread. Short videos remain downloadable attachments.
- The top Chat button opens the messenger. The small arrow beside it holds the optional enable switch and name settings. No chat requests are made before chat is enabled.

## Installation
Windows x64; Blender 5.1 or newer. Install `no_mans_sky_base_builder-18.2.3.zip` through Blender's **Install from Disk**, then restart Blender. Existing chat names, keys and messages remain valid.

---

# Base Builder Extended 18.2.2

## Chat fixes
- Two-character names such as FF are accepted. One private recovery key can claim and switch between up to three names; existing keys and messages remain valid.
- BBE identifies its chat requests to the website so Cloudflare does not reject Blender's default Python request identity. Website blocks now have a clearer error.

## Installation
Windows x64; Blender 5.1 or newer. Install `no_mans_sky_base_builder-18.2.2.zip` through Blender's **Install from Disk**, then restart Blender. Chat remains optional and starts off for new profiles.

---

# Base Builder Extended 18.2.1

## Optional community chat
- Chat starts off. Turn on **Enable Chat** in the top toolbar to join, and turn it off any time to stop chat requests. Your claimed name stays in your Blender profile; copy its private recovery key to restore it on another profile.
- See online users, send public messages and direct messages, and share supported images or short videos. Files are saved to a location you choose when downloaded.
- Queue a screenshot of the Blender window with Snapshot; review and explicitly send it from the chat controls. Chat requires Blender Online Access. Project files and game saves are never uploaded automatically; a screenshot can show anything visible in the Blender window.
- Attachments are limited by file type and size, checked by the server, and downloaded as files rather than opened in the chat.

## Installation
Windows x64; Blender 5.1 or newer. Install `no_mans_sky_base_builder-18.2.1.zip` through Blender's **Install from Disk**, then restart Blender. Community chat is optional and requires the FuriousFurby chat service.

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

release 18.1.86 - October 18, 2026
--------------------------------

- Preserve the current session's local account, save slot and selected build when opening another `.blend`, without importing that ship's parts. Re-read the destination save and match the selected build by identity; unavailable or ambiguous targets remain unselected. Discard another author's saved account/slot choices and stale runtime caches. Save choices remain accessible after refresh failures.
- Restore Asset Browser grids in older dedicated pop-out layouts whose helper object was omitted from the project. Recreate and pin the hidden browser helper without changing the active model or repurposing a similarly named user object. New layouts retain an explicit browser marker.
- Complete missing-HD-texture fallback during file loading, before the viewport can draw unresolved materials. The automatic conversion uses no intermediate progress redraw; its explanation appears after loading. With the HD pack present, TestBed's 165 texture images resolve and decode. With it absent, all 293 parts keep their identity and transforms while switching to simple proxies with no missing texture references.
- Show the selected Corvette's slot, name and part count on the picker button. Keep Select Corvette as the empty prompt, automatic menu closing and existing warning/repair controls.
- Verified the exact select-save/Corvette -> open TestBed -> refresh -> export sequence in isolated Blender 5.1.2 and 5.2.2 GUI processes, both loading and retaining window layouts. Browser thumbnails restore; ordinary and optimized fixture exports pass. The source project and real game saves are unchanged. The warning when opening a 5.2 file in 5.1 is Blender's version-compatibility warning and remains visible.
- Fix refresh and tab switches failing with `enum "9" not found` (or another previous build index). Restore a remembered selection only when that identifier still exists in the new list; otherwise show Select Corvette/Base. Clearing or changing the save also clears stale selections without changing scene metadata or game-save data.
- Edit Ship Name directly below Select Corvette in both I/O and the sidebar Save Manager. The field shares the existing project metadata, applies to ordinary, optimized and `.nmsship` exports, and explains when the name is saved. A blank field previews the selected saved name; the export review shows the final name before confirmation.
- Keep update polling alive when opening a Blender file. Automatic checks also resume when Online Access is enabled later, with retry after failures, bounded helper timeouts, and a clear up-to-date result. The checkbox is labeled Automatically check for updates; installation remains a separate user action.
- Fix Export to Save and Optimize & Export rejecting coincident cable endpoints as invalid part directions. Preserve the zero-length cable data. Invalid solid-part directions still stop export and now identify the part and field.
- Start the Corvette package file browser with a `.nmsship` filename and correct the extension as the filename is edited.
- Allow a design started in Blender to export a complete `.nmsship` without first importing a ship. Reuse the existing minimal Corvette ship records when no imported source, selected save or explicit template is supplied. No cockpit or template build parts are inserted.
- Retain imported ship inventory, technology, stats, appearance and additional package entries; explicit selected-save and template choices remain available.
- Add Feature Help for package export and inverse palette finishes.
- Correct the detailed Timber, Alloy, Stone and Builder roof gables and quarter-gables (`*_ROOF_E_CAP` / `*_ROOF_E_Q`). Their HD meshes had an extra local Z=1.333333 placement-locator translation. Recognised library meshes now match the native LOD0 coordinates, including meshes embedded in saved projects without the optional pack. Custom-edited meshes and exported object transforms are preserved.
- Verified a supplied 291-part project in Blender 5.1.2 and 5.2.2: all four affected gables migrate, all exported object records stay identical, and the original file is unchanged. Checked all eight variants against native game vertices (maximum error below 0.000002 units), repeated quality switches, saved-file reopen, UVs and custom normals. Live in-game confirmation is pending.
- Fix a reproduced native shutdown crash with the file browser still open: toolbar cleanup no longer changes region visibility after Blender clears the active window. Overlay cleanup also tolerates an absent screen. The exact quit sequence exits successfully in Blender 5.1.2 and 5.2.2, and ordinary disable/re-enable still restores toolbar visibility.
- Verified the supplied 293-part TestBed through ordinary and optimized export into temporary game-save fixtures in Blender 5.1.2 and 5.2.2. Both zero-length wires, inventory, stats and appearance survived; backups were created and the supplied `.blend` was unchanged. In-game validation is pending.
- B_CON2 color mapping is unchanged. Inverse finishes swap palette slots; the reporter says the same behavior occurs in-game.
- The reported bubble-duct undo crash remains open pending the reporter's crash log. Isolated placement tests did not reproduce a native crash. A separate real-click test found that modal browser placements did not create individual undo steps; this is recorded for the follow-up investigation and is not claimed fixed here.
- Two diagnostic GUI runs with automatic window screenshots encountered a native NVIDIA `nvoglv64.dll` access violation; its cause is unconfirmed. Subsequent normal project-load/export GUI tests passed in both Blender versions and the installed profile. This release does not claim to fix that graphics crash.

release 18.1.85
--------------

- Objects-only clipboard imports keep the destination scene's build type, name and retained ship metadata.
- Keep both `.nmsship` and `.nmsbase` export commands available and allow an explicit saved-ship source for metadata.

release 18.1.84
-------------

### Corvette picker
- Close the Corvette selection menu after choosing a ship. Keep its button labeled Select Corvette and show the selected ship below it.
- Remove freighters from selectable ship lists and selection lookup in both Main and Expedition saves. Preserve Corvette health warnings and repair actions.

release 18.1.83
----------------

- Fixed WASD being blocked by the sidebar Asset Browser listener in saved workspaces; active transforms and controller sessions still retain input ownership.
- Keep export progress visible through validation, verified writes and list refresh.
- Speed up save checks by avoiding unnecessary copies of unchanged data and repeated translation-table construction, retaining backups and preservation validation.

release 18.1.82
-------------

## Cockpit selector stability and feature help

- Fix changing/garbled cockpit selector labels by retaining their strings for the dialog and undo/redo lifetime. The reviewed cockpit list stays stable; changed or removed entries require reopening instead of redirecting a selection.
- Add Swap Cockpit Order to both BBE menus, retaining the Optimizer Settings shortcut. The swap changes scene export order immediately, never physical placement. Ordinary and optimized exports use that order; saving the .blend keeps it with the project, and Undo/Redo works.
- Add clearer hover descriptions, contextual How this works popups and BBE Feature Help. Topics explain cockpit order, optimizer settings, Corvette export, keep-build repair, file replacement, recovery and WASD navigation, including when changes take effect and what can undo them. Help is local and does not modify data.

## Ship warnings, keep-build repair and new-slot export

- Check Corvette health as soon as a save is loaded. The shared I/O selector highlights affected builds in red, explains the problem and identifies ship slots consistently as 1–12. Missing-build Corvettes are also listed; the freighter stays separate.
- Add Repair — Keep My Build directly below the selected build in I/O, in both the top bar and sidebar, and Repair Build in Ship Management. Repair retains the saved objects, transforms, colors and readable inventories, technology, hyperslots, class, stats and appearance. Invalid data resets are listed and require separate confirmation. A missing build can be supplied through scene export or Replace From File.
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

Website support 2.1.0 was deployed and independently verified before publication of 18.1.84. Local client/server integration, consent/offline tests and Blender 5.1.2 / 5.2.2 checks passed. Normal website support conversations remain available separately.

release 18.1.81
-------------

## Ship Management with uncertain Corvette links

- Open Ship Management when an existing Corvette build link is missing, duplicated, invalid or points to an unrecognized ship. A fresh install no longer makes these existing save conditions look like a failure to open the manager.
- Keep inventory, cargo, technology, ship class, saved stats and existing hyperslot edits available. Before saving, compare the complete draft with the original snapshot and preserve all uncertain ownership, build and surrounding context records exactly.
- Lock Move Up/Down and Add Minimal Corvette only in affected Main or Expedition contexts. Healthy contexts remain editable independently. Duplicate Save / Clear Builds still requires valid links in every context.
- Add an Ownership notice / Link Status dialog explaining the affected context and slots locally. No save upload is required and no ownership link is guessed or automatically rewritten.
- Start on the selected Corvette and context when available, otherwise the active or first owned ship.

Verified with synthetic English-key and obfuscated saves and Blender 5.1.2 / 5.2.2 LTS operator tests. The notice and disabled controls were also inspected in Blender 5.2.2. This protects existing uncertain links; it does not repair them or claim in-game validation of the reported user's save. The existing verified-backup writer is unchanged.

release 18.1.80
-------------

## Detailed proxy loading and Asset Browser helper

- Resolve each detailed model's texture paths against the local HD pack before the model enters the scene. Progress redraws should no longer show the pack author's missing texture paths as pink materials.
- If a detailed texture is missing or the optional pack is damaged, reject that model and keep or use its simple proxy. Projects saved on another computer with unavailable detailed textures switch their BBE parts and groups to simple proxies on opening; object identities, transforms and group caches are retained. The original `.blend` is not overwritten.
- Remove BBE's hidden Asset Browser context helper from the scene after its window closes, while retaining it for the next browser launch.

The detailed-proxy pack remains optional. These changes were tested with the pack installed, with its textures unavailable, and with simple-proxy fallback in Blender 5.1.2 and 5.2.2 LTS. Install **no_mans_sky_base_builder-18.1.80.zip** through Blender's **Install from Disk**, then restart Blender.

release 18.1.79
-------------

## Group color reset and Charon Forge activation check

- Fix Reset Default Color on a selected group. It restores each child part's cached color, including simple proxies, without the group's missing `ObjectID` error.
- When Charon Forge is active or set to load at startup, BBE asks before activating: Continue disables Charon and enables BBE; Cancel keeps Charon and leaves BBE inactive.
- If Charon is enabled after BBE, BBE warns that the current session is incompatible and asks for a save and restart. BBE cannot control Charon's installer or safely undo their overlapping registrations after Charon has activated.
- The reported Blender 5.2 `acquire(): cookie doesn't exist!` traceback occurs in Blender's extension installer before BBE code runs. Save work, fully restart Blender, then retry Install from Disk. If it recurs, check whether Blender's session temporary directory is being removed.

Install the intact **no_mans_sky_base_builder-18.1.79.zip** via Blender's **Install from Disk**, then restart Blender. Tested in Blender 5.1.2 and 5.2.2 LTS; the Charon prompt was checked in a separate Blender 5.1 GUI session. Existing projects and game saves were not changed.

release 18.1.78
-------------

## Recovery, stability and a clearer interface

### Automatic project recovery
- Fix recovery timers being repeatedly restarted by other add-ons' save-copy operations or normal saves. BBE now keeps its own schedule, including after a delayed first idle tick.
- Choose a time interval (10 minutes by default) or placement count (5 parts by default). Keep the latest three consecutive recovery saves per project; each new save replaces only the oldest generation.
- See the live countdown, placement progress, waiting reason, and backup errors. Failed backups retry after one minute.
- Use the dedicated Recovery menu or sidebar panel to back up now, open a recovery copy, or open/change the shared backup folder. Project copies and game-save backups use separate subfolders.
- Recovery copies do not overwrite the original project. Saving waits while undo/redo settles or an active editing operation makes saving unsafe.

### Stability and importing
- Harden rapid undo/redo handling around generated window meshes, decals and lighting refresh.
- Import JSON/TXT designs with missing or blank base-type metadata using the selected fallback, including designs that have never been assigned to a ship or base.
- Add visible staged progress across import/export workflows, including Optimize & Export and Ship Management save operations.
- Correct the four B_STR_T NW fuel-pod cover rim display meshes and refresh recognized older proxies without replacing custom edited meshes.
- Clarify scene, selected-build and save-slot part counts, and the Account/Save Slot selection steps.

### Interface improvements
- Restore the direct prefab catalogue in both toolbar and sidebar; remove the obsolete Parts list and nested Legacy Asset Browser section.
- Add transparent colored symbols across the toolbar, sidebar and action controls, with RGB Color and hammer Builder icons.
- Tighten dropdown widths and place recovery Minutes/Qty beside its mode selector. Preserve the Color palette width.
- Clean up BBE branding and sharp native creator credits. Fresh workspaces start with only BBE expanded; saved workspace panel states remain respected.

### Install
Download **no_mans_sky_base_builder-18.1.78.zip** below. In Blender, use **Install from Disk**, select the intact ZIP, then restart Blender. Keep the previous installer for rollback. The GitHub source archives are not the installer.

Windows x64. Recovery timer regression checks passed in Blender **5.1.2** and **5.2.2 LTS**, including real save-copy callbacks, three-generation rotation, source-file preservation, failure/retry behavior and placement triggers. The countdown and automatic backup were also checked in the Blender UI. The reported 676-part TXT design imported completely in both versions.

Includes all changes since 18.1.63; automatic update checks remain opt-in. Base Builder by DjMonkey. Extended by FuriousFurby.

release 18.1.63
-------------

- Ask once whether to enable automatic update checks. Yes enables and saves Blender Online Access and the startup-update setting, then checks for updates.
- No or dismissal keeps automatic checks off and remembers the choice across restarts and upgrades. An existing disabled setting is respected.
- The prompt explains that Blender's global internet access also applies to other add-ons. Forced offline mode stays offline; background sessions do not prompt or start automatic checks.
- Updates & Support can enable checks later using the same Yes/No prompt. Installation of downloaded updates remains user-controlled.
- Includes the complete Colour & Materials sidebar restored in 18.1.62.

Verified Yes/No operators, preference persistence across restart, legacy settings,
failed preference saving, and forced offline mode in Blender 5.1.2 and 5.2.2 LTS.
The first-run prompt was visually inspected in Blender 5.1.2.

release 18.1.62
-------------

Restore the complete Colour & Materials section in the Base Builder sidebar,
including the palette selector, swatches, and colour picker. The top-toolbar
Color menu remains available. All 18.1.61 runtime files and assets are retained
except the restored panel registration, version number, and release instructions.

Install no_mans_sky_base_builder-18.1.62.zip using Blender's Install from Disk,
then restart Blender. Windows x64; Blender 5.1.2 and 5.2.2 LTS validation covered
panel registration, all 18 palettes, and the existing bulk-colouring checks.
The ZIP passed archive integrity and comparison with the published 18.1.61 installer.

release 18.0.9-station-reference
-------------

## Fixed

- Selecting multiple repeated parts now colours every selected piece visibly.
- The colour picker updates every selected copy's viewport colour and labels.
- Mixed HD/proxy selections preserve their geometry and textures, while
  unselected parts keep their existing colour.
- Colour edits preserve part identity, transforms and reserved UserData bits.
- Extension startup safely handles Blender's temporarily restricted context.

Includes the previously local shared-builder/material/part-handler integration
hooks, with the built-in implementation used by default. No companion add-on,
separate model download, NMSDK, external Python or pip command is required.

Retains the reactor and girder mirroring fixes, Duplicate Along Curve behaviour,
fossil import fixes, corrected cuboid models and station-reference tools from
18.0.8.

## Installation

1. Download **no_mans_sky_base_builder-18.0.9-station-reference.zip** from Assets.
2. Save your Blender work.
3. Open **Edit > Preferences > Get Extensions > Install from Disk** and select
   the intact ZIP.
4. Enable **No Man's Sky Base Builder**, then restart Blender.

Windows x64; tested with Blender **5.1.2** and **5.2.2 LTS**. Use the attached
plugin ZIP for installation. GitHub's Source code archives are for developers.
Keep the previous installer if you need to roll back. Previously misidentified
parts are not repaired automatically by upgrading.

## Verification

The final ZIP was extracted into a clean folder and tested for bulk colouring,
colour picking, mixed HD/proxy parts, exported colour data, duplication, curve
following, all 266 mirror pairs in both directions, fossil imports, corrected
cuboid parts, textured Corvette weapons, aligned hab/bay details, both browser icons, UI/assets, station imports and private-copy save round-trips.
Archive CRCs and every extracted file hash were checked. No live game save was
modified, and no new in-game test is claimed. SHA256SUMS.txt is attached.


release 6.5.2
-------------

* Fixed an issue where the Asset Browser would not load on Linux.


release 6.5.1
-------------

* Fixed incorrect scale of Swarm Trophy parts.


release 6.5.0
-------------


* A UI polish pass across the panels of the tool, improving visual consistency across different tools. (credit: Kuma the Wizard, with additional feedback/tweaks from DjMonkey)
* Panels that contain particular tools are now collapsed by default, to help with initial overwhelm when loading for the first time. (credit: DjMonkey)
* New workspace buttons that simplify the Blender UI and quicker access to the Asset Browser UI. (credit: Kuma the Wizard & DjMonkey)
* Expanded Mirror Options: Specify different axis options and auto-duplication settings with these new options (credit: Kuma the Wizard)
* Expanded Curve Options: Selecting the "Duplicate Along Curve" button now provides an expanded property box with dynamic options like number of parts and part scale. Selecting and deselecting the curve will toggle these tools. (credit: Kuma the Wizard)
* Batch Tools: Various options for selecting and swapping multiple objects all at once. (credit: Kuma the Wizard)
* Added a colour picker button that lets you drop material and colour options quicker between parts from another part. (credit: Kuma the Wizard)
* Bugfixes and visual updates to the Save Manager tools. (credit: Kuma the Wizard)
* Added a top section for logos, guides, and support (credit: Kuma the Wizard & DjMonkey)
* Added Prismatic Core Trophy models to the catalogue. (credit: DjMonkey)
* Consolidated the terminology and file format for Presets => Prefabs. From this update onward both Blender and App will produce `.nmsprefab` files compatible with both tools. Blender can still read `.json` preset files for backward compatibility. (credit: DjMonkey)
* Prefabs now appear in a left-most tab within the Asset Browser UI. (credit: DjMonkey)



release 6.4.1
-------------

* Added parts for 6.4.0 - Swarm update.
* Added a built-in Save Editor panel to import/export bases and corvettes to a save directly from the Blender extension itself. A big thanks to Kuma the Wizard who spent a few weeks building this feature out and the patience listening to feedback from myself and other community builders.
* Fixed an error pop up when using the Duplicate Part button.


release 6.3.0
-------------

* Improvements and optimizations to the mirror, mirror across X, and flip functions (Thanks to Kuma the Wizard).
* Model fixes to B_DECO_Q_1,B_STR_AA_N,B_STR_AA_S, S_SAIL, TOYCORE, PANEL_GLASS, S_ROOF objects and added settlement class objects (Thanks to Kuma the Wizard).
* Added more logic checks to the PySide start up to prevent start up errors for some users with the Asset Browser.
* Fixed an issue where Blender would become unresponsive after loading the Asset Browser.
* Added parts from 6.3.0 update including GAMETABLE and Quicksilver rewards.
* Removed extraneous print statements.


release 6.2.0
-------------

* Added the option to tag base parts as a "Favourite" which adds them to a dedicated tab in the Asset Browser.
* Added the option to pin category tabs which places them in their own pinned section to the left of the tab bar.
* Base Building App prefabs (.nmsprefab) can now be listed and loaded natively using the Preset/Prefab mechanism.
* Fixed visibility of the Vesper Rim part in the asset browser.


release 6.1.7
-------------

* Added Freighter colour options to the Colour and Materials tool.
* Editing colours/materials should no longer reset additional UserData information like logic switches, states, etc.


release 6.1.6
-------------

* Revamped the colour options to allow users to use colours from a variety of material palettes.
* Added a button only export the objects of the base to the user clipboard.
* Re-processed meshes for STORAGEPANEL and BUILDFLATPANEL.
* Fixed an issue where the Asset Browser would not load on Linux.
* Fixed an issue where the Asset Browser tabs would be squashed and not be scrollable on Mac.
* Fixed a mesh placement issue with the B_STR_U corvette pieces.


release 6.1.5
-------------

* Fixed an issue when adding parts from the Asset Browser was not taking into consideration the current selection.
* Fixed an issue where miniimze and maximize buttons disappared from the Asset Browser window.
* Fixed an issue where the Wonder Projector was not retaining it's message data.


release 6.1.4
-------------

* It is no longer required to installed bpy_external for the Asset Browser to work.
* Visual refresh to the Asset Browser which improves readability and consistency with the Base App.
* Added connection point data to the Corvette Mini Teleporter.


release 6.1.3
-------------

* It is no longer required to install Python in order to use the Asset Browser tool
    * The tool now uses the Python installation that is part of Blender itself.
    * Using the Asset Browser should now be a lot more stable to use for users setting things up for the first time.
    * Existing users can remove their Python installation if they were only using it for this tool.
    * There is still a small wait on the first-time load as things initialize.
* Added a Guides button to the tool.


release 6.1.2
-------------

* Ported add-on structure to newer Blender extension structure.
* Removed YAML as a Python dependency as it’s no longer used.
* Fixed an issue where the corvette “_Y_NE” parts were not being listed in their respective variants panel in the Asset Browser.
* Collapsed L/R corvette connector pieces into one item with the variants sub-window in the part drawer.
* Fixed naming of variants for the Atlas Corvette parts.
* Fixed visibility of NW parts for the Hardrame Diffuser Rim
* Fixed visibility of Speedbird Dome Rime in the Asset Browser
* Fixed an issue where the Asset Browser could not load on systems of certain language settings.


release 6.1.1
-------------

* Improved the search responsiveness on the Asset Browser.
* Part variant’s have been removed from the Asset Browser and are now accessed from a sub-menu from the “parent” part in the Asset Browser.
* Added the “Mirror Across X Axis” tool.


release 6.1.0
-------------

* Added parts from 6.1 BREACH update.


release 6.0.0
-------------

* Added parts for Corvette pieces
* Added parts for Fossil pieces
* Added other missing parts from recent updates.
* Added a mirror and flip button which can be used on certain corvette pieces.
* Improved support for message fields.
* UserData value is now retained during import and export, which should make Corvette workflows nicer.


release 2.1.4
-------------

* Added parts from Worlds Part II (Ruins, exotic plants, etc)


release 2.1.3
-------------

* Added support for base parts added up to Worlds Part 1 Update.
* Adjusted hallway and walkway freighter models.
* Added some Linux compatibility thanks to dsalt on GitHub.
* Updated output JSON format to match latest version found in the game.


release 2.1.2
-------------

* Fixed model issues on FRE_FACE_WINDOW, BLD_HOLOGEK, CREATHOLOGRAM, S_GAZEBO0.
* Replaced GEK statue's with their actual representation, rather than Blobs.
* Added cable connection point to U_SILO_S, U_EXTRACTOR_S, and U_GASEXTRACTOR
* Added a UI control to the cable window to toggle between the different cable types. (Power, ByeBeat, Portal, Pipe)
* Renamed the tab to "No Man's Sky Base Builder"


release 2.1.1
-------------

* Fixed model issues on BLD_BUI_HAND, BLD_CRANE, and MAPTABLE.
* Fixed error when using the snapping buttons on power controllers.
* Fixed snapping data for large structures/prefabs.
* Fixed an issue where connecting power controllers would make extraneous wires and controllers.
* Added power connections to the base teleporters.


release 2.1.0
-------------

* Fixed errors when using Blender 4.0
* Base parts up to date as of ORBITAL update.


release 2.0.5
-------------

* Fixed a bug where some scaled parts were being assigned a random color.


release 2.0.4
-------------

* Added model support for Timber, Alloy and Stone variant pieces.


release 2.0.3
-------------

* Added some automation scripts for updating this tool.
* Added a bunch of missing objects since the last year (Expeditions/Sentinel/Outlaws/Endurance/Waypoint).
* Thanks to Peter Laan for assistance with missing parts and their source file locations.


release 2.0.2
-------------

* Simplified Qt Dependencies. (Swapped to PySide6)
* Compatible with latest Python 3.10 and Blender 3.0 versions.


release 2.0.1
-------------

* Fixed an issue where loading a base using presets would error.
* Small fixes to asset naming and categorization in the Asset Browser.


release 2.0.0
-------------

* Added over 250 new parts to support the FRONTIERs update.
* Fixed issues with cable placement logic introduced with FRONTIERS.
* Added a new Asset Browser UI for better browsing on building parts. (See readme and video tutorials for more information.)
* Added category support for Presets. The tool will now recognise sub-folders within the user Preset folder.
* Added a button to apply the default colour to a base part.
* A fancy new logo.


release 1.3.3
-------------

Thanks to Wormhole Badger (@MarkAlanSwann1) for supplying the proxy models for
this update.

* Added a Fireworks category with firework items.
* Added support for the following items.
    * Unlockables
        * BASE_HOUDINI1
        * BASE_HOUDINI2
        * BASE_HOUDINI3
        * BASE_INFEST1
        * BASE_INFEST2
        * BASE_INFEST3
        * BASE_LAVA1
        * BASE_LAVA2
        * BASE_LAVA3
        * BASE_SWAMP1
        * BASE_SWAMP2
        * BASE_SWAMP3
        * BASE_TOYJELLY
        * SLIME_MED
        * SPOOKY_PLANT
        * SPEC_FIREWORK01
        * SPEC_FIREWORK02
        * SPEC_FIREWORK03
        * SPEC_FIREWORK04
        * SPEC_FIREWORK05
        * SPEC_FIREWORK06


release 1.3.2
-------------

* Added the Derelict Freighter Turret as a buildable item.
* Added some window and door items to the visibility ghost list.
* Changed blender ops naming from "nms." to "object.nms_".
* Added more snapping positions so walls can be snapped below floors.
* Complete rework of triangle pieces.
    * Triangles are now the correct size.
    * 3D model updated to better represent part, with indication of the direction of the triangle.
    * Fixed snapping points on triangle pieces.
* Renamed Parts...
    * BASE_HOTPLANT1 > * BASE_HOTPLANT01
    * BASE_HOTPLANT2 > * BASE_HOTPLANT02
    * BASE_HOTPLANT3 > * BASE_HOTPLANT03
* Added support for the following models ...
    * Freighter
        * TURRET_ABAND - Freighter Turret
* Fixed a power connection position on the Light Floor (credit: @bjj)
* "Connect" can now operate on multiple selections. (credit: @bjj)
* Added a "Select Connected" button to the Power Tooling (credit: @bjj)
* Added a "Select Floating" button to the Power Tooling (credit: @bjj)
* Fixed a power line division bug (credit: @bjj)
* Material clears when importing OBJs. (credit: @bjj)
* Power Controllers now created at the 3D cursor position. (credit: @bjj)


release 1.3.1
-------------

* Added `bl_options = {"UNDO", "REGISTER"}` everywhere required.
* Changed material colour of U_PORTALLINE.
* Added .gitignore file.


release 1.3.0
-------------

* Fixed some Blender error messages when interacting with non-NMS scene items.
* Missing/Modded parts will be named their ID instead of "cube".
* New models for C_ROOF, M_ROOF
* Added support for the following models ...
    * Freighter
        * ABAND_BARREL - Industrial Barrel
        * ABAND_BENCH - Industrial Bench
        * ABAND_CASE - Secure Briefcase
        * ABAND_CRATE_L - Storage Unit
        * ABAND_CRATE_M - Salvage Crate
        * ABAND_CRATE_XL - Large Storage
        * ABAND_SHELF - Heavy-Duty Furniture
        * FOORLIGHT - Emergency Light
        * FOOTLOCKER - Crew Footlocker
        * HEATER - Emergency Heater
        * LOCKER2 - Crew Locker
        * MEDTUBE - Sample Container
        * PALLET - Industrial Pallet
        * PLANTTUBE - Floral Cannister


release 1.2.1
-------------

* Fixed naming of BUILDCHAIR.
* Fixed a model positioning issue with NPCFRIGTERM.
* Added snapping positions for Plants, Platers and Bioroom.
* Adjusted scaling for gold, silver and bronze statues.
* Added support for the following models ...(with help from @DevilinPixy)
    * Main
        * PANEL_GLASS
    * Decoration
        * STATUE_DIP_B
        * STATUE_DIP_S
        * STATUE_DIP_G
    * Exocraft
        * GARAGE_MECH
    * Technology
        * POWERLINE_HIDER
        * BUILDHARVESTER
    * Farming
        * TOXICPLANT
        * SNOWPLANT
        * SCORCHEDPLANT
        * SACVENOMPLANT
        * RADIOPLANT
        * POOPPLANT
        * PEARLPLANT
        * NIPPLANT
        * GRAVPLANT
        * LUSHPLANT
        * BARRENPLANT
        * CREATUREPLANT
    * Freighter
        * GARAGE_FREIGHT
        * S_CONTAINER0
        * S_CONTAINER1
        * S_CONTAINER2
        * S_CONTAINER3
        * S_CONTAINER4
        * S_CONTAINER5
        * S_CONTAINER6
        * S_CONTAINER7
        * S_CONTAINER8
        * S_CONTAINER9
    * Unlockables
        * BASE_BEAMSTONE
        * BASE_BUBBLECLUS
        * BASE_COLDPLANT1
        * BASE_COLDPLANT2
        * BASE_COLDPLANT3
        * BASE_CONTOURPOD
        * BASE_DUSTPLANT1
        * BASE_DUSTPLANT2
        * BASE_DUSTPLANT3
        * BASE_ENGINEORB
        * BASE_HOTPLANT1
        * BASE_HOTPLANT2
        * BASE_HOTPLANT3
        * BASE_HYDROPOD
        * BASE_MEDGEOMETR
        * BASE_MEDPLANT01
        * BASE_MEDPLANT02
        * BASE_MEDPLANT03
        * BASE_RADPLANT01
        * BASE_RADPLANT02
        * BASE_RADPLANT03
        * BASE_ROBOTOY
        * BASE_ROCK01
        * BASE_ROCK02
        * BASE_ROCK03
        * BASE_SHARD
        * BASE_SHELLWHITE
        * BASE_STARJOINT
        * BASE_TOXPLANT01
        * BASE_TOXPLANT02
        * BASE_TOXPLANT03
        * BASE_WEIRDCUBE
        * BASE_WPLANT1
        * BASE_WPLANT2

release 1.2.0
-------------

* Added support for the decal items.
* Added models for...
    * BUILDDECAL
    * BUILDDECAL2
    * BUILDDECALNMS
    * BUILDDECALNUM0
    * BUILDDECALNUM1
    * BUILDDECALNUM2
    * BUILDDECALNUM3
    * BUILDDECALNUM4
    * BUILDDECALNUM5
    * BUILDDECALNUM6
    * BUILDDECALNUM7
    * BUILDDECALNUM8
    * BUILDDECALNUM9
    * BUILDDECALSIMP1
    * BUILDDECALSIMP2
    * BUILDDECALSIMP3
    * BUILDDECALSIMP4
    * BUILDDECALVIS1
    * BUILDDECALVIS2
    * BUILDDECALVIS3
    * BUILDDECALVIS4
    * BUILDDECALVIS5
    * SPEC_DECAL01
    * SPEC_DECAL02
    * SPEC_DECAL03
    * SPEC_DECAL04
    * SPEC_DECAL05
    * SPEC_DECAL06
    * SPEC_DECAL07
    * SPEC_DECAL08

release 1.1.9
-------------

* Updated Add-on information for Blender 2.82
* Added missing Half Metal Arch object.
* Added missing power connection to Garage Wall items.
* Added missing power connections to Light Posts.
* Added missing power connection to Byte Beat Switch.
* Enabled message capturing on Byte Beat Switch.
* Added some snapping information to the short wall pieces.
* Improved models for...
    * BUILDLIGHT
    * BUILDLIGHT2
    * BUILDLIGHT3
    * BYTEBEATSWITCH
    * C_GDOOR
    * M_GDOOR
    * W_GDOOR
    * C_WALL_Q
    * C_WALL_Q_H
    * M_WALL_Q
    * M_WALL_Q_H
    * W_WALL_Q
    * W_WALL_Q_H

release 1.1.8
-------------

* Arranged the Tools panel into a neater and more compact layout.
* Missing object cube placeholder's are now named after the object ID in the scene.
* Added OBJ add-on as a plugin dependency.


release 1.1.7
-------------

* Added a specific "Delete" button in the tools area that safely removed Base Parts and Presets from the scene.
* BYTEBEAT machines and their configurations are now supported.
    * BYTEBEAT machines and their songs can now be saved as presets and shared with other people.
    * Example: https://djmonkeyuk.github.io/nms-base-builder-presets/Byte%20Beats
* Optimized the creation of wiring controls. Bases with lots of wiring should now load faster.
* Added models for...
    * BYTEBEAT
    * BYTEBEATSWITCH
    * L_FLOOR_Q
    * U_BYTEBEATLINE

release 1.1.6
-------------

* Fixed a rotation accuracy bug when generating presets.
* Preset files now have a time stamp applied to them to help with date sorting in the Preset Directory.
* Improved timestamp data on individual base objects.


release 1.1.5
-------------

* Added support for triangle pieces.

release 1.1.4
-------------

* Support for Blender 2.81.
* Added support for Freighter bases.
    * Added simple model parts for Freighter pieces.
    * Restricted movement of FREIGHTER_CORE, AIRLCKCONNECTOR and BRIDGECONNECTOR.
    * Freighter BaseType key detected on import and kept at export. Planet base key used as default.
    * Added snapping support for Freighter parts.
* Improved snapping information for cube parts.
* Improved snapping information for light/noise boxes.
* Updated import/export functions with new keys and values from NMS version 2.16.
* Added a "Open Preset Folder" button that opens explorer window for quick access to preset .json files.


release 1.1.3
-------------

* Added a "Get More Presets..." button that opens the directory web-page for community made presets.

release 1.1.2
-------------

* Added a 'Build Counter' to the Base Properties panel to show the total number of NMS objects in your scene.
* Fixed communication message modules forgetting messages.
* Fixed the 'X' delete preset button in the preset list.
* Apply radian rotation values when snapping objects for better accuracy.
    (which fixes some cases where small offsets were being applied to snap positions)
* Fixed an issue where objects weren't remembering their snapped partner object when they don't have matching snap points.
* Added socket model and power connection to CONTAINER objects.
* Added CONTAINER7.
* Added Infrastructure Ladder.
* Added Oscilloscope.


release 1.1.1
-------------

* Fixed preset folder creation for new users.


release 1.1.0
-------------

* General
    * Further improvements to Blender 2.8 support.
    * Vastly improved loading times for base and preset generation.
    * Added more custom warnings and error messages so the user encounters less Python trace-back errors.
    * Removed the default Blender Cube, Light and Camera when generating bases.
    * Ensured all items fit under the default "Collection" in the Outliner.
    * Fixed the transparent shader being applied to all items instead of just structural items as intended.
    * Turned off relationship lines by default.
    * Part and Preset list search bar to always be visible.
    * Base parts are now listed alphabetically in the UI list.
* Presets
    * A better control is generated, calculated from the total floor-area of the preset parts.
    * Fixed an issue where presets were not generating properly if more than one instance existed.
* Snapping
    * Snapping an object remembers which object it has previously snapped to.
    * Allows you to use the snap buttons without having to select two items at a time after the initial snap has been done.
    * Updated snap information for BUILDLANDINGPAD.
    * Swapped the selection order when snapping one object to another.
* Power
    * When selecting a point then pressing "New Point". This will automatically create a power line between the new point and the previous point.
    * Added power sockets to farm planter and mega planter.
* Models improvements for...
    * BUILDLANDINGPAD
    * GARAGE_M
    * GARAGE_SUB
    * PLANTER
    * PLANTERMEGA
* Added models for...
    * GARAGE_L
    * GARAGE_S
    * SUMMON_GARAGE
    * RACE_RAMP
    * BASE_TOYCORE
    * BASE_TOYCUBE
    * BASE_TOYSPHERE
    * U_SILO_S
    * CUBEROOF
    * BUILDGASHARVEST
    * STATUE_GEK_B
    * STATUE_GEK_S
    * STATUE_GEK_G
    * STATUE_SHIP_B
    * STATUE_SHIP_S
    * STATUE_SHIP_G
* Code refactor.
    * Restructured object and class hierarchy to something more manageable.
    * Replaced most bpy.ops methods with bpy.data methods.
    * Enhanced the caching mechanism for base part and preset retrieval.
    * Added framework to easily allow custom behavior for specific parts.
    * Categorized utility methods into their own modules.


release 1.0.0
-------------

* Updated code-base to work for Blender 2.8.
* Internal base version updated to 4. Additional save data keys added to export.
* Unlocked scale channels on all base parts as scaling is now supported. Works for ALL base parts.
    * (Use at your own risk, in-game snapping behavior becomes unreliable for base parts not intending to be scaled.)
* Added power socket details to some base part models that require electricity.
* Added a set of features for managing power and electricity.
    * Connect electrical base parts together from the new power UI panel.
    * Snap and cycle wire ends to base part connection points.
    * Divide existing wires into two, creating an additional control.
    * Split existing wires into two, creating a gap with 2 additional controls.
    * Create arbitrary control points to create more complex wire paths.
    * Quickly create logic gates and switches in the logic UI area.
* Fixed a minor matrix offset on wall snap points.
* MAINROOMCUBE and BUILDLANDINGPAD model improvements.
* Fixed and adjusted "nice name" table.
* Added models for...
    * W_GDOOR
    * M_GDOOR
    * C_GDOOR
    * W_ROOF_IC
    * M_ROOF_IC
    * C_ROOF_IC
    * U_BATTERY_S
    * U_EXTRACTOR_S
    * U_GASEXTRACTOR
    * U_GENERATOR_S
    * U_MINIPORTAL
    * CREATURE_FEED
    * CREATURE_FARM
    * COOKER
    * BUILDANTIMATTER
    * U_BIOGENERATOR
    * BUILDTABLE3
    * NOISEBOX
    * LIGHTBOX
    * U_POWERLINE
    * U_PORTALLINE
    * U_PIPELINE


release 0.9.3
-------------
* Refactored module and code structure.
* Faster loading times for bases and presets with OBJ reference cache mechanism (only imports OBJs for first load).
* Improved models for mainrooms.
* Added support for a vast amount of decoration and technology parts: WATERBUBBLE, SHIELDSTATION, HEALTHSTATION, O2_HARVESTER, DRESSING_TABLE, BUILDTERMINAL, FOUNDATION, CRATELRARE, CRATELCYLINDER, MAINROOMFRAME, SMALLLIGHT, BUILDLABLAMP, GARAGE_B, CUBEWINDOWSMALL, CUBEWINDOWOVAL, WALLSCREEN, WALLSCREENB, WALLSCREENB2, WALLFLAG1, WALLFLAG2, WALLFLAG3, WALLFAN, TECHPANEL, STORAGEPANEL, STATUE_WALK_?, STATUE_ASTRO_?, SERVERSTACK, OCTACABINET, FLOORMAT1, DRAWS, BUILDSIDEPANEL, BUILDLIGHTTABLE, BUILDHCABINET, BUILDFLATPLANEL, BUILDCANRACK, BUILDBED, BLDWALLUNIT, BASE_WPLANT3, BASE_TREE03, BASE_MEDPLANT01, BASE_MEDPLANT02, BASE_MEDPLANT03, BASE_BONEGARDEN, BASE_BARNACLE, ?_DOOR_H, ?_DOORWINDOW, ?_DOOR, ?_ARCH_H, ?_ROOF_M, ?_ROOF_C, BASE_TERRARIUM, BASE_AQUARIUM, NPCWEAPONTERM, NPCBUILDERTERM


release 0.9.2
-------------
* Added some legacy base building parts.
* New OBJs for Standing Planter, Walls, Floors, Folding Door, Corner Post.


release 0.9.1
-------------
* Added under water parts to the list.
* Added and improved snap point information and relationships.
* Improved appearance of L shape hallway pieces.
* Implemented first phase of mod support. (see readme for more details.)
* Light objects now create blender lights.
* Improved room visibility switch to display current mode.
* Added "Lighted" as an option on room visibility.


release 0.9.0
-------------
* Added colour options.
* Improved overall UI. Changed to collapsible areas and added button icons.
* Changes to snapping information.
* Added nice name mechanism to base parts.

release 0.8.0
-------------
* Improved and added various models.
* New Snapping area in the tool. With convenient Duplicate button. (Expect some items would not snap yet!)
* Items with compatible snapping will automatically snap on creation.
* Fixed a bug where the tool would disappear when no item was selected.
* Re-organised Basic parts into more granular categories (floors, stairs, walls, etc)


release 0.7.2
-------------
* Improved obj's of CUBEFLOOR, C_WALL_Q_H, BUILDPAVING and BUILDPAVING_BIG.
* Added obj for BUILDSODA2L and CUBESTAIRS.


release 0.7.0
-------------
* Added options for defining and building presets.
* Added large paving, pipe and curved pipe.


release 0.6.0
-------------
* Added a button to toggle between different room visibility. Shown, Ghost and Hidden.
* Added display support for...
    Chairs
    Locker
    Sofas
    Worktop
    Ceiling light
    Cube Inner Doors
    Cube Walls
    Large Desk
    Robotic Arm
    Shelf Panel
    Roof Monitor
    Weapon Rack
    Plant Pot
    Ladder
    Main room Window


release 0.5.0
-------------
* Initial release
For habs or the Thunderbird bay already placed in an older saved scene, select
those parts and switch to Low-Res, then back to High-Res to refresh their meshes.

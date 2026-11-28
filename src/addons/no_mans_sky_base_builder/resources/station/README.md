# Station references

BBE reads the GalacticAddress field when you import a station through Save Manager, Import Build File, or the clipboard. The system address selects the native hull, entrance tube, structural branches and exterior hull colours. Open **Outside** with its Outliner eye to inspect the hull. The exterior and the interior roof start hidden for building. Material Preview displays packed game textures on the interior cutaways and exterior hull. The system colours tint the exterior panels. To update an older station scene, use Refresh Station Materials under Station Reference, or Refresh Reference Library for a manual reference.

A station file carries its own address, so sharing a full station base export also shares its reference. For a parts-only file, choose **Station Base** under **Fallback build type** in the import dialog. An identified station with a missing or invalid address opens the manual library. Raw clipboard lists have no build type to identify them as stations.

Under **Station Reference**, **Use Manual Reference** opens the hull and module choices. **Remember Station Visibility** keeps that manual choice for the next import. **Match Station Address** restores automatic matching for an addressed station. Reference geometry stays in Blender. Game exports contain the player's placed build parts.

## Manual library and earlier versions


The reference now loads prebuilt interior cutaways and shares repeated exterior meshes. All six hull families, large-part toggles, native geometry and placement stay the same. In the local Blender 5.1.2 benchmark, reference creation dropped from 23.15 seconds to about 0.6 seconds. A saved reference dropped from 219 MB to 55 MB; stored unique vertices dropped from 10.38 million to 2.51 million. Player building-part import takes additional time and varies with the build. These changes reduce repeated geometry and preparation work; they do not decimate the visible surfaces.

After upgrading, restart Blender. For an existing station scene, click **Refresh Reference Library**, then save the blend to replace its old, larger reference data. Player parts and reference eye choices are preserved. Exterior entries use collection instances internally; keep using the same Outliner eyes. No separate geometry files are needed beside a saved blend.

Import a Station with Save Manager. The Outside collection contains all six hull families: **01 Tet, 02 Oct, 03 Disk, 04 EX, 05 Tri, 06 Simple**. Use the eye icons to turn the current family off and another one on. Expand a family to toggle its bodies, arch rings, large spheres, cylinder towers, tanks and other major modules. Keep one Body variant enabled in that family. Modules are in their authored station positions; you do not need to move them.

Outside starts hidden for interior work. When enabled, Tet is the initial family; other families start hidden, with their first body ready to show. Extra modules start hidden. Some families offer alternate sphere, hex and segmented-sphere bodies. Inside retains the existing six roof/wall/floor cutaway objects and uses one fixed round entrance corridor.

The earlier Simple file combined one selection into a single Hull object. Its exterior catalog also lost the hidden source objects' rotations and translations. Version 6.5.4 restores the authored transforms and exposes the large components separately. The original Inside geometry and player coordinates are unchanged. The old Simple files and old preview images do not show the corrected exterior.

## Large component alternatives

Version 6.5.5 keeps the verified geometry and corrects 17 display names. Oct's Upper/Lower labels become **Single/Paired**. Disk's Upper disc becomes **Vertical ring layout**. EX and Tri's complete module sets are named **All ...**.

Choose one body and one alternative at each mounting group. For Disk, the vertical-ring layout is an alternative to its upper-module/arch-ring layout. For EX and Tri, choose an All set or a mixed Upper/Lower combination. Eye controls remain independent. See **Station exterior choices.md** for the complete guide.

All 80 exterior objects were checked against their own native hull family and option branch, including every vertex and triangle. No placement correction was needed. Tet and Oct's low rings follow the native scene data. Labels were updated in the saved libraries with geometry, player transforms and visibility preserved.

## Compact collection lists

Version 6.5.7 starts station imports and reference refreshes with Station Reference and Outside expanded. The six hull-family lists, Inside, player parts and object data are collapsed. This changes the list expansion only; the eye settings, active collection and selection are preserved. Opening a saved blend keeps its saved tree layout.

## Importing your station

Save your Blender work and restart Blender after the plugin update. Use the existing **Save Manager > account/save > Station > your station > Import from Save** workflow. The reference has Station Reference > Outside / Inside, alongside the separate Station Player Parts collection.

For an already imported station, click **Refresh Reference Library** in Save Manager to replace the old reference. It preserves player parts and interior cutaway visibility. New references include all six hull groups without an entrance or model-variation dropdown. Use the Outliner eyes directly.

Eye settings are saved in the blend file. Click **Remember Station Visibility** in Save Manager to reuse those eye settings when importing that station again. This is a manual appearance profile; the save still does not supply a decoded exterior recipe. The reference does not change the in-game station.

## Geometry and checks

Exterior antennas, aerials, decals, lights, effects and small exhausts remain omitted. Fine procedural variations use a representative default; the largest structural forms remain available as separate objects. Omitted decorative protrusions are not part of the reference bounds. Native geometry keeps its size and position.

The corrected exterior was compared independently with the native XML scene hierarchy, and approach rays were checked through all 14 body variants across the six families. These checks verify the model alignment, not the game's complete flight or building restrictions. Interior geometry is static and neutral, without animated NPC bodies or game lighting.


Station Reference controls appear only while the Station tab is selected in the enabled Save Manager, below its station selection and import controls.

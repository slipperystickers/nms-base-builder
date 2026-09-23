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

# September 22, 2026 compatibility audit

Local target: Steam build 25442159, game executable version 179666.
The latest official release notes found were Cosmos 7.04, dated September 21:
https://www.nomanssky.com/2026/09/cosmos-7-04/

The fossil import failure is caused by a deleted Blender placeholder returned
from the shared deserializer. It is independent of game save-schema changes.
Version 18.0.4 corrects that object lifetime error for all import callers.

## Confirmed checks

- Saves written on September 22 decode with the bundled Save Manager, including
  base lists and ship ownership. Decode/write/decode comparisons on private
  copies preserve the full decoded document.
- The current build-object table has 2,124 IDs and the part-model table has
  1,344 IDs, with none added or removed versus the stored Cosmos baseline.
- Building globals are byte-identical to the previous local audit.
- 896 cached station scene, descriptor and entity paths remain in the game.

## Changes since the stored Cosmos baseline

These differences span the baseline-to-current interval; they are not all
attributed specifically to the September 22 download.

- Nine freighter room definitions no longer set BuildableOnSpaceStationBase:
  FRE_ROOM_FLEET, FRE_ROOM_NPCBUI, FRE_ROOM_NPCFAR, FRE_ROOM_NPCSCI,
  FRE_ROOM_NPCVEH, FRE_ROOM_NPCWEA, FRE_ROOM_SCAN, FRE_ROOM_TELEPO,
  and FRE_ROOM_VEHICL.
- PIPESHAPE and CURVEPIPESHAPE no longer set BuildableOnSpaceBase.
- SB_BEACON now sets IsPlaceableFloatingInSpace; WATERBUBBLE now sets
  BuildableOnPlanetBase.
- Freighter glass corridor styles now use FRE_A. Some doorway/connector style
  mappings gained variants. FRE_CORR_STA_B now uses the station colour palette.
- 48 cached station scene/entity/descriptor files differ in raw bytes, including
  decor, dock interiors, collision and interaction data. These include actual
  scene changes, not only compiler formatting differences. One gravity entity
  could not be decoded by the available compiler.

## Scope of this release

The model/reference library is unchanged. The import and save compatibility
checks do not establish exact visual parity of every bundled mesh, current
in-game placement permission, multiplayer behaviour, or collision. The builder
does not override the game's placement rules. A separate asset refresh and
in-game verification are needed before making those claims.

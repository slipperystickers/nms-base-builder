# Base Builder Extended

Current standalone release: **18.2.44** (Forsaken 7.10 support). Windows x64,
This release was verified with Blender 5.1.2.

Build bubble tube routes with nearby part icons, rotation controls and all eight
basic shapes. Add one new pathway at a time, redirect unused openings, and join
an elbow into the side of a straight with a T or draft +. Tube controls hide when
multiple parts are selected.

Closed sides no longer trigger false proximity warnings. Tube warnings stay
advisory so you can export and test your own designs in game. See
[release notes](release_notes.md) for details and validation limits.

Includes early Corvette warnings and reviewed keep-build repairs,
one-step export to a new ship slot, saved ship metadata, optional WASD navigation,
cockpit-order controls, restored Asset Browser layouts, faster export validation,
and opt-in diagnostic tickets. The Corvette picker closes after selection and
excludes freighters. The website diagnostic service is deployed and verified.

[Download the installer and read the release notes](https://github.com/slipperystickers/nms-base-builder/releases/tag/v18.2.44).
Install the attached plugin ZIP through Blender's **Install from Disk**, then
restart Blender. Existing Detailed Proxy users receive missing or updated packs
automatically when Blender Online Access is enabled; no fresh install is needed.
Keep Blender open until the HD progress finishes. Only changed or missing
components download, and the previous compatible pack stays usable meanwhile.
Use Detailed Proxies > Retry Download if a transfer fails.

This release adds Curve from Edges / Faces with hover previews, expanded
point-and-click snapping, a persistent Auto-Snap switch, interior cutaways,
connected hab doorways and corrected magnetic wall assemblies. See the release
notes for the complete list.

Recovery defaults to every 10 minutes, with an optional placement-count trigger.
The latest three consecutive recovery copies are kept without overwriting the
original project. The Recovery menu shows its countdown and backup status.
Version 18.1.79 also fixes group default-colour reset and checks for Charon Forge
before BBE activates. The two add-ons cannot run together; the activation prompt
lets users keep Charon or disable it and continue with BBE. Automatic update
checks remain opt-in. Keep the previous installer for rollback.

Version 18.1.80 resolves detailed-proxy texture paths before models enter the
scene, falls back to simple proxies when a shared project's detailed textures
are unavailable, and removes the hidden Asset Browser helper from the Outliner
after its window closes. The optional detailed-proxy pack is not required.

Version 18.1.81 keeps Ship Management available when existing Corvette links
are uncertain. Inventory, class, stats and hyperslot edits preserve those links
exactly; structural edits are locked only in affected contexts. Link Status
explains the issue locally without requiring users to upload their saves.

**Base Builder by DjMonkey. Extended by Furiousfurby.** Based on Kuma's 18.0.0
build; the original guides, Patreon, Discord and Steam Games links are preserved.


<p align="center" style="font-size:26px">
  <img src="https://raw.githubusercontent.com/djmonkeyuk/nms-base-builder/master/images/CommunityBadge.png" alt="No Mans Sky"  width="50%">
  <br />
A plugin for Blender to build bases in No Mans Sky.<br />
<span style="font-size:18">Community Discord: <a href="https://discord.gg/kpGVRKPn5W">https://discord.gg/kpGVRKPn5W</a></span>
</p>



<p align="center">
  <a href="#key-features">Key Features</a> â€¢
  <a href="#requirements">Requirements</a> â€¢
  <a href="#how-to-use">Guides</a> â€¢
  <a href="#credits">Credits & Support</a> â€¢
  <a href="#screenshots">Screenshots</a> â€¢
</p>

<a name="key-features"></a>
## Key Features

* Build bases for No Mans Sky using proxy representations for building parts.
* Translate, rotate and scale any base part to any position and any size!
* Define presets to build complex items quickly. Share or download presets online.
* Save and Load bases to disk (.json format).
* Import and Export back and forth from the game using the No Mans Sky Save Editor.
* Snapping features help with the placement of base parts. Similar to the snapping features in-game.
* A Power and Logic UI panel helps manage electricity and switches.
* An asset browser for searching and locating base parts.

<p align="center" style="font-size:26px">
<img src="https://djmonkey.uk/images/public/asset_browser.png" alt="No Mans Sky"  width="75%">
</p>


<a name="requirements"></a>
## Requirements

* Blender
    * https://www.blender.org
* Latest Base Builder Release
    * https://github.com/djmonkeyuk/nms-base-builder/releases
* A No Mans Sky Save Editor, you have a few options:
    * GoatFungus - https://github.com/goatfungus/NMSSaveEditor
    * NomNom - https://github.com/zencq/NomNom
    * NMSBaseJsonEditor - https://www.nexusmods.com/nomanssky/mods/3849

<br />


<a name="how-to-use"></a>

## Official Guides

For the latest and greatest guidance on installation and how to use this Blender extension, please visit the <a href="https://djmonkey.uk/no-mans-sky-base-builder-blender/guides/" target="_blank">official guide pages.</a>

<a href="https://djmonkey.uk/no-mans-sky-base-builder-blender/guides/" target="_blank"><img src="https://djmonkey.uk/images/public/blender_guide_screen_30.png" /></a>


## Preset Location

Presets are stored in your "**%USERPROFILE%\NoMansSkyBaseBuilder\presets**" directory.
These can be downloaded and shared with other people.

Visit the <a href="https://discord.gg/kpGVRKPn5W" target="_blank">Community Discord</a> where creators share their own prefabs!

## Technical Dependencies

Casual users may ignore this section. These Python dependencies are installed automatically on execution of the Asset Browser UI.

* PySide6


<a name="credits"></a>

## Credits & Support

Created and maintained by DjMonkey. You can reach out via various social media channels:

* Discord: <a href="https://discord.gg/kpGVRKPn5W">https://discord.gg/kpGVRKPn5W</a>
* Threads: <a href="https://www.threads.net/@djmonkeyuk" target="_blank">@djmonkeyuk</a>
* Twitter/X: <a href="https://www.x.com/djmonkeyuk" target="_blank">@djmonkeyuk</a>
* BlueSky: <a href="https://bsky.app/profile/djmonkeyuk.bsky.social" target="_blank">@djmonkeyuk.bsky.social</a>

## Play my Indie Game!

If you have enjoyed using my tools, consider playing my very own indie game! It is the best way you can support me!

> <i>'Tales from the Dancing Moon' is a life-sim RPG set in a parallel universe inspired by UK culture and fantasy novels. After the events of a shadow-beast invasion on a seaside town, complete villager quests and collect hidden diaries to understand your role in this mysterious character-driven story.</i>

There is a <a href="https://store.steampowered.com/app/1782420/Tales_from_The_Dancing_Moon/" target="_blank">FREE demo</a>. You would help me a lot by either wishlisting it, grabbing a copy, or even sharing it with your friends!

Click the image below to be taken to the Steam page!

<p align="center">
  <a href="https://store.steampowered.com/app/1782420/Tales_from_The_Dancing_Moon/" target="_blank"><img src="https://raw.githubusercontent.com/djmonkeyuk/nms-base-builder/master/images/SteamDemoBanner.png" alt="Tales from The Dancing Moon Steam Store Page" width="50%"></a>
</p>


<a name="screenshots"></a>
## Screenshots

<p align="center">
  <img src="https://raw.githubusercontent.com/djmonkeyuk/nms-base-builder/feature/blender2.8/images/blender_showcase.png" alt="NMS1" width="100%">
</p>

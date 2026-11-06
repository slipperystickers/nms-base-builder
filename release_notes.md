# Base Builder Extended 18.2.45

Hotfix for Windows update downloads failing with **PermissionError / WinError 5** while replacing `progress.json`.

- A locked progress file no longer aborts a download. BBE retries temporary locks, limits progress writes and continues tracking the growing ZIP.
- Final results retry temporary file locks. File-size and SHA-256 verification remain mandatory before installation.
- BBE's updater checks Blender's temporary session directory before handing over to the installer. A missing or unwritable directory produces restart instructions before BBE is disabled.

## If you are stuck on 18.2.43 or 18.2.44

The updater already running in those versions cannot benefit from this fix until you install it:

1. Turn off **Download and install automatically** for now and save your work.
2. Fully close every Blender window, then reopen Blender.
3. Download **no_mans_sky_base_builder-18.2.45.zip** below. Use **Edit > Preferences > Get Extensions > Install from Disk** to install it over BBE.
4. Restart Blender and confirm **18.2.45** in Updates & Support. You can then re-enable automatic updates.

If Blender showed `acquire(): cookie doesn't exist!` and BBE's checkbox stayed enabled while its interface disappeared, fully restarting Blender restores its session directory. If needed, uncheck and re-enable BBE after restarting. This hotfix protects BBE's updater; it does not replace Blender's own Install from Disk implementation.

**No uninstall or fresh install is required. Do not delete the HD packs.** HD content is unchanged from 18.2.44. Existing HD owners still receive missing or updated components automatically with Blender Online Access enabled.

Verified on Windows with real file-sharing locks, checksum rejection tests, and native Blender 5.1.2 installation/recovery tests. Blender 5.2.3 was reported by the affected user but is not locally runtime-verified.

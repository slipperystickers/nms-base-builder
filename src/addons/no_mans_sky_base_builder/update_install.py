"""Install verified updates through Blender's own package manager."""
from pathlib import Path
import hashlib, json, zipfile

def validate_archive(path, result, product, blender_version):
    asset=result['asset']
    path=Path(path)
    if path.stat().st_size != asset['size']:
        raise ValueError('Installer size changed after download')
    with path.open('rb') as f:
        if hashlib.file_digest(f,'sha256').hexdigest() != asset['digest'].split(':',1)[1].lower():
            raise ValueError('Installer checksum changed after download')
    with zipfile.ZipFile(path) as archive:
        names=archive.namelist()
        if any(n.startswith(('/', '\\')) or '..' in n.replace('\\','/').split('/') or ':' in n for n in names):
            raise ValueError('Unsafe installer path')
        if product=='bbe':
            import tomllib
            manifest=tomllib.loads(archive.read('blender_manifest.toml').decode())
            if manifest['id']!='no_mans_sky_base_builder' or manifest['version']!=result['version']:
                raise ValueError('Installer identity differs from the release')
            minimum=tuple(map(int,manifest['blender_version_min'].split('.')))
            if tuple(blender_version)<minimum:
                raise ValueError('This update requires Blender '+manifest['blender_version_min'])
        else:
            import ast
            tree=ast.parse(archive.read('nms_text_generator/__init__.py').decode('utf-8'))
            info=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
                      and any(isinstance(t,ast.Name) and t.id=='bl_info' for t in n.targets))
            if '.'.join(map(str,info['version'])) != result['version']:
                raise ValueError('NMScribe version differs from the release')
            if tuple(blender_version)<tuple(info['blender']):
                raise ValueError('This NMScribe update needs a newer Blender version')
    return str(path.resolve())

def check_extension_session():
    """Check Blender's lock cookie before its installer disables the add-on."""
    import bpy
    import tempfile
    directory = bpy.app.tempdir
    if not directory or not Path(directory).is_dir():
        raise RuntimeError('Blender\'s temporary session folder is missing. Save your work, '
                           'close every Blender window, reopen Blender, and retry. '
                           'BBE has not been disabled or replaced.')
    try:
        with tempfile.TemporaryFile(dir=directory):
            pass
    except OSError as exc:
        raise RuntimeError('Blender cannot write to its temporary session folder. '
                           'Save your work, restart Blender, and retry. '
                           'BBE has not been disabled or replaced.') from exc


def install(path, package):
    import bpy
    if package.startswith('bl_ext.'):
        check_extension_session()
        repo=package.split('.')[1]
        result=bpy.ops.extensions.package_install_files('EXEC_DEFAULT',filepath=path,repo=repo,enable_on_install=True)
    else:
        import addon_utils,sys
        addon_utils.disable(package,default_set=False)
        try:
            result=bpy.ops.preferences.addon_install('EXEC_DEFAULT',filepath=path,overwrite=True)
            if result != {'FINISHED'}:
                raise RuntimeError('Blender could not install the update')
        finally:
            # Reload submodules too; reloading only __init__ mixes releases.
            for name in list(sys.modules):
                if name == package or name.startswith(package+'.'):
                    del sys.modules[name]
            addon_utils.modules(refresh=True)
            if addon_utils.enable(package,default_set=True) is None:
                raise RuntimeError('The updated add-on could not be enabled; restart Blender and check Updates & Support')
    if result != {'FINISHED'}:
        raise RuntimeError('Blender could not install the update')
    import sys
    loaded = sys.modules.get(package)
    if loaded is None or (package.endswith('no_mans_sky_base_builder')
                          and not getattr(loaded, '_core_registered', False)):
        raise RuntimeError('The update was extracted but could not start; restart Blender and review the add-on error')
    # Blender can return FINISHED even when its extension worker reports an
    # extraction failure. Verify the installed payload before claiming success.
    root = Path(loaded.__file__).resolve().parent
    with zipfile.ZipFile(path) as archive:
        prefix = '' if package.startswith('bl_ext.') else package + '/'
        for entry in archive.infolist():
            if entry.is_dir() or not entry.filename.startswith(prefix):
                continue
            relative = entry.filename[len(prefix):]
            if not relative.endswith(('.py', '.toml')):
                continue
            installed = root / relative
            if not installed.is_file() or installed.read_bytes() != archive.read(entry):
                raise RuntimeError('Blender did not replace all update files; restart Blender and retry the update')
    bpy.ops.wm.save_userpref()

_pending = None
_parked = []
_wake_timers = []


def _browser_modules():
    import sys
    return [module for name, module in tuple(sys.modules.items())
            if name.endswith(('.tools.asset_browser_grid', '.tools.asset_browser_sidebar'))
            and 'no_mans_sky_base_builder' in name and hasattr(module, '_sessions')]


def wait_reason():
    import bpy
    wm = bpy.context.window_manager
    if wm is None or wm.is_interface_locked:
        return 'Waiting for Blender to finish its current operation.'
    if bpy.context.mode != 'OBJECT':
        return 'Waiting for Object Mode to install the update.'
    if bpy.app.is_job_running('RENDER'):
        return 'Waiting for the render to finish.'
    idle = {'BBE_OT_asset_grid', 'BBE_OT_sidebar_asset_grid',
            'bbe.asset_grid', 'bbe.sidebar_asset_grid'}
    for module in _browser_modules():
        if not module._enabled:
            continue  # Paused modal operators may already have invalid RNA.
        if any(getattr(s, '_drag', False) or getattr(s, '_pressed', None)
               for s in module._sessions.values()):
            return 'Waiting for the Asset Browser interaction to finish.'
    for window in wm.windows:
        for op in getattr(window, 'modal_operators', ()):
            if op.bl_idname not in idle:
                return 'Waiting for the current edit or dialog to finish.'
    return ''


def _pause_browsers():
    import bpy
    for module in _browser_modules():
        if module._enabled:
            _parked.append(module)
            module._enabled = False
            module._close_all()  # Remove draw handlers before their RNA expires.
    wm = bpy.context.window_manager
    if _parked:
        for window in wm.windows:
            _wake_timers.append(wm.event_timer_add(.1, window=window))
    # A temporary event wakes each window so paused modal handlers can exit.


def _resume_browsers():
    import bpy
    while _wake_timers:
        try:bpy.context.window_manager.event_timer_remove(_wake_timers.pop())
        except ReferenceError:pass
    while _parked:
        module = _parked.pop()
        # On successful replacement these old modules are no longer registered.
        cls = getattr(module, 'BBE_OT_sidebar_asset_grid',
                      getattr(module, 'BBE_OT_asset_grid', None))
        if cls is None or not getattr(cls, 'is_registered', False):
            continue
        module._close_all()
        module._enabled = True
        timer = getattr(module, '_restore', getattr(module, '_cleanup_closed', None))
        if timer and not bpy.app.timers.is_registered(timer):
            bpy.app.timers.register(timer, first_interval=.1, persistent=True)


def cancel_pending():
    global _pending
    import bpy
    if _pending and bpy.app.timers.is_registered(_pending):
        bpy.app.timers.unregister(_pending)
    _pending = None
    _resume_browsers()


def advance(client, package):
    """Called on the main thread; defer replacing code during user operations."""
    global _pending
    import bpy
    if bpy.app.background or client.busy or _pending:
        return
    if client.downloaded:
        token = str(client.downloaded)
        if getattr(client, '_install_attempt', None) == token:
            return
        reason = wait_reason()
        if reason:
            client.message = 'Update downloaded. ' + reason
            return
        client._install_attempt = token
        try:
            path = validate_archive(client.downloaded, client.result, client.product, bpy.app.version)
        except Exception as exc:
            client.message = 'Update was not installed: ' + str(exc)
            return
        client.message = 'Installing update…'
        _pause_browsers()
        def apply():
            global _pending
            reason = wait_reason()
            if reason:
                client.message = 'Update downloaded. ' + reason
                return 1.0
            wm = bpy.context.window_manager
            if any(getattr(w, 'modal_operators', ()) for w in wm.windows):
                return .25  # Let paused browser handlers exit before unregister.
            _pending = None
            try:
                install(path, package)
                _installation_message(client, package, 'Updated to ' + client.result['version'] + '.')
            except Exception as exc:
                _installation_message(client, package, 'Update installation failed: ' + str(exc))
            finally:
                _resume_browsers()
            return None
        _pending = apply
        bpy.app.timers.register(apply, first_interval=.25, persistent=True)
    elif (bpy.app.online_access and client.settings.get('auto_check', False)
          and (client.result or {}).get('available')
          and getattr(client, '_auto_download_attempt', None) != client.result['version']):
        client._auto_download_attempt = client.result['version']
        client.start('download')


def _installation_message(client, package, message):
    import sys
    client.message = message
    # Installation reloads the UI module and replaces its client object.
    ui = sys.modules.get(package + '.release_updates')
    current = getattr(ui, '_client', None)
    if current is not None:
        current.message = message
    print(message, flush=True)

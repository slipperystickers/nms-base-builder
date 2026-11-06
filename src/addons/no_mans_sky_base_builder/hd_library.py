"""Persistent, verified HD asset packs. No Blender API calls in worker threads."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import threading
import urllib.request
import zipfile
from functools import lru_cache

ADDON = Path(__file__).resolve().parent
STATE = {"busy": False, "message": "", "progress": 0.0, "error": "", "result": None}
CANCEL = threading.Event()
_PROGRESS = threading.local()


def _progress(message, progress):
    offset, span = getattr(_PROGRESS, 'segment', (0.0, 1.0))
    STATE.update(message=message, progress=offset + span * progress)


def specification():
    path = ADDON / "resources/hd_library.json"
    stat = path.stat()
    return _read_specification(path, stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=4)
def _read_specification(path, modified_ns, size):
    # Updating the add-on while Blender is open must not leave detection
    # comparing the installed pack with an obsolete cached manifest.
    return json.loads(path.read_text(encoding="utf-8"))


def storage():
    override = os.environ.get("BBE_ASSET_LIBRARY_ROOT")
    return Path(override) if override else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "BaseBuilderExtended" / "asset-libraries"


def installed_root():
    spec = specification()
    root = storage() / spec["id"]
    try:
        receipt = json.loads((root / "installed.json").read_text(encoding="utf-8"))
        if (not receipt.get('removing') and receipt.get("id") == spec["id"] and receipt.get("content_sha256") == spec["content_sha256"]
                and (root / "assets").is_dir() and (root / "textures").is_dir()):
            return root
    except (OSError, ValueError):
        pass
    return None


def library_root():
    root = installed_root()
    if root:
        return root
    # Existing full installations remain usable until migrated before updating.
    bundled = ADDON / "models-high-res"
    return bundled if (bundled / "assets").is_dir() else None


def available():
    return library_root() is not None


def has_installed_content():
    """Recognise previous HD owners across add-on updates and reinstalls.

    An old pack is evidence that the user installed Detailed Proxies, not
    evidence that its assets satisfy the current manifest.
    """
    if available():
        return True
    try:
        for path in storage().glob('hd-*/installed.json'):
            try:
                receipt = json.loads(path.read_text(encoding='utf-8'))
                if (receipt.get('id') == path.parent.name
                        and receipt.get('content_sha256') and not receipt.get('removing')):
                    return True
            except (OSError, ValueError):
                continue
    except OSError:
        pass
    return False


def content_version():
    """All separately downloaded components form one user-facing HD pack."""
    return tuple((spec['id'], spec['content_sha256']) for spec in
                 (specification(), scenes_specification(), additions_specification(),
                  characters_specification()))


@lru_cache(maxsize=4)
def _texture_names(pack_id, content_sha256):
    """Index verified texture names once, including during a bulk proxy switch."""
    spec = specification()
    return {name.casefold(): name for name in spec['files']
            if name.startswith('textures/')}


def relink_texture_images(images=None):
    """Resolve BBE texture references against this machine's HD library.

    Appended assets carry the library builder's paths. Shared projects instead
    carry their author's downloaded-pack paths, including their user folder.
    Recognise both layouts and require an exact manifest-relative filename;
    unrelated user textures and packed images must keep their own content.
    """
    root = library_root()
    if images is None:
        import bpy
        images = bpy.data.images
    from . import pilot_reference, character_references
    if root is None:
        return pilot_reference.relink_texture_images(images) + character_references.relink_texture_images(images)
    spec = specification()
    known = _texture_names(spec['id'], spec['content_sha256'])
    changed = 0
    additions = None
    additions_checked = False
    # The pack ID also covers a custom BBE_ASSET_LIBRARY_ROOT on another PC.
    markers = ('/models-high-res/textures/', '/' + spec['id'].casefold() + '/textures/')
    for image in images:
        if image.source != 'FILE' or image.packed_file:
            continue
        native_texture = image.get('bbe_native_texture')
        if isinstance(native_texture, str) and Path(native_texture).name == native_texture:
            if not additions_checked:
                additions = additions_root()
                additions_checked = True
            if additions is None:
                continue
            target = additions / 'textures' / native_texture
            # Saved scenes from the PNG additions pack use the same native
            # texture identity; the prepared HD pack stores it as WebP.
            if not target.is_file() and target.suffix.lower() == '.png':
                target = target.with_suffix('.webp')
            if target.is_file():
                if image.filepath != str(target):
                    image.filepath = str(target)
                    image.reload()
                    changed += 1
                continue
        path = '/' + image.filepath.replace('\\', '/').lstrip('/')
        lower_path = path.casefold()
        relative = None
        for marker in markers:
            if marker in lower_path:
                suffix = path[lower_path.index(marker) + len(marker):]
                relative = known.get(('textures/' + suffix).casefold())
                break
        if relative is None:
            continue
        target = root / relative
        if target.is_file() and image.filepath != str(target):
            image.filepath = str(target)
            image.reload()
            changed += 1
    return changed + pilot_reference.relink_texture_images(images) + character_references.relink_texture_images(images)


def scenes_specification():
    path = ADDON / 'resources/hd_scenes.json'
    info = path.stat()
    return _read_specification(path, info.st_mtime_ns, info.st_size)


def scenes_root():
    spec = scenes_specification()
    root = storage() / spec['id']
    try:
        receipt = json.loads((root / 'installed.json').read_text(encoding='utf-8'))
        if (not receipt.get('removing') and receipt.get('id') == spec['id']
                and receipt.get('content_sha256') == spec['content_sha256']
                and all((root / name).is_file() for name in spec['files'])):
            return root
    except (OSError, ValueError):
        pass
    return None


def ready():
    return (available() and scenes_root() is not None and additions_root(allow_previous=False) is not None
            and characters_root() is not None)


def characters_specification():
    path = ADDON / 'resources/hd_characters.json'
    info = path.stat()
    return _read_specification(path, info.st_mtime_ns, info.st_size)


def characters_root():
    """Separate, optional character download; independent of the ship HD assets."""
    spec = characters_specification()
    root = storage() / spec['id']
    try:
        receipt = json.loads((root / 'installed.json').read_text(encoding='utf-8'))
        if (not receipt.get('removing') and receipt.get('id') == spec['id']
                and receipt.get('content_sha256') == spec['content_sha256']
                and all((root / name).is_file() for name in spec['files'])):
            return root
    except (OSError, ValueError):
        pass
    bundled = ADDON / 'resources/hd_additions'
    return bundled if all((bundled / name).is_file() for name in spec['files']) else None


def additions_specification():
    path = ADDON / 'resources/hd_additions.json'
    info = path.stat()
    return _read_specification(path, info.st_mtime_ns, info.st_size)


def additions_root(*, allow_previous=True):
    spec = additions_specification()
    candidates = [spec]
    if allow_previous:
        # Only explicitly reviewed compatible packs may bridge an add-on update.
        # A new manifest must not replace a working HD preview with a base mesh
        # merely because its separate replacement download is not installed yet.
        candidates.extend(spec.get('compatible_previous', []))
    for candidate in candidates:
        root = storage() / candidate['id']
        try:
            receipt = json.loads((root / 'installed.json').read_text(encoding='utf-8'))
            if (receipt.get('content_sha256') == candidate['content_sha256']
                    and receipt.get('id') == candidate['id'] and not receipt.get('removing')
                    and (root / 'assets').is_dir() and (root / 'textures').is_dir()):
                return root
        except (OSError, ValueError):
            pass
    # Source checkouts and older full installations remain usable.
    bundled = ADDON / 'resources/hd_additions'
    return bundled if (bundled / 'assets').is_dir() else None


def pending_specs():
    result = [] if available() else [specification()]
    if scenes_root() is None:
        result.append(scenes_specification())
    if additions_root(allow_previous=False) is None:
        result.append(additions_specification())
    if characters_root() is None:
        result.append(characters_specification())
    return result


def removable_root():
    """Only the managed downloaded pack may be removed, never bundled assets."""
    if STATE['busy']:
        return None
    spec = specification()
    root = storage() / spec['id']
    try:
        receipt = json.loads((root / 'installed.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    if receipt.get('id') != spec['id'] or receipt.get('content_sha256') != spec['content_sha256']:
        return None
    parent = storage().resolve()
    if root.resolve().parent != parent or root.name != specification()['id']:
        raise ValueError('The HD pack is outside its managed library folder.')
    return root


def remove_installed(expected_root):
    root = removable_root()
    if root is None or root.resolve() != Path(expected_root).resolve():
        raise ValueError('The HD library changed. Please open Delete HD Pack again.')
    # Validate the entire tree before deletion: junctions/symlinks must never
    # turn this operation into a recursive deletion outside the managed pack.
    packs = [(root, specification())]
    additions = additions_specification()
    extras = [scenes_specification(), additions, characters_specification()]
    extras.extend(additions.get('compatible_previous', []))
    for extra in extras:
        extra_root = storage() / extra['id']
        if extra_root.exists():
            if extra_root.resolve().parent != storage().resolve():
                raise ValueError('An HD component is outside its managed library folder.')
            receipt = json.loads((extra_root / 'installed.json').read_text(encoding='utf-8'))
            if receipt.get('id') != extra['id'] or receipt.get('content_sha256') != extra['content_sha256']:
                raise ValueError('An HD component changed. Nothing was deleted.')
            packs.insert(0, (extra_root, extra))
    # Validate all components before deleting either one.
    for pack_root, pack_spec in packs:
        allowed = set(pack_spec['files']) | {'installed.json'}
        for directory, folders, files in os.walk(pack_root, followlinks=False):
            for path in [Path(directory)] + [Path(directory) / n for n in folders + files]:
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                    raise ValueError('The HD pack contains a linked path; nothing was deleted.')
                if path.is_file() and path.relative_to(pack_root).as_posix() not in allowed:
                    raise ValueError('The HD pack contains extra files; nothing was deleted.')
    # Invalidate detection first, including if an OS file lock prevents cleanup.
    for root, spec in packs:
        marker = dict(id=spec['id'], content_sha256=spec['content_sha256'], removing=True)
        (root / 'installed.json').write_text(json.dumps(marker), encoding='utf-8')
        try:
            shutil.rmtree(root)
        except OSError:
            if root.exists():
                (root / 'installed.json').write_text(json.dumps(marker), encoding='utf-8')
            raise
    CANCEL.clear()
    STATE.update(busy=False, message='HD pack deleted. Detailed Proxies can download it again.',
                 progress=0.0, error='', result=None)


def _check_cancel():
    if CANCEL.is_set():
        raise InterruptedError("HD library installation cancelled. Your previous library is unchanged.")


def _hash(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _safe_name(name):
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or "\\" in name or ":" in name:
        raise ValueError("Unsafe path in HD library archive")
    return p.as_posix()


def install_archive(archive, spec=None, *, downloaded=False):
    """Verify every payload file in staging, then publish an immutable library.

    Bundled manifests pin the pack independently of the add-on version. Invalid
    or interrupted installs never replace the currently installed library.
    """
    spec = spec or specification()
    root = storage()
    root.mkdir(parents=True, exist_ok=True)
    target = root / spec["id"]
    if shutil.disk_usage(root).free < sum(f["bytes"] for f in spec["files"].values()) + 64 * 1024 * 1024:
        raise OSError("Not enough free disk space to install the HD library.")
    verify_start, verify_span = (0.75, 0.10) if downloaded else (0.0, 0.25)
    install_start = verify_start + verify_span
    digest = hashlib.sha256()
    total = Path(archive).stat().st_size
    processed = 0
    with open(archive, 'rb') as stream:
        while block := stream.read(1024 * 1024):
            _check_cancel()
            digest.update(block)
            processed += len(block)
            _progress(message="Checking download: %.0f%%" % (100 * processed / max(total, 1)),
                         progress=verify_start + verify_span * processed / max(total, 1))
    archive_hash = digest.hexdigest()
    if archive_hash not in spec["archives"]:
        raise ValueError("This ZIP is not a verified HD library for this BBE version.")
    prefix = spec["archives"][archive_hash].get("prefix", "")
    files = spec["files"]
    staging = Path(tempfile.mkdtemp(prefix=".install-", dir=root))
    try:
        with zipfile.ZipFile(archive) as z:
            names = [_safe_name(i.filename) for i in z.infolist()]
            if len(names) != len(set(names)):
                raise ValueError("Duplicate archive paths")
            for index, (name, expected) in enumerate(files.items()):
                _check_cancel()
                _safe_name(name)
                info = z.getinfo(prefix + name)
                if info.file_size != expected["bytes"]:
                    raise ValueError("Wrong file size: " + name)
                dest = staging / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                with z.open(info) as src, dest.open("wb") as dst:
                    while block := src.read(1024 * 1024):
                        _check_cancel()
                        digest.update(block)
                        dst.write(block)
                if digest.hexdigest() != expected["sha256"]:
                    raise ValueError("Checksum mismatch: " + name)
                _progress(message="Installing models: %d / %d files" % (index + 1, len(files)),
                             progress=install_start + (1 - install_start) * (index + 1) / len(files))
        (staging / "installed.json").write_text(json.dumps({"id": spec["id"], "content_sha256": spec["content_sha256"]}), encoding="utf-8")
        _check_cancel()
        # A second Blender process may have finished this exact pack meanwhile.
        if target.exists():
            if all((target / n).is_file() and _hash(target / n) == f["sha256"] for n, f in files.items()):
                (target / "installed.json").write_text((staging / "installed.json").read_text(), encoding="utf-8")
                return target
            raise ValueError("An incomplete library occupies this location. Choose another library folder or move it aside before retrying: " + str(target))
        staging.rename(target)
        return target
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def download_and_install(spec=None):
    spec = spec or specification()
    root = storage()
    root.mkdir(parents=True, exist_ok=True)
    needed = spec["download_bytes"] + sum(f["bytes"] for f in spec["files"].values()) + 64 * 1024 * 1024
    if shutil.disk_usage(root).free < needed:
        raise OSError("Not enough free disk space for the download and installed HD library.")
    fd, name = tempfile.mkstemp(prefix=".download-", suffix=".zip", dir=root)
    os.close(fd)
    try:
        request = urllib.request.Request(spec["url"], headers={"User-Agent": "BaseBuilderExtended-HD"})
        with urllib.request.urlopen(request, timeout=45) as response, open(name, "wb") as dst:
            size = int(response.headers.get("Content-Length", 0))
            received = 0
            while block := response.read(1024 * 1024):
                _check_cancel()
                received += len(block)
                if received > spec["download_bytes"]:
                    raise ValueError("Download exceeds the expected HD library size")
                dst.write(block)
                _progress(message="Downloading: %.0f / %.0f MB" % (received / 1e6, spec["download_bytes"] / 1e6),
                             progress=0.75 * received / spec["download_bytes"])
        if received != spec["download_bytes"]:
            raise ValueError("The HD download was incomplete. Please retry.")
        return install_archive(name, spec, downloaded=True)
    finally:
        Path(name).unlink(missing_ok=True)


def start(archive=None):
    if STATE["busy"]:
        return False
    CANCEL.clear()
    STATE.update(busy=True, message="Preparing detailed models…", progress=0.0, error="", result=None)

    def worker():
        try:
            if archive:
                digest = _hash(archive)
                spec = next((s for s in (specification(), scenes_specification(), additions_specification(), characters_specification()) if digest in s['archives']), None)
                if spec is None:
                    raise ValueError('This ZIP is not a verified HD library component.')
                install_archive(archive, spec)
            else:
                pending = pending_specs()
                total = sum(s['download_bytes'] for s in pending) or 1
                offset = 0
                for spec in pending:
                    _check_cancel()
                    _PROGRESS.segment = (offset / total, spec['download_bytes'] / total)
                    download_and_install(spec)
                    offset += spec['download_bytes']
            complete = ready()
            STATE.update(message='Detailed Proxy pack is up to date.' if complete else
                         'HD update incomplete. Click Detailed Proxies to finish updating.',
                         progress=1.0, result='installed' if complete else 'partial')
        except InterruptedError:
            STATE.update(message="Download cancelled.", error="", result="cancelled")
        except Exception as exc:
            models_installed = available()
            STATE.update(message="HD update incomplete. Retry from Detailed Proxies."
                         if models_installed else "Detailed models were not installed.",
                         error=str(exc), result="partial" if models_installed else "failed")
        finally:
            _PROGRESS.segment = (0.0, 1.0)
            STATE["busy"] = False
    threading.Thread(target=worker, name="BBE HD library", daemon=True).start()
    return True

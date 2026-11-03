"""One guarded transaction for plain Steam account data and save unlocks.

Current NMSE writes accountdata.hg as JSON+NUL with writeMeta=False:
https://github.com/vectorcmdr/NMSE (UI/MainForm.cs, IO/MetaFileWriter.cs).
An optional mf_accountdata.hg is watched, backed up and preserved byte-for-byte.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from contextlib import nullcontext
from datetime import datetime
def decode_account(data):
    try:
        root = json.loads(data.rstrip(b'\x00').decode('utf-8-sig'))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError('Only plain Steam account JSON is supported') from exc
    if not isinstance(root, dict):
        raise ValueError('Unsupported account JSON root')
    return root


def read_account(folder):
    folder = Path(folder).resolve()
    path = folder / 'accountdata.hg'; meta = folder / 'mf_accountdata.hg'
    if not path.is_file():
        raise ValueError('This account has no plain accountdata.hg file')
    data = path.read_bytes(); metadata = meta.read_bytes() if meta.is_file() else None
    root = decode_account(data)
    expected = {str(path): hashlib.sha256(data).hexdigest()}
    if metadata is not None:
        expected[str(meta)] = hashlib.sha256(metadata).hexdigest()
    if meta.exists() != (metadata is not None) or any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest for p, digest in expected.items()):
        raise ValueError('Account files changed while opening the review')
    return dict(path=str(path), root=root, hashes=expected, metadata_exists=metadata is not None, mode='plain_json')


def _snapshot(originals, account_folder):
    from . import backup_policy
    identity = hashlib.sha256(str(account_folder).casefold().encode('utf-8')).hexdigest()[:10]
    parent = backup_policy.root_directory() / 'Game Accounts' / f'{account_folder.name}-{identity}'
    generation = parent / (datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '_buildable-unlocks')
    generation.mkdir(parents=True)
    records = {}
    for path, data in originals.items():
        target = generation / path.name
        with target.open('xb') as stream:
            stream.write(data)
        digest = hashlib.sha256(data).hexdigest()
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError('Account backup verification failed')
        records[path.name] = dict(source=str(path), sha256=digest)
    (generation / '.bbe-backup.json').write_text(json.dumps(dict(schema=1, reason='buildable-unlocks', files=records), indent=2), encoding='utf-8')
    return generation, [str(generation / name) for name in records]


def commit_bundle(save_roots, account, account_root, expected, progress=None):
    """Back up and publish the reviewed account + save points as one unit.

    On an in-process publication failure, restore every already-replaced file
    from its exact original bytes. Interrupted processes retain full backups.
    """
    from . import ship_files, backup_policy
    from .save_file import SaveFile
    from .optimizer_export import replace_file
    from .. import progress_ui
    account_path = Path(account['path']).resolve()
    folder = account_path.parent
    paths = {Path(p).resolve(): root for p, root in save_roots.items()}
    expected = {str(Path(p).resolve()): digest for p, digest in expected.items()}
    allowed = {account_path}
    account_meta = account_path.with_name('mf_accountdata.hg')
    if account.get('metadata_exists'):
        allowed.add(account_meta)
    allowed.update(paths)
    allowed.update(p.with_name('mf_' + p.name) for p in paths if p.with_name('mf_' + p.name).exists())
    if any(p.parent != folder for p in allowed) or not all(str(p) in expected for p in allowed):
        raise ValueError('Every transaction destination must belong to the reviewed account')
    staged, replaced, temporary = [], [], []
    timestamp = int(time.time())
    def stage(path, data):
        fd, name = tempfile.mkstemp(prefix='.bbe-unlock-', dir=folder)
        temp = Path(name); temporary.append(temp)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        if temp.read_bytes() != data:
            raise ValueError('Unlock staging verification failed')
        os.utime(temp, (timestamp, timestamp))
        staged.append((path, temp))
    with (nullcontext(progress) if progress is not None else
          progress_ui.Activity('Saving items and balances')) as progress:
        try:
            progress.update(.02, 'Checking reviewed save and account files')
            if account_meta.exists() != account.get('metadata_exists', False):
                raise ValueError('Optional account metadata changed since review')
            if ship_files.hashes(expected) != expected:
                raise ValueError('Save or account changed since review; reopen Account Item Unlock and Currency Modify')
            originals = {Path(p): Path(p).read_bytes() for p in expected}
            stats = {p: p.stat() for p in originals}
            if decode_account(originals[account_path]) != account['root']:
                raise ValueError('Account data changed since review')
            progress.update(.15, 'Encoding reviewed unlocks')
            for index, (path, root) in enumerate(paths.items()):
                progress.update(.15 + .38 * index / max(1, len(paths)),
                                f'Encoding and verifying {path.name}')
                fd, name = tempfile.mkstemp(prefix='.bbe-unlock-encode-', dir=folder); os.close(fd)
                temp = Path(name); temporary.append(temp)
                save = SaveFile(temp); save.json_data = root; save.save()
                if SaveFile(temp).load() != root:
                    raise ValueError('Save unlock round-trip verification failed')
                encoded = temp.read_bytes(); stage(path, encoded)
                meta = path.with_name('mf_' + path.name)
                if meta in originals:
                    decoded_size = len(json.dumps(root, separators=(',', ':'), ensure_ascii=False).encode('utf-8')) + 1
                    stage(meta, ship_files.steam_metadata.rebuild(originals[meta], path.name, path.name, len(encoded), decoded_size, timestamp=timestamp))
            if account_root != account['root']:
                progress.update(.55, 'Preparing account rewards')
                encoded = json.dumps(account_root, separators=(',', ':'), ensure_ascii=False).encode('utf-8') + b'\x00'
                if decode_account(encoded) != account_root:
                    raise ValueError('Account unlock round-trip verification failed')
                stage(account_path, encoded)
            if not staged:
                raise ValueError('No reviewed unlock changes to publish')
            progress.update(.6, 'Creating verified account and save backups')
            generation, backups = _snapshot(originals, folder)
            progress.update(.76, 'Checking source files again')
            if account_meta.exists() != account.get('metadata_exists', False) or ship_files.hashes(expected) != expected:
                raise ValueError('Save or account changed during preparation; nothing was written')
            for index, (path, temp) in enumerate(staged):
                progress.update(.82 + .14 * index / max(1, len(staged)),
                                f'Writing {path.name}')
                replace_file(temp, path); replaced.append(path)
            backup_policy.finish(generation)
            progress.update(1., 'Items and balances saved with verified backups')
            return backups
        except Exception:
            for path in reversed(replaced):
                fd, name = tempfile.mkstemp(prefix='.bbe-unlock-restore-', dir=folder)
                temp = Path(name); temporary.append(temp)
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(originals[path])
                os.utime(temp, ns=(stats[path].st_atime_ns, stats[path].st_mtime_ns))
                replace_file(temp, path)
            raise
        finally:
            for temp in temporary:
                if temp.exists(): temp.unlink()

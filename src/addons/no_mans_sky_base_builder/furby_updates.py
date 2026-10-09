"""Shared, dependency-free release checks and verified downloads.

Downloads are staged outside application/profile folders. Never installs,
executes, extracts an archive, or changes a game installation.
"""
import hashlib
import json
import os
import queue
import re
import threading
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

PRODUCTS = {
    'fff': ('FurbysFunFeatures', r'Furbys-Fun-Features-Mod-Deck-[0-9.]+-Windows-Portable\.zip'),
    'bbe': ('nms-base-builder', r'no_mans_sky_base_builder-[0-9.]+[^/]*\.zip'),
    'nmscribe': ('nms-text-generator', r'NMS_Text_Generator_[0-9.]+\.zip'),
}

def version_tuple(value):
    match = re.search(r'(?<!\d)(\d+)\.(\d+)\.(\d+)(?!\d)', str(value))
    if not match:
        raise ValueError('Release does not have a recognizable version')
    return tuple(map(int, match.groups()))

def check_release(product, installed, opener=urlopen):
    repo, pattern = PRODUCTS[product]
    url = f'https://api.github.com/repos/slipperystickers/{repo}/releases/latest'
    request = Request(url, headers={'User-Agent': 'FuriousFurby-App-Updates', 'Accept': 'application/vnd.github+json'})
    try:
        with opener(request, timeout=15) as response:
            data = json.loads(response.read(2_000_001))
    except HTTPError as exc:
        if exc.code == 404:
            return {'message': 'No public release is available yet.', 'available': False}
        raise
    if data.get('draft') or data.get('prerelease'):
        raise ValueError('This is not a stable public release')
    latest = version_tuple(data['tag_name'])
    current = version_tuple(installed)
    eligible = [a for a in data.get('assets', []) if re.fullmatch(pattern, a['name'])
                and 'hotfix' not in a['name'].lower() and 'patch' not in a['name'].lower()]
    if latest <= current:
        return {'message': ('You have the latest public version.' if latest == current else 'Your local version is newer than the public release.'),
                'available': False, 'version': '.'.join(map(str, latest))}
    if len(eligible) != 1:
        raise ValueError('Release has no unambiguous complete installer ZIP')
    asset = eligible[0]
    if version_tuple(asset['name']) != latest:
        raise ValueError('Installer version differs from the release tag')
    digest = str(asset.get('digest', ''))
    if not re.fullmatch(r'sha256:[a-fA-F0-9]{64}', digest):
        raise ValueError('This release has no SHA-256 digest; verified download is unavailable')
    expected = f'/slipperystickers/{repo}/releases/download/'
    parsed = urlparse(asset['browser_download_url'])
    if parsed.scheme != 'https' or parsed.netloc != 'github.com' or not parsed.path.startswith(expected):
        raise ValueError('Download does not belong to the official repository')
    if '/' in asset['name'] or '\\' in asset['name'] or not (0 < asset['size'] <= 3_000_000_000):
        raise ValueError('Invalid installer filename or size')
    return {'message': f"Version {'.'.join(map(str,latest))} is available.", 'available': True,
            'asset': asset, 'version': '.'.join(map(str, latest))}

def download_release(result, destination, cancel=None, progress=None, opener=urlopen, staging_token=None):
    if not result.get('available'):
        raise ValueError('There is no newer release to download')
    asset = result['asset']
    # A result must be obtained by check_release, not deserialized from user input.
    name = asset['name']
    if Path(name).name != name or '/' in name or '\\' in name:
        raise ValueError('Invalid filename')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / name
    expected = asset['digest'].split(':', 1)[1].lower()
    if target.exists():
        with target.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() == expected:
                return target
        raise ValueError('A different file already has this name; choose another download folder')
    token = staging_token or os.urandom(6).hex()
    if not re.fullmatch(r'[a-f0-9]{12}',token):raise ValueError('Invalid staging token')
    temporary = destination / (name + '.' + token + '.part')
    sha = hashlib.sha256(); total = 0
    try:
        request = Request(asset['browser_download_url'], headers={'User-Agent': 'FuriousFurby-App-Updates'})
        with opener(request, timeout=15) as response, temporary.open('xb') as stream:
            if urlparse(response.geturl()).scheme != 'https':
                raise ValueError('Download redirected to an insecure URL')
            while True:
                if cancel and cancel.is_set():
                    raise RuntimeError('Download cancelled')
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > asset['size']:
                    raise ValueError('Installer is larger than its published size')
                stream.write(chunk); sha.update(chunk)
                if progress:
                    progress(total, asset['size'])
        if total != asset['size'] or sha.hexdigest() != expected:
            raise ValueError('Download verification failed; incomplete file removed')
        # Preserve any existing file, including one another app downloaded.
        if target.exists():
            raise ValueError('Destination appeared during download; it was preserved')
        temporary.rename(target)
        return target
    finally:
        temporary.unlink(missing_ok=True)

class UpdateClient:
    def __init__(self, product, installed, state=None):
        self.product, self.installed = product, installed
        root = Path(state) if state else Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Furby/App Updates'
        self.settings_file = root / (product + '.json')
        try:
            self.settings = json.loads(self.settings_file.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.settings = {}
        if not isinstance(self.settings, dict): self.settings = {}
        self.settings.setdefault('auto_check', True)
        self.events = queue.Queue(); self.busy = False; self.result = None
        self.message = 'Check for a newer public version.'; self.downloaded = None
        self.cancel = threading.Event()

    def save(self):
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.settings_file.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.settings), encoding='utf-8')
        os.replace(temporary, self.settings_file)

    def set_auto(self, enabled):
        self.settings['auto_check'] = bool(enabled); self.save()

    def start(self, action='check', destination=None):
        if self.busy:
            return
        if action == 'download' and not (self.result or {}).get('available'):
            return
        if action == 'check':
            self.settings['last_attempt'] = time.time(); self.save()
        self.busy = True; self.message = 'Checking…' if action == 'check' else 'Downloading…'
        self.cancel.clear()
        def work():
            try:
                if action == 'check':
                    result = check_release(self.product, self.installed)
                    self.events.put(('release', result))
                else:
                    folder = destination or Path.home() / 'Downloads/Furby App Updates'
                    path = download_release(self.result, folder, self.cancel,
                        lambda n, size: self.events.put(('progress', f'Download {n/size:.0%}')))
                    self.events.put(('download', path))
            except Exception as exc:
                self.events.put(('error', f'{type(exc).__name__}: {exc}'))
            finally:
                self.events.put(('done', None))
        threading.Thread(target=work, daemon=True, name=f'FurbyUpdates-{self.product}').start()

    def poll(self):
        while True:
            try: kind, value = self.events.get_nowait()
            except queue.Empty: break
            if kind == 'release':
                self.result = value; self.message = value['message']
                self.settings['last_checked'] = time.time(); self.save()
            elif kind == 'download':
                self.downloaded = value; self.message = 'Verified ZIP downloaded. Install after closing this app.'
            elif kind in ('progress', 'error'):
                self.message = value
            elif kind == 'done': self.busy = False

    def maybe_check(self):
        if self.settings.get('auto_check', True) and time.time() - max(self.settings.get('last_checked', 0), self.settings.get('last_attempt', 0)) > 86400:
            self.start()

    def close(self):
        self.cancel.set()

class ProcessUpdateClient(UpdateClient):
    """Blender uses an isolated Python process, never a background Python thread."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.worker=None;self.job=None;self.staging=None

    def start(self,action='check',destination=None):
        import subprocess,sys,tempfile
        if self.busy:return
        if action=='download' and not (self.result or {}).get('available'):return
        python=sys.executable
        if not Path(python).stem.lower().startswith('python'):
            python=next((str(p) for p in (Path(sys.prefix)/'bin/python.exe',Path(sys.prefix)/'bin/python3') if p.is_file()),None)
        if not python:
            self.message='The bundled Python runtime was not found.';return
        if action=='check':
            self.settings['last_attempt']=time.time();self.save()
        self.job=Path(tempfile.mkdtemp(prefix='furby-update-'))
        folder=Path(destination) if destination else Path.home()/'Downloads/Furby App Updates'
        token=os.urandom(6).hex()
        self.staging=folder/(self.result['asset']['name']+'.'+token+'.part') if action=='download' else None
        request=dict(product=self.product,installed=self.installed,action=action,destination=str(folder),token=token,
                     asset=self.result['asset'] if action=='download' else None)
        (self.job/'request.json').write_text(json.dumps(request),encoding='utf-8')
        try:
            self.worker=subprocess.Popen([python,str(Path(__file__).resolve()),'--worker',str(self.job)],
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.busy=True;self.message='Checking…' if action=='check' else 'Downloading…'
        except Exception as exc:
            self.message=f'{type(exc).__name__}: {exc}';self.close()

    def poll(self):
        if self.worker is None:return
        try:self.message=json.loads((self.job/'progress.json').read_text(encoding='utf-8'))['message']
        except (OSError,ValueError):pass
        if self.worker.poll() is None:return
        try:
            outcome=json.loads((self.job/'result.json').read_text(encoding='utf-8'))
            if 'error' in outcome:self.message=outcome['error']
            elif 'release' in outcome:
                self.result=outcome['release'];self.message=self.result['message']
                self.settings['last_checked']=time.time();self.save()
            else:
                self.downloaded=Path(outcome['download']);self.message='Verified ZIP downloaded. Install after closing this app.'
        except (OSError,ValueError) as exc:self.message='Update helper did not complete: '+str(exc)
        self.close()

    def close(self):
        import subprocess,shutil
        if self.worker is not None and self.worker.poll() is None:
            self.worker.terminate()
            try:self.worker.wait(timeout=.2)
            except subprocess.TimeoutExpired:self.worker.kill();self.worker.wait(timeout=1)
        self.worker=None;self.busy=False
        if self.staging is not None:self.staging.unlink(missing_ok=True);self.staging=None
        if self.job is not None:
            shutil.rmtree(self.job,ignore_errors=True);self.job=None

def worker(folder):
    folder=Path(folder)
    request=json.loads((folder/'request.json').read_text(encoding='utf-8'))
    def write(name,value):
        temporary=folder/(name+'.tmp');temporary.write_text(json.dumps(value),encoding='utf-8');os.replace(temporary,folder/name)
    try:
        release=check_release(request['product'],request['installed'])
        if request['action']=='check':outcome={'release':release}
        else:
            # Revalidate the feed; a tampered local request cannot supply a URL.
            if not release.get('available') or release['asset']['name']!=request['asset']['name']:
                raise ValueError('The release changed. Check again before downloading.')
            path=download_release(release,request['destination'],staging_token=request['token'],
                progress=lambda n,size:write('progress.json',{'message':f'Download {n/size:.0%}'}))
            outcome={'download':str(path)}
    except Exception as exc:outcome={'error':f'{type(exc).__name__}: {exc}'}
    write('result.json',outcome)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--worker',required=True)
    worker(parser.parse_args().worker)

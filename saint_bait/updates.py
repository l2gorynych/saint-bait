"""GitHub release updates, staged and verified before a graceful restart."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
import requests
from .version import VERSION


def version_tuple(value):
    match=re.fullmatch(r'v?(\d{1,5})\.(\d{1,5})\.(\d{1,5})',value)
    if not match:raise ValueError('Неверный номер версии')
    return tuple(map(int,match.groups()))


def validate_repository(value):
    if value.startswith('https://github.com/'):value=value[len('https://github.com/'):].rstrip('/')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}',value) or value.split('/')[-1] in ('.','..'):
        raise ValueError('Репозиторий указывается как владелец/название')
    return value


def digest_file(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


class UpdateService:
    def __init__(self,app_dir,session=None):
        self.app_dir=Path(app_dir)
        self.http=session or requests.Session()
        self.status='Версия '+VERSION
        self.staged=None
        self._thread=None

    def check(self,repository):
        if not repository:return
        repository=validate_repository(repository)
        if self._thread and self._thread.is_alive():return
        self._thread=threading.Thread(target=self._check,args=(repository,),name='SaintBait-Updates',daemon=True)
        self._thread.start()

    def _get(self,url,**kwargs):
        response=self.http.get(url,timeout=(5,30),**kwargs)
        response.raise_for_status()
        parsed=urlsplit(response.url)
        allowed=parsed.hostname in ('api.github.com','github.com') or (parsed.hostname or '').endswith('.githubusercontent.com')
        if parsed.scheme!='https' or not allowed:raise ValueError('Неожиданный адрес файла обновления')
        return response

    def _check(self,repository):
        try:
            self.status='Проверка обновлений…'
            release=self._get('https://api.github.com/repos/'+repository+'/releases/latest').json()
            version=release['tag_name'].removeprefix('v')
            if release.get('draft') or release.get('prerelease') or version_tuple(version)<=version_tuple(VERSION):
                self.status='Установлена версия '+VERSION;return
            assets={row['name']:row for row in release['assets']}
            manifest_asset=assets['update.json']
            if manifest_asset.get('size',0)>16384:raise ValueError('Слишком большой манифест')
            manifest=self._get(self._asset_url(manifest_asset,repository)).json()
            if manifest['version']!=version or manifest['file']!='Saint Bait.exe':raise ValueError('Версия манифеста не совпадает')
            checksum=manifest['sha256'].lower()
            size=manifest['size']
            if not re.fullmatch('[0-9a-f]{64}',checksum) or type(size) is not int or not 1_000_000<=size<=300_000_000:
                raise ValueError('Некорректная контрольная сумма или размер')
            binary=assets[manifest['file']]
            if binary['size']!=size:raise ValueError('Размер файла не совпадает')
            folder=self.app_dir/'updates';folder.mkdir(exist_ok=True)
            path=folder/('Saint-Bait-'+version+'.exe')
            partial=path.with_suffix('.part')
            self.status='Загрузка версии '+version+'…'
            response=self._get(self._asset_url(binary,repository),stream=True)
            total=0;digest=hashlib.sha256()
            try:
                with partial.open('wb') as output:
                    for chunk in response.iter_content(1024*1024):
                        total+=len(chunk)
                        if total>size:raise ValueError('Превышен размер обновления')
                        digest.update(chunk);output.write(chunk)
            finally:response.close()
            if total!=size or digest.hexdigest()!=checksum:raise ValueError('Проверка файла обновления не пройдена')
            partial.replace(path)
            self.staged={'source':str(path.resolve()),'sha256':checksum,'version':version}
            self.status='Версия '+version+' готова · установится при закрытии'
        except (requests.RequestException,OSError,ValueError,KeyError,TypeError):
            self.status='Проверить обновления не удалось · версия '+VERSION

    @staticmethod
    def _asset_url(asset,repository):
        url=asset['browser_download_url']
        prefix='https://github.com/'+repository+'/releases/download/'
        if not url.startswith(prefix):raise ValueError('Файл находится вне выбранного репозитория')
        return url

    def schedule_install(self):
        if not self.staged or not getattr(sys,'frozen',False):return False
        source=Path(self.staged['source'])
        if digest_file(source)!=self.staged['sha256']:raise ValueError('Файл обновления изменился')
        plan={**self.staged,'target':str(Path(sys.executable).resolve()),'parent_pid':os.getpid()}
        path=self.app_dir/'updates'/'install.json'
        path.write_text(json.dumps(plan),encoding='utf-8')
        subprocess.Popen([str(source),'--install-update',str(path)],cwd=source.parent,
                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        return True


def install_staged(plan_path):
    """Runs from the staged binary, without Tk, after the previous app exits."""
    plan_path=Path(plan_path).resolve()
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    source=Path(sys.executable).resolve();target=Path(plan['target']).resolve()
    folder=source.parent
    if (folder.name!='updates' or plan_path.parent!=folder or target.parent!=folder.parent
            or target.name not in ('Saint Bait.exe','Podust.exe') or Path(plan['source']).resolve()!=source):
        raise ValueError('Недопустимый путь обновления')
    version_tuple(plan['version'])
    if digest_file(source)!=plan['sha256']:raise ValueError('Контрольная сумма обновления не совпадает')
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        parent=int(plan['parent_pid'])
        if parent<=0 or parent==os.getpid():raise ValueError('Неверный процесс предыдущей версии')
        handle=kernel.OpenProcess(0x100000,False,parent)
        if handle:
            try:
                if kernel.WaitForSingleObject(handle,45000)!=0:raise TimeoutError('Предыдущая версия ещё открыта')
            finally:kernel.CloseHandle(handle)
    # Keep the previous executable for recovery; settings and catches stay intact.
    backup=folder/('previous-'+str(time.time_ns())+'.exe')
    new=folder/'verified-new.exe'
    shutil.copy2(source,new)
    deadline=time.monotonic()+45
    moved=False
    while time.monotonic()<deadline:
        try:
            if target.exists():os.replace(target,backup)
            moved=True;break
        except PermissionError:time.sleep(.25)
    if not moved:raise TimeoutError('Предыдущая версия ещё открыта')
    try:os.replace(new,target)
    except OSError:
        if backup.exists() and not target.exists():os.replace(backup,target)
        raise
    subprocess.Popen([str(target)],cwd=target.parent,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

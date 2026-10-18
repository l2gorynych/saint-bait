"""Optional Supabase sync. Public project key + per-installation anonymous auth."""
import json
import binascii
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
import requests


def validate_service_url(value):
    parsed=urlsplit(value.strip().rstrip('/'))
    local=parsed.hostname in ('127.0.0.1','localhost','::1')
    if (parsed.scheme!='https' and not (local and parsed.scheme=='http')) or not parsed.hostname:
        raise ValueError('Адрес базы должен использовать HTTPS')
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        raise ValueError('Нужен адрес проекта без пути и пароля')
    return parsed.geturl().rstrip('/')


class SupabaseClient:
    def __init__(self,url,public_key,session_path,session=None):
        self.url=validate_service_url(url)
        self.key=public_key.strip()
        if not self.key or len(self.key)>4096:raise ValueError('Укажите публичный ключ проекта')
        if self.key.startswith('sb_secret_'):raise ValueError('Используйте публичный ключ, а не секретный')
        # Legacy JWT service_role keys are also unsuitable for an end-user app.
        try:
            import base64
            raw=self.key.split('.')[1]
            claim=json.loads(base64.urlsafe_b64decode(raw+'='*(-len(raw)%4)))
            if claim.get('role')=='service_role':raise ValueError('Секретный service_role ключ нельзя добавлять в бот')
        except (IndexError,UnicodeError,json.JSONDecodeError,binascii.Error):pass
        self.session_path=Path(session_path)
        self.http=session or requests.Session()
        self.auth={}
        try:
            stored=json.loads(self.session_path.read_text(encoding='utf-8'))
            if stored.get('url')==self.url:self.auth=stored.get('auth',{})
        except (OSError,ValueError):pass

    def request(self,method,path,*,auth=True,**kwargs):
        headers={'apikey':self.key,'Content-Type':'application/json'}
        if auth:headers['Authorization']='Bearer '+self.auth['access_token']
        headers.update(kwargs.pop('headers',{}))
        response=self.http.request(method,self.url+path,headers=headers,timeout=(3,8),**kwargs)
        response.raise_for_status()
        return response

    def authenticate(self):
        if self.auth.get('access_token') and time.time()<self.auth.get('expires_at',0)-60:return
        refresh=self.auth.get('refresh_token')
        path='/auth/v1/token?grant_type=refresh_token' if refresh else '/auth/v1/signup'
        payload={'refresh_token':refresh} if refresh else {}
        response=self.request('POST',path,auth=False,json=payload)
        auth=response.json()
        if not auth.get('access_token') or not auth.get('user',{}).get('id'):
            raise ValueError('В проекте должен быть разрешён анонимный вход')
        auth['expires_at']=auth.get('expires_at',time.time()+auth.get('expires_in',3600))
        self.auth=auth
        temporary=self.session_path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'url':self.url,'auth':auth}),encoding='utf-8')
        temporary.replace(self.session_path)

    def upload(self,events):
        self.authenticate()
        rows=[{**event,'contributor_id':self.auth['user']['id']} for event in events]
        self.request('POST','/rest/v1/catches?on_conflict=id',json=rows,
                     headers={'Prefer':'resolution=ignore-duplicates,return=minimal'})

    def nearby(self,waterbody,x,y):
        self.authenticate()
        result=self.request('POST','/rest/v1/rpc/nearby_catches',json={
            'p_waterbody':waterbody,'p_x':x,'p_y':y,'p_radius':3,'p_limit':100}).json()
        if not isinstance(result,list) or len(result)>100:raise ValueError('Некорректная лента уловов')
        return result

    def upload_prices(self,events):
        self.authenticate()
        self.request('POST','/rest/v1/market_observations?on_conflict=id',
            json=[{**event,'contributor_id':self.auth['user']['id']} for event in events],
            headers={'Prefer':'resolution=ignore-duplicates,return=minimal'})

    def prices(self,waterbody):
        self.authenticate()
        from datetime import datetime,timezone,timedelta
        result=self.request('GET','/rest/v1/market_observations',params={
            'waterbody_id':'eq.'+waterbody,'observed_at':'gte.'+(datetime.now(timezone.utc)-timedelta(hours=24)).isoformat(),
            'select':'id,observed_at,waterbody_id,fish_id,species,weight_g,grade,freshness,price_cents',
            'order':'observed_at.desc','limit':'1000'}).json()
        if not isinstance(result,list) or len(result)>1000:raise ValueError('Некорректные данные цен')
        return result


class CommunityService:
    def __init__(self,journal,registry,session_path):
        self.journal=journal;self.registry=registry;self.session_path=session_path
        self._lock=threading.Lock();self._stop=threading.Event();self._wake=threading.Event()
        self._settings=('','');self._rows=[];self._location=None
        self._prices=[]
        self.status='Локальный журнал · общая база ещё не подключена';self._thread=None

    def configure(self,url,key):
        if url:validate_service_url(url)
        with self._lock:
            self._settings=(url.strip(),key.strip());self._rows=[];self._location=None
        self._wake.set()

    def start(self):
        if self._thread and self._thread.is_alive():return
        self._stop.clear()
        self._thread=threading.Thread(target=self._run,name='SaintBait-Community',daemon=True)
        self._thread.start()

    def stop(self):self._stop.set();self._wake.set()

    def snapshot(self):
        with self._lock:return self._location,list(self._rows),self.status

    def price_snapshot(self):
        with self._lock:return list(self._prices)

    def _run(self):
        client=None;configured=None
        price_water=None;last_prices=0
        while not self._stop.is_set():
            self._wake.clear()
            scene=self.registry.scene()
            location=(scene.waterbody_id,*scene.coordinates) if scene and scene.waterbody_id and scene.coordinates else None
            with self._lock:settings=self._settings
            rows=[];status='Локальный журнал · общая база ещё не подключена'
            try:
                if settings!=configured:
                    client=SupabaseClient(*settings,self.session_path) if all(settings) else None
                    configured=settings
                if client:
                    pending=self.journal.pending()
                    if pending:
                        client.upload(pending)
                        self.journal.mark_synced([event['id'] for event in pending])
                    pending_prices=self.journal.pending_prices()
                    if pending_prices:
                        client.upload_prices(pending_prices)
                        self.journal.mark_prices_synced([event['id'] for event in pending_prices])
                    if location and (price_water!=location[0] or time.monotonic()-last_prices>30):
                        self.journal.add_prices(client.prices(location[0]),synced=True)
                        price_water=location[0];last_prices=time.monotonic()
                    if location:rows=client.nearby(*location)
                    status='Общая лента · обновление каждые 5 с'
                elif location:rows=self.journal.nearby(*location)
            except (requests.RequestException,OSError,ValueError,KeyError,TypeError):
                status='Нет связи с базой · уловы сохраняются локально'
                if location:
                    try:rows=self.journal.nearby(*location)
                    except Exception:pass
            try:prices=self.journal.price_samples(location[0]) if location else []
            except Exception:prices=[]
            with self._lock:self._location=location;self._rows=rows;self.status=status;self._prices=prices
            self._wake.wait(5)

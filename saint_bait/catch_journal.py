"""Durable local catches and an outbox. No network on the fishing thread."""
from dataclasses import asdict,replace
from contextlib import contextmanager
from datetime import datetime,timezone
import json
import sqlite3
import threading
import uuid
import queue
from pathlib import Path
from .rods import RodPhase


class CatchJournal:
    def __init__(self,path):
        self.path=str(path)
        self._lock=threading.RLock()
        self._open=None
        self._context={}
        self._generation=None
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS catches(
                  id TEXT PRIMARY KEY, occurred_at TEXT NOT NULL,waterbody_id TEXT,x REAL,y REAL,
                  species TEXT NOT NULL,weight_g INTEGER NOT NULL,clip_m INTEGER,bait_id TEXT,
                  payload TEXT NOT NULL,synced INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS nearby ON catches(waterbody_id,x,y,occurred_at);
                CREATE INDEX IF NOT EXISTS outbox ON catches(synced,occurred_at);
                CREATE TABLE IF NOT EXISTS market_observations(
                  id TEXT PRIMARY KEY,waterbody_id TEXT NOT NULL,observed_at TEXT NOT NULL,
                  payload TEXT NOT NULL,synced INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS market_history ON market_observations(waterbody_id,observed_at);
            ''')
            db.execute('INSERT OR IGNORE INTO meta VALUES(?,?)',('installation_id',str(uuid.uuid4())))
            self.installation_id=db.execute('SELECT value FROM meta WHERE key=?',('installation_id',)).fetchone()[0]
            self._has_open=db.execute("SELECT 1 FROM meta WHERE key='open_result'").fetchone() is not None

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=3)
        try:
            with db:yield db
        finally:db.close()

    def observe(self,scene,rods,generation):
        """Also captures manual fishing: a native result, not a guessed key press."""
        with self._lock:
            if generation!=self._generation:
                self._context.clear()
                self._generation=generation
            for rod in rods:
                if rod.phase in (RodPhase.CASTING,RodPhase.DEPLOYED,RodPhase.REEL_IN) and not rod.hooked:
                    previous=self._context.get(rod.identity)
                    if not previous or rod.phase==RodPhase.CASTING:
                        self._context[rod.identity]=(scene.waterbody_id,scene.coordinates,rod)
                    elif rod.equipment:
                        # Keep bait seen while waiting; it may disappear on a bite.
                        old=previous[2]
                        if any(x.kind=='bait' for x in rod.equipment) or not old.equipment:
                            self._context[rod.identity]=(previous[0],previous[1],replace(rod,clip_m=old.clip_m))
            if not scene.catch_id:
                if self._open is None and not self._has_open:return
                self._open=None
                with self.connect() as db:db.execute("DELETE FROM meta WHERE key='open_result'")
                self._has_open=False
                return
            if self._open is not None or not scene.catch_ready:return
            if not scene.catch_species or not scene.catch_weight_g:return
            active=next((r for r in rods if r.active),None)
            context=self._context.get(active.identity) if active else None
            waterbody,coordinates,rig=context or (scene.waterbody_id,scene.coordinates,active)
            if waterbody!=scene.waterbody_id:
                waterbody,coordinates,rig=scene.waterbody_id,scene.coordinates,active
            equipment=tuple(rig.equipment) if rig else ()
            bait=scene.catch_bait_id or next((item.system_id for item in equipment if item.kind=='bait'),None)
            signature=json.dumps([generation,scene.catch_id,scene.catch_species,scene.catch_weight_g],default=str)
            with self.connect() as db:
                existing=db.execute("SELECT value FROM meta WHERE key='open_result'").fetchone()
                if existing:
                    saved=json.loads(existing[0])
                    if saved['signature']==signature:
                        self._open=saved['id'];self._has_open=True;return
                event={
                    'id':str(uuid.uuid5(uuid.NAMESPACE_URL,'rf4-catch:'+scene.catch_fish_id)) if scene.catch_fish_id else str(uuid.uuid4()),
                    'fish_id':scene.catch_fish_id,'occurred_at':scene.catch_time or datetime.now(timezone.utc).isoformat(),
                    'waterbody_id':waterbody,'x':coordinates[0] if coordinates else None,
                    'y':coordinates[1] if coordinates else None,'species':scene.catch_species,
                    'weight_g':scene.catch_weight_g,'grade':scene.catch_grade,
                    'clip_m':rig.clip_m if rig else None,'bait_id':bait,
                    'equipment':[asdict(item) for item in equipment],
                    'groundbait_used':None,'groundbait':[],
                }
                db.execute('INSERT OR IGNORE INTO catches(id,occurred_at,waterbody_id,x,y,species,weight_g,clip_m,bait_id,payload) '
                           'VALUES(?,?,?,?,?,?,?,?,?,?)',tuple(event[k] for k in
                           ('id','occurred_at','waterbody_id','x','y','species','weight_g','clip_m','bait_id'))+
                           (json.dumps(event,ensure_ascii=False),))
                db.execute('INSERT OR REPLACE INTO meta VALUES(?,?)',('open_result',json.dumps({'signature':signature,'id':event['id']})))
                self._open=event['id']
                self._has_open=True

    def pending(self,limit=50):
        with self.connect() as db:
            rows=db.execute('SELECT payload FROM catches WHERE synced=0 AND waterbody_id IS NOT NULL '
                            'AND x IS NOT NULL AND y IS NOT NULL ORDER BY occurred_at LIMIT ?',
                            (min(100,max(1,limit)),)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def find_fish(self,fish_id):
        identifier=str(uuid.uuid5(uuid.NAMESPACE_URL,'rf4-catch:'+fish_id))
        with self.connect() as db:row=db.execute('SELECT payload FROM catches WHERE id=?',(identifier,)).fetchone()
        return json.loads(row[0]) if row else None

    def mark_synced(self,ids):
        with self.connect() as db:db.executemany('UPDATE catches SET synced=1 WHERE id=?',[(v,) for v in ids])

    def add_prices(self,rows,synced=False):
        with self.connect() as db:
            db.executemany('INSERT OR IGNORE INTO market_observations VALUES(?,?,?,?,?)',
                [(row['id'],row['waterbody_id'],row['observed_at'],json.dumps(row,ensure_ascii=False),int(synced)) for row in rows])

    def pending_prices(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT payload FROM market_observations WHERE synced=0 LIMIT 50')]

    def mark_prices_synced(self,ids):
        with self.connect() as db:db.executemany('UPDATE market_observations SET synced=1 WHERE id=?',[(v,) for v in ids])

    def price_samples(self,waterbody):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT payload FROM market_observations '
                'WHERE waterbody_id=? ORDER BY observed_at DESC LIMIT 2000',(waterbody,))]

    def nearby(self,waterbody,x,y,radius=3,limit=100):
        radius=min(3,max(0,float(radius)))
        with self.connect() as db:
            rows=db.execute('SELECT payload FROM catches WHERE waterbody_id=? AND x BETWEEN ? AND ? '
                            'AND y BETWEEN ? AND ? ORDER BY occurred_at DESC LIMIT ?',
                            (waterbody,x-radius,x+radius,y-radius,y+radius,min(200,max(1,limit)))).fetchall()
        return [json.loads(row[0]) for row in rows]


class JournalWorker:
    """Disk I/O is isolated from the 50 ms tackle load observer."""
    def __init__(self,journal):
        self.journal=journal;self.error=None
        self.queue=queue.Queue(maxsize=128)
        self._signature=None;self._thread=None;self._stop=threading.Event()

    def start(self):
        if self._thread and self._thread.is_alive():return
        self._stop.clear()
        self._thread=threading.Thread(target=self._run,name='SaintBait-CatchJournal',daemon=True)
        self._thread.start()

    def submit(self,scene,rods,generation):
        signature=(generation,scene.catch_id,scene.catch_ready,scene.catch_species,scene.catch_weight_g,
                   scene.waterbody_id,scene.coordinates,tuple((r.identity,r.phase,r.clip_m,
                   tuple((i.kind,i.system_id) for i in r.equipment)) for r in rods))
        if signature==self._signature:return
        try:self.queue.put_nowait((scene,rods,generation))
        except queue.Full:self.error='Очередь журнала заполнена';return
        self._signature=signature

    def stop(self):
        self._stop.set()
        if self._thread:self._thread.join(timeout=1)

    def _run(self):
        while not self._stop.is_set() or not self.queue.empty():
            try:payload=self.queue.get(timeout=.1)
            except queue.Empty:continue
            try:self.journal.observe(*payload);self.error=None
            except Exception as error:self.error=type(error).__name__
            finally:self.queue.task_done()

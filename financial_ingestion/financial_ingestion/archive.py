"""Local durable publication outbox. SQLite FULL sync stores the envelope first.
Use a persistent local volume, and back it up along with XML/HTML archives.
"""
import hashlib
import os
from pathlib import Path
import sqlite3
from .contract import canonical, loads, MessageValidator, utc_text

class Archive:
    def __init__(self,directory):
        self.root=Path(directory); self.root.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(self.root/'outbox.sqlite3',timeout=30)
        self.db.execute('PRAGMA journal_mode=WAL'); self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS publications (message_id TEXT PRIMARY KEY, envelope BLOB NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, updated_at TEXT NOT NULL)')
        self.db.commit()
    def save_raw(self,data,suffix):
        name=hashlib.sha256(data).hexdigest()+suffix; target=self.root/name
        if not target.exists():
            tmp=self.root/(name+f'.{os.getpid()}.tmp')
            with open(tmp,'wb') as f:
                f.write(data); f.flush(); os.fsync(f.fileno())
            os.replace(tmp,target)
            if os.name!='nt':
                fd=os.open(self.root,os.O_RDONLY)
                try: os.fsync(fd)
                finally: os.close(fd)
        return name
    def enqueue(self,envelope,max_bytes=8_000_000):
        MessageValidator(max_bytes).validate(envelope)
        body=canonical(envelope); mid=envelope['message_id']
        with self.db:
            existing=self.db.execute('SELECT envelope FROM publications WHERE message_id=?',(mid,)).fetchone()
            if existing and bytes(existing[0])!=body: raise ValueError('Cannot reuse message_id with different envelope')
            self.db.execute('INSERT OR IGNORE INTO publications (message_id,envelope,status,updated_at) VALUES (?,?,?,?)',(mid,body,'PENDING',utc_text()))
        return mid
    def pending(self):
        for mid,body in self.db.execute("SELECT message_id,envelope FROM publications WHERE status != 'PUBLISHED' ORDER BY rowid"):
            yield mid,bytes(body)
    def mark(self,mid,status,error=None):
        with self.db:
            self.db.execute('UPDATE publications SET status=?,attempts=attempts+1,last_error=?,updated_at=? WHERE message_id=?',(status,error,utc_text(),mid))
    def get(self,mid):
        row=self.db.execute('SELECT envelope FROM publications WHERE message_id=?',(mid,)).fetchone()
        if not row: raise KeyError(mid)
        return loads(row[0])
    def close(self): self.db.close()

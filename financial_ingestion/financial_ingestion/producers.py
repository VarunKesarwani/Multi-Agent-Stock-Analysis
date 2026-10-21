import uuid
from urllib.parse import urlparse
from .archive import Archive
from .contract import envelope, digest, PermanentError
from .extractors import fetch_screener, parse_xbrl
from .broker import flush_outbox

def screener_produce(symbol,session,settings,publish=True,correlation_id=None):
    archive=Archive(settings.archive_dir)
    try:
        payload,page=fetch_screener(session,symbol,settings)
        archive.save_raw(page,'.html')
        # Payload stays stable when unrelated page markup changes.
        e=envelope('SCREENER',symbol,payload,correlation_id=correlation_id)
        archive.enqueue(e,settings.max_message_bytes)
        if publish: flush_outbox(archive,settings)
        return e
    finally: archive.close()

def xbrl_produce(symbol,record,session,settings,publish=True,correlation_id=None):
    symbol=symbol.strip().upper()
    if str(record.get('symbol','')).strip().upper()!=symbol: raise PermanentError('NSE record symbol mismatch')
    url=record.get('xbrl',''); u=urlparse(url)
    if u.scheme!='https' or u.hostname not in ('nsearchives.nseindia.com','archives.nseindia.com') or not u.path.lower().endswith('.xml'):
        raise PermanentError('Unexpected NSE XBRL source URL')
    if not record.get('seqNumber'): raise PermanentError('NSE record ID required')
    archive=Archive(settings.archive_dir)
    try:
        response=session.get(url,timeout=60); response.raise_for_status()
        xml=response.content
        if not xml: raise PermanentError('Empty XML download')
        raw_id=archive.save_raw(xml,'.xml')
        meta=dict(record)
        meta['scope']={'Consolidated':'CONSOLIDATED','Non-Consolidated':'STANDALONE','Standalone':'STANDALONE'}.get(record.get('consolidated'),'UNKNOWN')
        # filed_at is only accepted when supplied as a verified UTC timestamp.
        # Board-meeting or reporting-end dates are not publication timestamps.
        payload=parse_xbrl(xml,meta,url)
        payload['document']['archive_sha256']=raw_id.removesuffix('.xml')
        source_id=f"NSE_XBRL:{symbol}:{record['seqNumber']}:{digest(payload)}"
        e=envelope('NSE_XBRL',symbol,payload,source_id,correlation_id)
        archive.enqueue(e,settings.max_message_bytes)
        if publish: flush_outbox(archive,settings)
        return e
    finally: archive.close()

def fetch_nse_records(session,symbol,issuer):
    session.headers.update({'User-Agent':'Mozilla/5.0','Accept':'application/json,text/plain,*/*','Referer':'https://www.nseindia.com/'})
    r=session.get('https://www.nseindia.com/',timeout=30); r.raise_for_status()
    r=session.get('https://www.nseindia.com/api/corporates-financial-results',params=dict(index='equities',fo_sec='false',symbol=symbol,issuer=issuer,period='all',period_ended='all'),timeout=30)
    r.raise_for_status(); rows=r.json()
    if not isinstance(rows,list): raise PermanentError('Unexpected NSE metadata response')
    return rows

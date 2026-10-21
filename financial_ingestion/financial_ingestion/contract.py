import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

SOURCES = {'SCREENER': 'screener', 'NSE_XBRL': 'xblr'}
SECTIONS = ('profit_loss', 'quarterly_results', 'balance_sheet', 'cash_flows', 'ratios_table', 'shareholding')

class PermanentError(ValueError):
    pass

def utcnow():
    return datetime.now(timezone.utc)

def utc_text():
    return utcnow().isoformat().replace('+00:00', 'Z')

def parse_utc(value):
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if d.tzinfo is None or d.utcoffset().total_seconds() != 0:
            raise ValueError('UTC required')
        return d
    except (TypeError, AttributeError, ValueError) as e:
        raise PermanentError('Invalid UTC timestamp') from e

def canonical(value):
    # Contract v1: JSON UTF-8, sorted string keys, compact separators, Unicode
    # unescaped, no floats at any depth. Source numbers stay strings.
    def check(x):
        if x is None or type(x) in (str, int, bool):
            return
        if isinstance(x, list):
            for v in x: check(v)
        elif isinstance(x, dict) and all(isinstance(k, str) for k in x):
            for v in x.values(): check(v)
        else:
            raise PermanentError('Only JSON values supported; numeric source text must be strings')
    check(value)
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')

def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()

def loads(raw):
    def pairs(items):
        d = {}
        for k, v in items:
            if k in d: raise PermanentError('Duplicate JSON object key')
            d[k] = v
        return d
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda x: (_ for _ in ()).throw(PermanentError('Non-finite JSON')))
    except (ValueError, UnicodeError) as e:
        raise PermanentError('Invalid JSON') from e

def envelope(source, symbol, payload, source_document_id=None, correlation_id=None):
    h = digest(payload)
    e = dict(message_id=str(uuid.uuid4()), contract_version=1, source=source,
             symbol=symbol.strip().upper(), source_document_id=source_document_id or f'{source}:{symbol.strip().upper()}:{h}',
             content_hash=h, extracted_at=utc_text(), extractor_version='1.0.0',
             correlation_id=correlation_id or str(uuid.uuid4()), payload=payload)
    MessageValidator().validate(e)
    return e

class MessageValidator:
    def __init__(self, max_bytes=8_000_000):
        self.max_bytes = max_bytes

    def validate(self, e):
        if not isinstance(e, dict): raise PermanentError('Envelope must be an object')
        required = {'message_id','contract_version','source','symbol','source_document_id','content_hash','extracted_at','extractor_version','correlation_id','payload'}
        if set(e) != required: raise PermanentError('Envelope fields mismatch')
        if type(e['contract_version']) is not int or e['contract_version'] != 1:
            raise PermanentError('Unsupported contract version')
        if e['source'] not in SOURCES: raise PermanentError('Unknown source')
        for k in required - {'payload','contract_version'}:
            if not isinstance(e[k], str) or not e[k]: raise PermanentError(f'Invalid {k}')
        try: uuid.UUID(e['message_id'])
        except ValueError as ex: raise PermanentError('Invalid message_id') from ex
        if e['symbol'] != e['symbol'].strip().upper(): raise PermanentError('Symbol must be normalized')
        parse_utc(e['extracted_at'])
        if not re.fullmatch('[0-9a-f]{64}', e['content_hash']): raise PermanentError('Invalid hash')
        if not isinstance(e['payload'], dict): raise PermanentError('Payload must be object')
        if len(canonical(e)) > self.max_bytes: raise PermanentError('Message size limit exceeded')
        if digest(e['payload']) != e['content_hash']: raise PermanentError('Payload hash mismatch')
        p = e['payload']
        if e['source'] == 'SCREENER':
            if not isinstance(p.get('tables'), dict) or not isinstance(p.get('section_status'), dict):
                raise PermanentError('Missing Screener tables/status')
            for s in SECTIONS:
                if p['section_status'].get(s) not in ('COLLECTED','NOT_AVAILABLE','FAILED'):
                    raise PermanentError(f'Missing/invalid section status: {s}')
                if p['section_status'][s] == 'COLLECTED':
                    t = p['tables'].get(s)
                    if not isinstance(t, dict) or not isinstance(t.get('columns'), list) or not isinstance(t.get('rows'), list):
                        raise PermanentError(f'Invalid table: {s}')
                    if not all(isinstance(c,str) for c in t['columns']): raise PermanentError('Invalid column')
                    for row in t['rows']:
                        if not isinstance(row.get('label'),str) or not isinstance(row.get('values'),list) or len(row['values']) != len(t['columns']):
                            raise PermanentError('Row/column alignment mismatch')
                        if not all(isinstance(v,str) for v in row['values']): raise PermanentError('Source values must be strings')
        else:
            for k in ('filing_metadata','document','namespaces'):
                if not isinstance(p.get(k),dict): raise PermanentError(f'Missing {k}')
            for k in ('contexts','units','facts'):
                if not isinstance(p.get(k),list): raise PermanentError(f'Missing {k}')
        return e

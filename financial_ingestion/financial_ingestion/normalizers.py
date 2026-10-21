import calendar
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
from bson.decimal128 import Decimal128
from dateutil.relativedelta import relativedelta
from .contract import digest, parse_utc, utcnow
from .mappings import MetricDefinitions

MISSING = {'', '-', '--', '—', '–', 'NA', 'N/A', 'null', 'None'}

@dataclass
class NormalizationResult:
    facts: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    disclosures: list = field(default_factory=list)
    eligible: bool = False
    def issue(self, locator, reason, code='UNRESOLVED', blocking=True):
        self.issues.append(dict(locator=locator, reason=reason, code=code, blocking=blocking))

def date(value):
    return datetime.strptime(value, '%Y-%m-%d').replace(tzinfo=timezone.utc)

def month_end(label):
    d = datetime.strptime(label, '%b %Y')
    return d.replace(day=calendar.monthrange(d.year,d.month)[1],tzinfo=timezone.utc)

def months_between(start, end):
    n = (end.year-start.year)*12 + end.month-start.month + 1
    if start.day != 1 or end.day != calendar.monthrange(end.year,end.month)[1]:
        raise ValueError('Period boundaries are not evidenced full months')
    return n

def number(text):
    if not isinstance(text,str): raise ValueError('Numeric source must be string')
    t = text.strip().replace('−','-')
    if t in MISSING: raise ValueError('Missing source value')
    t = t.replace(',','').removesuffix('%').strip()
    if t.startswith('(') and t.endswith(')'): t = '-' + t[1:-1]
    try: n = Decimal(t)
    except InvalidOperation as e: raise ValueError('Invalid numeric value') from e
    if not n.is_finite(): raise ValueError('Non-finite numeric value')
    return n

def period(kind, typ, end, start=None, months=None):
    return dict(period_kind=kind,period_type=typ,period_start=start,period_end=end,duration_months=months)

class FinancialFactValidator:
    def validate(self, facts, result):
        grouped = defaultdict(list)
        for f in facts:
            try:
                if f['scope'] not in ('CONSOLIDATED','STANDALONE'): raise ValueError('Unknown scope')
                if not isinstance(f['value'],Decimal128) or not f['value'].to_decimal().is_finite(): raise ValueError('Invalid numeric type')
                if f['period_kind']=='INSTANT':
                    if f['period_start'] is not None or f['duration_months'] is not None: raise ValueError('Instant has duration')
                else:
                    if f['period_start'] > f['period_end']: raise ValueError('Reversed period')
                    if months_between(f['period_start'], f['period_end']) != f['duration_months']: raise ValueError('Duration mismatch')
                grouped[f['logical_fact_key']].append(f)
            except (ValueError,TypeError,KeyError) as e:
                result.issue(f.get('provenance',{}).get('locator','unknown'),str(e),'INVALID_FACT')
        output = []
        for items in grouped.values():
            if len({str(x['value'].to_decimal()) for x in items}) > 1:
                for x in items: result.issue(x['provenance']['locator'],'Conflicting values for the same fact identity','CONFLICT')
            else:
                f = items[0]
                f['provenance']['duplicate_locators'] = [x['provenance']['locator'] for x in items[1:]]
                output.append(f)
        return output

class BaseNormalizer:
    def __init__(self, definitions=None, normalization_version='1.0.0'):
        self.definitions = definitions or MetricDefinitions()
        self.version = normalization_version
    def fact(self,e,m,raw,unit,factor,p,scope,dimensions,locator,extra=None):
        with localcontext() as ctx:
            ctx.prec = 80
            value = Decimal128(number(raw)*Decimal(factor))
        dims = sorted(dimensions,key=lambda x:digest(x))
        base = dict(symbol=e['symbol'],source=e['source'],scope=scope,statement=m['statement'],
                    metric=m['metric'],metric_label=m['source_label'],value=value,unit=unit,
                    **p,dimensions=dims,dimensions_key=digest(dims),source_document_id=e['source_document_id'],
                    provenance=dict(locator=locator,original_value=raw,original_unit=(extra or {}).get('original_unit'),
                                    conversion_factor=str(factor), **{k:v for k,v in (extra or {}).items() if k!='original_unit'}),
                    validation_status='VALID',mapping_version=self.definitions.version,normalization_version=self.version,
                    schema_version=1,observed_at=parse_utc(e['extracted_at']),created_at=utcnow())
        identity = {k:base[k] for k in ('symbol','source','scope','statement','metric','unit','period_kind','period_type','duration_months','dimensions_key')}
        identity.update({k:base[k].isoformat() if base[k] else None for k in ('period_start','period_end')})
        base['logical_fact_key'] = digest(identity)
        base['fact_version_key'] = digest([base['logical_fact_key'],e['source_document_id'],e['content_hash'],str(value),self.version,self.definitions.version,1])
        return base
    def finish(self,result,candidates):
        result.facts = FinancialFactValidator().validate(candidates,result)
        result.eligible = bool(result.facts) and not any(x['blocking'] for x in result.issues)
        return result

class ScreenerNormalizer(BaseNormalizer):
    def normalize(self,e):
        r = NormalizationResult(); candidates=[]; p=e['payload']; scope=p.get('scope')
        if p.get('identity',{}).get('symbol') != e['symbol']:
            r.issue('identity','Source identity does not match requested company','IDENTITY'); return r
        if scope not in ('CONSOLIDATED','STANDALONE'):
            r.issue('scope','Unknown reporting scope'); return r
        for s,status in p['section_status'].items():
            if status != 'COLLECTED':
                # Shareholding is supplementary to the core financial statements. A parser
                # failure there must not suppress otherwise valid P&L/BS/CF/ratio facts.
                # Core financial-section failures remain blocking.
                blocking = status == 'FAILED' and s != 'shareholding'
                r.issue(f'tables.{s}',f'Section {status}',status,blocking=blocking)
        for statement,t in p['tables'].items():
            for i,row in enumerate(t['rows']):
                label=re.sub(r'\s*\+\s*$','',row['label']).strip()
                m=self.definitions.find('SCREENER',label,statement)
                if not m:
                    metric=re.sub(r'[^a-z0-9]+','_',label.lower().replace('%',' percent ')).strip('_')
                    kind='INSTANT' if statement in ('balance_sheet','shareholding') else 'DURATION'
                    inferred=('PERCENT' if '%' in label or statement=='shareholding' and label!='No. of Shareholders'
                              else 'DAYS' if 'days' in label.lower() else 'COUNT' if 'shareholder' in label.lower()
                              else 'INR_PER_SHARE' if 'eps' in label.lower() else 'INR')
                    m=dict(statement=statement,metric=metric,source_label=label,unit=inferred,period_kind=kind)
                    r.issue(f'tables.{statement}.rows[{i}]',f'Unmapped metric retained as source label: {label}','UNMAPPED',False)
                for j,(column,raw) in enumerate(zip(t['columns'],row['values'])):
                    loc=f'tables.{statement}.rows[{i}].values[{j}]'
                    if raw.strip() in MISSING: continue
                    try:
                        per=self.resolve_period(statement,column,m,p,t)
                        unit,factor=self.resolve_unit(m,raw,t)
                        candidates.append(self.fact(e,m,raw,unit,factor,per,scope,[],loc,dict(original_unit=t.get('unit_label'),source_period=column,source_url=p.get('source_url'))))
                    except (ValueError,InvalidOperation,OverflowError) as ex:
                        r.issue(loc,str(ex))
        return self.finish(r,candidates)

    def resolve_unit(self,m,raw,t):
        unit=m['unit']
        if unit=='INR':
            heading=(t.get('unit_label') or '').lower()
            options=[('crore','10000000'),('cr.','10000000'),('million','1000000'),('lakh','100000'),('thousand','1000')]
            if not any(x in heading for x in ('rs','inr','₹','rupee')): raise ValueError('Unresolved monetary currency')
            found={factor for word,factor in options if word in heading}
            if len(found)!=1: raise ValueError('Unresolved or ambiguous monetary multiplier')
            return unit,found.pop()
        if unit=='PERCENT' and '%' not in raw and '%' not in m['source_label']:
            raise ValueError('Percentage unit not evidenced')
        # Non-monetary units are explicit in reviewed metric definitions.
        return unit,'1'

    def resolve_period(self,statement,column,m,p,t):
        # Explicit evidence may be attached by an archive review, never guessed.
        evidence=t.get('period_evidence',{}).get(column)
        if evidence:
            if not evidence.get('source_locator'): raise ValueError('Period evidence requires source locator')
            end=date(evidence['end'])
            if m['period_kind']=='INSTANT': return period('INSTANT','INSTANT',end)
            start=date(evidence['start']); n=months_between(start,end)
            typ=evidence['type']
            if typ not in ('ANNUAL','QUARTERLY','HALF_YEARLY','YTD','TTM','EXTENDED'): raise ValueError('Unknown period type')
            expected={'ANNUAL':12,'QUARTERLY':3,'HALF_YEARLY':6,'TTM':12}.get(typ)
            if expected and n!=expected: raise ValueError('Period type disagrees with duration')
            return period('DURATION',typ,end,start,n)
        if column.upper()=='TTM':
            endpoints=[]
            for table in p['tables'].values():
                for label in table['columns']:
                    z=re.fullmatch(r'([A-Za-z]{3} \d{4})(?: \d+m)?',label.strip())
                    if z: endpoints.append(month_end(z[1]))
            if not endpoints: raise ValueError('TTM endpoint unavailable')
            end=max(endpoints); start=(end+timedelta(days=1))-relativedelta(months=12)
            return period('DURATION','TTM',end,start,12)
        match=re.fullmatch(r'([A-Za-z]{3} \d{4})(?: (\d+)m)?',column.strip())
        if not match: raise ValueError('Unresolved source period label')
        end=month_end(match[1])
        if m['period_kind']=='INSTANT': return period('INSTANT','INSTANT',end)
        if match[2]: n=int(match[2]); typ='EXTENDED'
        elif statement=='quarterly_results': n=3; typ='QUARTERLY'
        elif statement in ('profit_loss','cash_flows','ratios_table'): n=12; typ='ANNUAL'
        else: raise ValueError('Unresolved duration')
        if n<=0: raise ValueError('Invalid duration')
        # A gap that might reflect a changed accounting year is not assumed annual.
        if typ=='ANNUAL':
            prior=[]
            for c in t['columns']:
                z=re.fullmatch(r'([A-Za-z]{3} \d{4})(?: \d+m)?',c)
                if z:
                    d=month_end(z[1])
                    if d<end: prior.append(d)
            if prior and (end.year-max(prior).year)*12+end.month-max(prior).month !=12:
                raise ValueError('Annual boundary requires explicit evidence after a reporting gap')
        start=(end+timedelta(days=1))-relativedelta(months=n)
        return period('DURATION',typ,end,start,n)

class XbrlNormalizer(BaseNormalizer):
    def normalize(self,e):
        r=NormalizationResult(); candidates=[]; p=e['payload']; meta=p['filing_metadata']
        contexts={x['id']:x for x in p['contexts']}; units={x['id']:x for x in p['units']}
        if len(contexts)!=len(p['contexts']) or len(units)!=len(p['units']):
            r.issue('contexts/units','Duplicate reference IDs','CONFLICT'); return r
        scope=meta.get('scope')
        reported={f['value'].strip().upper() for f in p['facts'] if f.get('local_name')=='NatureOfReportStandaloneConsolidated'}
        if reported and reported != {scope}:
            r.issue('filing_metadata.scope','Filing scope conflicts with XML disclosure','CONFLICT'); return r
        if scope not in ('CONSOLIDATED','STANDALONE'):
            r.issue('filing_metadata.scope','Unknown scope'); return r
        for f in p['facts']:
            loc=f['occurrence_id']; c=contexts.get(f.get('contextRef'))
            if not c: r.issue(loc,'Unresolved contextRef'); continue
            identities=c.get('identifiers',[])
            matches=[x['value'] for x in identities if x['scheme']=='http://www.nseindia.com/NSESymbol']
            if matches and matches != [e['symbol']]: r.issue(loc,'Context company identity mismatched','IDENTITY'); continue
            if not matches: r.issue(loc,'Context has no NSE symbol identifier; using record symbol','IDENTITY',False)
            m=self.definitions.find('NSE_XBRL',f['qualified_tag'])
            if not m:
                if not f.get('unitRef'):
                    r.disclosures.append(dict(locator=loc,concept=f['qualified_tag'],value=f['value'],contextRef=f['contextRef']))
                    continue
                try: unit=self.resolve_unit(units[f['unitRef']])
                except (KeyError,ValueError):
                    r.issue(loc,f"Unknown unit for concept: {f['qualified_tag']}",'UNMAPPED',False); continue
                m=dict(statement='xbrl_facts',metric=re.sub(r'[^a-z0-9]+','_',f['local_name'].lower()).strip('_'),
                       source_label=f['qualified_tag'],unit=unit,
                       period_kind='INSTANT' if c['period'].get('instant') else 'DURATION')
                r.issue(loc,f"Unmapped concept retained as source label: {f['qualified_tag']}",'UNMAPPED',False)
            if f.get('nil'): r.issue(loc,'Source reports nil','NIL',blocking=False); continue
            try:
                if c.get('unresolved_structure'): raise ValueError('Context has unsupported non-dimensional structure')
                u=units.get(f.get('unitRef'))
                if not u: raise ValueError('Unresolved unitRef')
                unit=self.resolve_unit(u)
                if unit!=m['unit']: raise ValueError('Unit incompatible with mapping')
                per=self.resolve_period(c,meta,m)
                candidates.append(self.fact(e,m,f['value'],unit,'1',per,scope,c['dimensions'],loc,
                                            dict(original_unit=u,contextRef=f['contextRef'],decimals=f.get('decimals'),precision=f.get('precision'))))
            except (ValueError,InvalidOperation,KeyError) as ex: r.issue(loc,str(ex))
        return self.finish(r,candidates)

    def resolve_unit(self,u):
        INR='{http://www.xbrl.org/2003/iso4217}INR'; SH='{http://www.xbrl.org/2003/instance}shares'
        if u['numerator']==[INR] and not u['denominator']: return 'INR'
        if u['numerator']==[INR] and u['denominator']==[SH]: return 'INR_PER_SHARE'
        if u['numerator']==[SH] and not u['denominator']: return 'COUNT'
        raise ValueError('Unresolved XBRL unit (pure does not imply percentage)')

    def resolve_period(self,c,meta,m):
        p=c['period']
        if p.get('instant'):
            if m['period_kind']!='INSTANT': raise ValueError('Instant incompatible with metric')
            return period('INSTANT','INSTANT',date(p['instant']))
        if m['period_kind']=='INSTANT': raise ValueError('Duration incompatible with instant metric')
        start=date(p['start']); end=date(p['end']); n=months_between(start,end)
        # Classification needs filing evidence as well as duration, including comparisons.
        reporting=meta.get('period','').lower(); cumulative=meta.get('cumulative')
        if n==12 and reporting=='annual': typ='ANNUAL'
        elif n==3 and reporting=='quarterly' and cumulative=='Non-cumulative': typ='QUARTERLY'
        elif n==6 and reporting in ('half yearly','half-yearly','half yearly results') and cumulative=='Non-cumulative': typ='HALF_YEARLY'
        elif n in (3,6,9) and cumulative=='Cumulative': typ='YTD'
        elif meta.get('period_type')=='EXTENDED' and meta.get('duration_months')==n: typ='EXTENDED'
        elif meta.get('period_type')=='TTM' and n==12: typ='TTM'
        elif n==12: typ='ANNUAL'
        elif n==3: typ='QUARTERLY' if cumulative=='Non-cumulative' else 'YTD'
        elif n==6: typ='HALF_YEARLY' if cumulative=='Non-cumulative' else 'YTD'
        elif n==9: typ='YTD'
        else: typ='EXTENDED'
        return period('DURATION',typ,end,start,n)

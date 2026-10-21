from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import pytest
from bson.decimal128 import Decimal128
from financial_ingestion.contract import envelope, digest, MessageValidator, PermanentError, SECTIONS
from financial_ingestion.normalizers import ScreenerNormalizer, XbrlNormalizer
from financial_ingestion.extractors import parse_xbrl, parse_screener, fetch_screener
from financial_ingestion.mappings import MetricDefinitions,NS

SAMPLES=Path(__file__).resolve().parents[1]/'samples'

def screener_payload():
    return dict(scope='CONSOLIDATED',source_url='https://www.screener.in/company/ACC/consolidated/',identity={'symbol':'ACC'},
        tables={'profit_loss':dict(unit_label='Figures in Rs. Crores',columns=['Mar 2025','TTM'],rows=[{'label':'Sales','values':['21,762','25,442']}],
                period_evidence={'TTM':dict(start='2024-07-01',end='2025-06-30',type='TTM',source_locator='TEST FIXTURE: explicit TTM endpoint')})},
        section_status={s:('COLLECTED' if s=='profit_loss' else 'NOT_AVAILABLE') for s in SECTIONS})

def message(payload=None): return envelope('SCREENER','ACC',payload or screener_payload())

def test_amount_decimal_and_distinct_annual_ttm():
    r=ScreenerNormalizer().normalize(message())
    assert r.eligible
    assert {x['period_type'] for x in r.facts}=={'ANNUAL','TTM'}
    assert r.facts[0]['value'].to_decimal()==Decimal('217620000000')
    assert len({x['logical_fact_key'] for x in r.facts})==2

def test_stable_hash_and_fact_identity():
    a=message();b=message()
    assert a['message_id']!=b['message_id'] and a['content_hash']==b['content_hash']
    n=ScreenerNormalizer()
    assert [x['fact_version_key'] for x in n.normalize(a).facts]==[x['fact_version_key'] for x in n.normalize(b).facts]
    n2=ScreenerNormalizer(normalization_version='2.0.0')
    assert n.normalize(a).facts[0]['fact_version_key']!=n2.normalize(a).facts[0]['fact_version_key']

def test_unknown_unit_mapping_ttm_report_issues():
    p=screener_payload();p['tables']['profit_loss']['unit_label']=None;p['tables']['profit_loss'].pop('period_evidence')
    p['tables']['profit_loss']['rows'].append({'label':'Unknown','values':['1','2']})
    r=ScreenerNormalizer().normalize(message(p))
    assert not r.eligible and not r.facts
    assert len(r.issues)>=3 and all('locator' in i and 'reason' in i for i in r.issues)

def test_extended_and_instant():
    p=screener_payload();p['tables']['profit_loss']['columns']=['Mar 2023 15m'];p['tables']['profit_loss']['rows'][0]['values']=['123.123456789']
    p['tables']['balance_sheet']=dict(unit_label='Rs. Crores',columns=['Mar 2023'],rows=[dict(label='Total Assets',values=['200'])])
    p['section_status']['balance_sheet']='COLLECTED'
    r=ScreenerNormalizer().normalize(message(p));assert r.eligible
    f=r.facts[0];assert f['duration_months']==15 and f['period_start'].strftime('%Y-%m-%d')=='2022-01-01'
    assert f['value'].to_decimal()==Decimal('1231234567.89')
    f=r.facts[1];assert f['period_kind']=='INSTANT' and f['period_start'] is None and f['duration_months'] is None

def test_conflicting_duplicate_excludes_all_versions():
    p=screener_payload();p['tables']['profit_loss']['rows'].append({'label':'Sales','values':['1','2']})
    r=ScreenerNormalizer().normalize(message(p));assert not r.facts and not r.eligible
    assert any(i['code']=='CONFLICT' for i in r.issues)

def test_percentage_points():
    p=screener_payload();p['tables']['profit_loss']['rows']=[{'label':'OPM %','values':['13%','12.5%']}]
    r=ScreenerNormalizer().normalize(message(p));assert r.facts[0]['value'].to_decimal()==13

def test_schema_and_hash_failures():
    e=message();e['payload']['scope']='STANDALONE'
    with pytest.raises(PermanentError,match='hash'):MessageValidator().validate(e)
    e=message();e['contract_version']=2
    with pytest.raises(PermanentError):MessageValidator().validate(e)
    with pytest.raises(PermanentError):digest({'amount':float('nan')})
    p=screener_payload();p['tables']['profit_loss']['rows'][0]['values']=['1']
    with pytest.raises(PermanentError):message(p)

def test_source_scope_and_identity():
    p=screener_payload();p['scope']='STANDALONE'
    assert all(f['scope']=='STANDALONE' for f in ScreenerNormalizer().normalize(message(p)).facts)
    p['identity']['symbol']='TCS';r=ScreenerNormalizer().normalize(message(p));assert not r.facts

def test_real_tcs_archived_xml():
    e=json.loads((SAMPLES/'tcs_archived.envelope.json').read_text())
    MessageValidator().validate(e)
    r=XbrlNormalizer().normalize(e)
    assert r.facts
    assert all(isinstance(f['value'],Decimal128) for f in r.facts)
    segments=[f for f in r.facts if f['metric']=='segment_profit_before_tax_and_finance_costs']
    assert len({f['dimensions_key'] for f in segments})>1
    original=e['payload']['facts']
    by_loc={f['occurrence_id']:f for f in original}
    for f in r.facts:
        assert f['value'].to_decimal()==Decimal(by_loc[f['provenance']['locator']]['value']) # decimals=-7 is NOT a multiplier
    assert r.disclosures and any(i['code']=='UNMAPPED' for i in r.issues)

def test_acc_archived_preview_is_conservative():
    e=json.loads((SAMPLES/'acc_archived_preview.envelope.json').read_text())
    r=ScreenerNormalizer().normalize(e)
    assert not r.eligible
    assert any('currency' in i['reason'].lower() for i in r.issues)

def test_typed_dimensions_and_local_namespaces():
    xml=f'''<x:xbrl xmlns:x="http://www.xbrl.org/2003/instance" xmlns:d="http://xbrl.org/2006/xbrldi" xmlns:m="{NS}" xmlns:i="http://www.xbrl.org/2003/iso4217"><x:context id="c"><x:entity><x:identifier scheme="http://www.nseindia.com/NSESymbol">TCS</x:identifier></x:entity><x:period><x:startDate>2024-04-01</x:startDate><x:endDate>2024-06-30</x:endDate></x:period><x:scenario><d:typedMember dimension="m:CustomerAxis"><m:Code>00123</m:Code></d:typedMember></x:scenario></x:context><x:unit id="u"><x:measure>i:INR</x:measure></x:unit><m:RevenueFromOperations contextRef="c" unitRef="u" precision="5">123</m:RevenueFromOperations></x:xbrl>'''
    p=parse_xbrl(xml.encode(),{'scope':'CONSOLIDATED','period':'Quarterly','cumulative':'Non-cumulative'})
    r=XbrlNormalizer().normalize(envelope('NSE_XBRL','TCS',p));assert r.eligible
    assert '00123' in r.facts[0]['dimensions'][0]['typed_xml']
    assert r.facts[0]['provenance']['precision']=='5'

def test_failed_sections_block_activation():
    p=screener_payload();p['section_status']['quarterly_results']='FAILED'
    assert not ScreenerNormalizer().normalize(message(p)).eligible


def test_failed_shareholding_does_not_block_core_financial_facts():
    p=screener_payload();p['section_status']['shareholding']='FAILED'
    r=ScreenerNormalizer().normalize(message(p))
    assert r.eligible
    issue=next(x for x in r.issues if x['locator']=='tables.shareholding')
    assert issue['code']=='FAILED' and not issue['blocking']

def test_mapping_order_is_stable():
    a=MetricDefinitions();b=MetricDefinitions(list(reversed(a.rows)))
    assert a.version==b.version

def test_producer_fallback_only_for_404(monkeypatch):
    monkeypatch.setattr('financial_ingestion.screener_http.time.sleep', lambda _: None)
    class Response:
        content=b'<html><h1>ACC</h1><section id="profit-loss"><table class="data-table"><thead><tr><th></th><th>Mar 2025</th></tr></thead><tbody><tr><td>Sales</td><td>1</td></tr></tbody></table></section></html>'
        def __init__(self,status,url):self.status_code=status;self.url=url
        def close(self):pass
        def raise_for_status(self):
            if self.status_code>=400:raise RuntimeError('HTTP error')
    class Session:
        def __init__(self,code):self.code=code;self.calls=[]
        def get(self,url,**kw):
            self.calls.append(url);return Response(self.code if len(self.calls)==1 else 200,url)
    s=Session(404);p,_=fetch_screener(s,'ACC');assert p['scope']=='STANDALONE' and len(s.calls)==2
    # Transient 429/5xx retry/cooldown coverage lives in test_screener_http.py.
    for code in (401,403):
        s=Session(code)
        with pytest.raises(RuntimeError):fetch_screener(s,'ACC')
        assert len(s.calls)==1

def test_invalid_http_200_page():
    with pytest.raises(PermanentError):parse_screener(b'<html>Login required</html>','https://www.screener.in/company/ACC/','ACC')

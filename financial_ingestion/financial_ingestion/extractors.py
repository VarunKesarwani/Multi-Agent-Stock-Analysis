"""Structural extraction only. No financial amount/period normalization."""
import re
from urllib.parse import urlparse, unquote
from lxml import etree, html
from .contract import PermanentError, SECTIONS

XI='http://www.w3.org/2001/XMLSchema-instance'
XB='http://www.xbrl.org/2003/instance'
XD='http://xbrl.org/2006/xbrldi'

def qname(text,node):
    if not text: raise PermanentError('Missing QName')
    if ':' in text:
        prefix,local=text.split(':',1); namespace=node.nsmap.get(prefix)
        if namespace is None: raise PermanentError('Unresolved QName prefix')
        return f'{{{namespace}}}{local}'
    namespace=node.nsmap.get(None)
    return f'{{{namespace}}}{text}' if namespace else text

def parse_xbrl(xml_bytes,filing_metadata,source_url=None):
    if b'<!DOCTYPE' in xml_bytes.upper() or b'<!ENTITY' in xml_bytes.upper():
        raise PermanentError('DTD/entity declarations forbidden')
    root=etree.fromstring(xml_bytes,etree.XMLParser(resolve_entities=False,no_network=True))
    if root.tag!=f'{{{XB}}}xbrl': raise PermanentError('Expected XBRL instance')
    ns={'x':XB,'d':XD}; contexts=[]; units=[]; facts=[]
    for node in root.findall(f'{{{XB}}}context'):
        identifiers=[dict(scheme=x.get('scheme'),value=x.text or '') for x in node.findall(f'.//{{{XB}}}identifier')]
        per=node.find(f'{{{XB}}}period'); dates={}
        if per is not None:
            for x in per: dates[{'startDate':'start','endDate':'end'}.get(etree.QName(x).localname,etree.QName(x).localname)]=x.text
        dims=[]
        for x in node.xpath('.//d:explicitMember | .//d:typedMember',namespaces=ns):
            d=dict(axis=qname(x.get('dimension'),x),kind=etree.QName(x).localname)
            if d['kind']=='explicitMember': d['member']=qname((x.text or '').strip(),x)
            else:
                # Preserve typed XML plus all local namespace bindings, including QName text.
                d['typed_xml']=''.join(etree.tostring(c,method='c14n').decode() for c in x)
                d['namespaces']={k or '':v for k,v in x.nsmap.items()}
            dims.append(d)
        extra=node.xpath('.//x:scenario/*[not(self::d:explicitMember or self::d:typedMember)] | .//x:segment/*[not(self::d:explicitMember or self::d:typedMember)]',namespaces=ns)
        contexts.append(dict(id=node.get('id'),identifiers=identifiers,period=dates,dimensions=dims,
                             unresolved_structure=bool(extra),raw_xml=etree.tostring(node).decode()))
    for node in root.findall(f'{{{XB}}}unit'):
        direct=node.findall(f'{{{XB}}}measure')
        numerator=direct or node.findall(f'{{{XB}}}divide/{{{XB}}}unitNumerator/{{{XB}}}measure')
        denominator=node.findall(f'{{{XB}}}divide/{{{XB}}}unitDenominator/{{{XB}}}measure')
        units.append(dict(id=node.get('id'),numerator=[qname(x.text,x) for x in numerator],denominator=[qname(x.text,x) for x in denominator],raw_xml=etree.tostring(node).decode()))
    for node in root.iter():
        if not isinstance(node.tag,str) or node.get('contextRef') is None: continue
        q=etree.QName(node)
        facts.append(dict(occurrence_id=root.getroottree().getpath(node),namespace=q.namespace or '',local_name=q.localname,
                          qualified_tag=node.tag,contextRef=node.get('contextRef'),unitRef=node.get('unitRef'),
                          decimals=node.get('decimals'),precision=node.get('precision'),nil=node.get(f'{{{XI}}}nil') in ('true','1'),
                          value=''.join(node.itertext()),attributes=dict(node.attrib),namespaces={k or '':v for k,v in node.nsmap.items()}))
    return dict(filing_metadata=filing_metadata,document=dict(root_tag=root.tag,source_url=source_url),
                namespaces={k or '':v for k,v in root.nsmap.items()},contexts=contexts,units=units,facts=facts)

def clean(node):
    return ' '.join(''.join(node.itertext()).split())

def parse_screener(page,final_url,requested_symbol):
    u=urlparse(final_url); parts=[unquote(x) for x in u.path.split('/') if x]
    if u.hostname not in ('www.screener.in','screener.in') or len(parts) not in (2,3) or parts[0]!='company':
        raise PermanentError('Unexpected Screener URL')
    if parts[1].upper()!=requested_symbol.strip().upper(): raise PermanentError('Redirected to different company')
    if len(parts)==3 and parts[2]!='consolidated': raise PermanentError('Unexpected reporting scope URL')
    scope='CONSOLIDATED' if len(parts)==3 else 'STANDALONE'
    root=html.fromstring(page)
    if not root.xpath('//h1') or not root.xpath('//section[@id="profit-loss"]//table'):
        raise PermanentError('Unexpected page; financial company page not detected')
    tables={}; status={}; errors={}
    for section,key in [('profit-loss','profit_loss'),('quarters','quarterly_results'),('balance-sheet','balance_sheet'),('cash-flow','cash_flows'),('ratios','ratios_table'),('shareholding','shareholding')]:
        nodes=root.xpath(f'//section[@id="{section}"]')
        if not nodes: status[key]='NOT_AVAILABLE'; continue
        try:
            ts=nodes[0].xpath('.//table[contains(concat(" ",normalize-space(@class)," ")," data-table ")]')
            if len(ts)!=1: raise ValueError('Expected one financial table')
            t=ts[0]; headers=t.xpath('.//thead/tr')
            if len(headers)!=1: raise ValueError('Unsupported header layout')
            cells=headers[0].xpath('./th|./td'); columns=[clean(x) for x in cells[1:]]
            if not columns or len(columns)!=len(set(columns)): raise ValueError('Missing/duplicate column labels')
            rows=[]
            for tr in t.xpath('.//tbody/tr'):
                cells=tr.xpath('./td|./th')
                if not cells: continue
                if any(x.get('colspan','1')!='1' or x.get('rowspan','1')!='1' for x in cells): raise ValueError('Unsupported merged cells')
                if len(cells)!=len(columns)+1: raise ValueError('Row/column count mismatch')
                rows.append(dict(label=clean(cells[0]),values=[clean(x) for x in cells[1:]]))
            if not rows: raise ValueError('No financial rows')
            headings=nodes[0].xpath('./div//p | ./p')
            unit_labels=[clean(x) for x in headings if re.search(r'\b(?:Rs\.?|INR|rupees)\b|₹',clean(x),re.I)]
            tables[key]=dict(unit_label=' | '.join(unit_labels) or None,columns=columns,rows=rows)
            status[key]='COLLECTED'
        except ValueError as ex:
            status[key]='FAILED'; errors[key]=str(ex)
    return dict(scope=scope,source_url=final_url,identity=dict(symbol=parts[1].upper(),name=clean(root.xpath('//h1')[0]),evidence='final company URL'),
                tables=tables,section_status=status,section_errors=errors)

def fetch_screener(session,symbol,settings=None):
    from .screener_http import get_screener_page
    from .settings import Settings
    settings = settings or Settings()
    symbol=symbol.strip().upper()
    url=f'https://www.screener.in/company/{symbol}/consolidated/'
    response=get_screener_page(session,url,settings)
    # Only an explicit missing page triggers standalone retry. Never 401/403/429/5xx.
    if response.status_code==404:
        response.close()
        response=get_screener_page(session,f'https://www.screener.in/company/{symbol}/',settings)
    response.raise_for_status()
    return parse_screener(response.content,response.url,symbol),response.content

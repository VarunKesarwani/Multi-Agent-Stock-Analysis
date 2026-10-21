"""Immutable staged datasets, transactional head selection and completion.
Readers must use a head pointer, never query staged facts as current.
"""
from bson import BSON
from pymongo import MongoClient, UpdateOne, ASCENDING
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern
from .contract import digest, parse_utc, utcnow, PermanentError
from .mappings import MetricDefinitions

COLLECTIONS=('screener_snapshots','financial_filings','financial_facts','metric_definitions','ingestion_runs')

def connect(uri,name):
    client=MongoClient(uri,serverSelectionTimeoutMS=5000,tz_aware=True)
    client.admin.command('ping')
    return client[name]

def initialize(db,definitions=None):
    definitions=definitions or MetricDefinitions()
    schemas={
      'financial_facts':dict(bsonType='object',required=['_id','dataset_id','fact_version_key','logical_fact_key','value','period_end','validation_status','source','symbol','scope','schema_version'],properties={
        'value':{'bsonType':'decimal'},'period_end':{'bsonType':'date'},'period_start':{'bsonType':['date','null']},
        'observed_at':{'bsonType':'date'},'created_at':{'bsonType':'date'},'source':{'enum':['SCREENER','NSE_XBRL']},
        'scope':{'enum':['STANDALONE','CONSOLIDATED']},'validation_status':{'enum':['VALID']},'schema_version':{'enum':[1]}}),
      'ingestion_runs':dict(bsonType='object',required=['_id','status','dataset_id']),
      'metric_definitions':dict(bsonType='object',required=['_id','mapping_set_version','source','metric','approved']),
      'screener_snapshots':dict(bsonType='object',required=['_id','kind']),
      'financial_filings':dict(bsonType='object',required=['_id','kind'])}
    for name in COLLECTIONS:
        validator={'$jsonSchema':schemas[name]}
        if name not in db.list_collection_names(): db.create_collection(name,validator=validator)
        else: db.command('collMod',name,validator=validator,validationLevel='strict')
    db.financial_facts.create_index('fact_version_key',unique=True)
    db.financial_facts.create_index([('dataset_id',1),('statement',1),('period_end',1)])
    db.financial_facts.create_index([('symbol',1),('source',1),('scope',1),('metric',1),('period_end',1)])
    db.ingestion_runs.create_index([('dataset_id',1),('status',1)])
    for name in ('screener_snapshots','financial_filings'):
        db[name].create_index([('kind',1),('symbol',1),('source',1),('scope',1)])
    for row in definitions.rows:
        key=digest([definitions.version,row['source'],row['statement'],row['source_label']])
        db.metric_definitions.update_one({'_id':key},{'$setOnInsert':dict(row,mapping_set_version=definitions.version)},upsert=True)

def load_definitions(db,version):
    rows=list(db.metric_definitions.find({'mapping_set_version':version}).sort('_id',1))
    if not rows: raise RuntimeError('Initialize the requested mapping set first')
    rows=[{k:v for k,v in r.items() if k not in ('_id','mapping_set_version')} for r in rows]
    # Ordering is canonicalized in MetricDefinitions.
    definitions=MetricDefinitions(rows)
    if definitions.version!=version: raise RuntimeError('Mapping set digest mismatch')
    return definitions

class IngestionRunRepository:
    def __init__(self,db): self.db=db
    def register(self,e,dataset_id):
        receipt_id='receipt:'+e['message_id']
        receipt_hash=digest([e['source'],e['symbol'],e['source_document_id'],e['content_hash']])
        self.db.ingestion_runs.update_one({'_id':receipt_id},{'$setOnInsert':dict(status='RECEIVED',dataset_id=dataset_id,receipt_hash=receipt_hash)},upsert=True)
        receipt=self.db.ingestion_runs.find_one({'_id':receipt_id})
        if receipt['receipt_hash']!=receipt_hash: raise PermanentError('Message ID reused with different source content')
        run_id=digest([e['message_id'],dataset_id])
        old=self.db.ingestion_runs.find_one({'_id':run_id})
        if old and old['content_hash']!=e['content_hash']: raise PermanentError('Message ID reused with different payload')
        self.db.ingestion_runs.update_one({'_id':run_id},{'$setOnInsert':dict(status='PROCESSING',dataset_id=dataset_id,content_hash=e['content_hash'],message_id=e['message_id'],symbol=e['symbol'],source=e['source'],started_at=utcnow()),'$inc':{'attempts':1}},upsert=True)
        return run_id,self.db.ingestion_runs.find_one({'_id':run_id})

class MongoFinancialRepository:
    def __init__(self,db,batch_size=250):
        self.db=db; self.batch_size=batch_size
        if batch_size<1: raise ValueError('Batch size must be positive')
    @staticmethod
    def dataset_id(e,normalizer):
        return digest([e['source'],e['symbol'],e['source_document_id'],e['content_hash'],normalizer.version,normalizer.definitions.version,1])
    def persist(self,e,result,normalizer,run_id,dataset_id,publication_revision=1):
        name='screener_snapshots' if e['source']=='SCREENER' else 'financial_filings'
        collection=self.db[name]; scope=e['payload'].get('scope') or e['payload'].get('filing_metadata',{}).get('scope')
        if scope not in ('CONSOLIDATED','STANDALONE'): scope='UNRESOLVED'
        if e['source']=='SCREENER':
            selection=['SCREENER',e['symbol'],scope]
            rank_time=parse_utc(e['extracted_at'])
        else:
            meta=e['payload']['filing_metadata']
            selection=['NSE_XBRL',e['symbol'],scope,meta.get('fromDate'),meta.get('toDate'),meta.get('period'),meta.get('cumulative')]
            try: rank_time=parse_utc(meta.get('filed_at'))
            except PermanentError:
                rank_time=parse_utc(e['extracted_at'])
                result.issue('filing_metadata.filed_at','Using extraction time for filing selection','ORDERING',False)
        head_id='head:'+digest(selection)
        # All records are immutable until the small transaction below publishes their pointer.
        source=dict(kind='dataset',symbol=e['symbol'],source=e['source'],scope=scope,envelope=e,
                    dataset_id=dataset_id,normalization_version=normalizer.version,mapping_version=normalizer.definitions.version,
                    counts=dict(valid=len(result.facts),issues=len(result.issues),disclosures=len(result.disclosures)),
                    eligible=result.eligible,created_at=utcnow())
        if len(BSON.encode(source))>15_000_000: raise PermanentError('Source dataset exceeds BSON safety limit')
        collection.update_one({'_id':dataset_id},{'$setOnInsert':source},upsert=True)
        # Chunk diagnostics separately so large issue sets cannot exceed Mongo's document limit.
        for kind,items in [('issues',result.issues),('disclosures',result.disclosures)]:
            for i in range(0,len(items),self.batch_size):
                collection.update_one({'_id':f'{dataset_id}:{kind}:{i}'},{'$setOnInsert':dict(kind=kind,dataset_id=dataset_id,items=items[i:i+self.batch_size])},upsert=True)
        for i in range(0,len(result.facts),self.batch_size):
            writes=[UpdateOne({'_id':f['fact_version_key']},{'$setOnInsert':dict(f,dataset_id=dataset_id)},upsert=True) for f in result.facts[i:i+self.batch_size]]
            self.db.financial_facts.bulk_write(writes,ordered=False)
        # A sentinel exists before transactions, so concurrent first publishers write the same document.
        collection.update_one({'_id':head_id},{'$setOnInsert':dict(kind='head',symbol=e['symbol'],source=e['source'],scope=scope,dataset_id=None,rank_time=None,publication_revision=0)},upsert=True)
        def activate(session=None):
            run=self.db.ingestion_runs.find_one({'_id':run_id},session=session)
            if run.get('status')=='COMPLETED': return
            head=collection.find_one({'_id':head_id},session=session)
            selected=False; reason='validation_blocked'
            if result.eligible:
                old=head.get('rank_time')
                # Same payload replay can use an explicitly increasing publication revision.
                newer=(old is None or rank_time>old) and publication_revision>=head.get('publication_revision',0)
                replay=old is not None and head.get('source_document_id')==e['source_document_id'] and head.get('content_hash')==e['content_hash'] and publication_revision>head.get('publication_revision',0)
                if newer or replay:
                    collection.update_one({'_id':head_id},{'$set':dict(dataset_id=dataset_id,rank_time=max(rank_time,old) if old else rank_time,content_hash=e['content_hash'],source_document_id=e['source_document_id'],publication_revision=publication_revision)},session=session)
                    selected=True; reason='selected'
                elif head.get('dataset_id')==dataset_id: reason='already_selected'
                else: reason='older_or_ambiguous_order'
            self.db.ingestion_runs.update_one({'_id':run_id},{'$set':dict(status='COMPLETED',completed_at=utcnow(),eligible=result.eligible,selected=selected,selection_reason=reason,counts=source['counts'],head_id=head_id)},session=session)
        # Idempotent writes make this usable with a personal standalone MongoDB.
        activate()
    def current_facts(self,symbol,source,scope,statement=None,metric=None):
        name='screener_snapshots' if source=='SCREENER' else 'financial_filings'
        # Immutable dataset IDs make a pointer read followed by a facts query safe.
        ids=[x['dataset_id'] for x in self.db[name].find(dict(kind='head',symbol=symbol,source=source,scope=scope)) if x.get('dataset_id')]
        query=dict(dataset_id={'$in':ids},validation_status='VALID')
        if statement: query['statement']=statement
        if metric: query['metric']=metric
        return self.db.financial_facts.find(query).sort('period_end',ASCENDING)

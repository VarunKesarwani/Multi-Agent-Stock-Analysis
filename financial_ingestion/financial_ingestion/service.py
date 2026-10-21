from .contract import MessageValidator, PermanentError
from .normalizers import ScreenerNormalizer, XbrlNormalizer
from .repository import IngestionRunRepository, MongoFinancialRepository

class ConsumerService:
    def __init__(self,db,definitions,settings):
        self.validator=MessageValidator(settings.max_message_bytes)
        self.normalizers={'SCREENER':ScreenerNormalizer(definitions,settings.normalization_version),
                          'NSE_XBRL':XbrlNormalizer(definitions,settings.normalization_version)}
        self.runs=IngestionRunRepository(db); self.repository=MongoFinancialRepository(db,settings.batch_size)
        self.revision=settings.publication_revision
    def process(self,envelope,expected_source=None):
        e=self.validator.validate(envelope)
        if expected_source and e['source']!=expected_source: raise PermanentError('Source does not match queue')
        n=self.normalizers[e['source']]; dataset=self.repository.dataset_id(e,n)
        run_id,run=self.runs.register(e,dataset)
        if run['status']=='COMPLETED': return run
        result=n.normalize(e)
        self.repository.persist(e,result,n,run_id,dataset,self.revision)
        return self.runs.db.ingestion_runs.find_one({'_id':run_id})

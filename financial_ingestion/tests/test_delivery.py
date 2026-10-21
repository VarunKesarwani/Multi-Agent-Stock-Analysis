from types import SimpleNamespace
import pytest
from pymongo.errors import AutoReconnect
from financial_ingestion.archive import Archive
from financial_ingestion.contract import loads, PermanentError
from financial_ingestion.broker import dispatch_delivery
from financial_ingestion.settings import Settings
from test_normalization import message

class Channel:
    def __init__(self,fail=False):self.calls=[];self.fail=fail
    def basic_publish(self,**kw):
        self.calls.append(('publish',kw))
        if self.fail:raise RuntimeError('Broker unavailable')
    def basic_ack(self,tag):self.calls.append(('ack',tag))

def test_archive_reuses_original_message_and_resumes(tmp_path):
    a=Archive(tmp_path);e=message();a.enqueue(e);a.close()
    b=Archive(tmp_path);rows=list(b.pending());assert len(rows)==1 and loads(rows[0][1])['message_id']==e['message_id']
    b.enqueue(e);assert len(list(b.pending()))==1
    b.mark(e['message_id'],'PUBLISHED');assert not list(b.pending());b.close()

def test_mongo_down_schedules_delayed_retry_before_ack():
    ch=Channel();m=SimpleNamespace(delivery_tag=7);p=SimpleNamespace(headers={},message_id='id')
    dispatch_delivery(ch,m,p,b'original','screener',Settings(),AutoReconnect('database unavailable'))
    assert [x[0] for x in ch.calls]==['publish','ack']
    assert ch.calls[0][1]['routing_key']=='financial.screener.retry.5'
    assert ch.calls[0][1]['body']==b'original' and ch.calls[0][1]['mandatory']

def test_handoff_failure_never_acks():
    ch=Channel(fail=True)
    with pytest.raises(RuntimeError):dispatch_delivery(ch,SimpleNamespace(delivery_tag=7),SimpleNamespace(headers={},message_id='id'),b'x','screener',Settings(),AutoReconnect())
    assert not any(x[0]=='ack' for x in ch.calls)

def test_permanent_and_exhausted_go_to_failed():
    for error,attempt in [(PermanentError('bad contract'),0),(AutoReconnect(),3)]:
        ch=Channel();dispatch_delivery(ch,SimpleNamespace(delivery_tag=1),SimpleNamespace(headers={'processing_attempt':attempt},message_id='id'),b'x','xblr',Settings(),error)
        assert ch.calls[0][1]['exchange']=='financial.ingestion.failed'
        assert loads(ch.calls[0][1]['body'])['original_body_base64']=='eA=='

def test_success_ack_only():
    ch=Channel();dispatch_delivery(ch,SimpleNamespace(delivery_tag=9),SimpleNamespace(),b'x','xblr',Settings())
    assert ch.calls==[('ack',9)]

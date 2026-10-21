"""Opt-in real replica-set tests; unique disposable test database per test."""
import os
import uuid
from copy import deepcopy
from dataclasses import replace
import pytest
from financial_ingestion.repository import connect, initialize, MongoFinancialRepository
from financial_ingestion.mappings import MetricDefinitions
from financial_ingestion.service import ConsumerService
from financial_ingestion.settings import Settings
from financial_ingestion.contract import digest
from test_normalization import message

pytestmark=pytest.mark.integration

@pytest.fixture
def db():
    uri=os.getenv('TEST_MONGO_URI')
    if not uri: pytest.skip('Set TEST_MONGO_URI to a disposable MongoDB replica set')
    database=connect(uri,'ingestion_test_'+uuid.uuid4().hex)
    initialize(database)
    yield database
    database.client.drop_database(database.name)
    database.client.close()

def test_commit_before_ack_redelivery_and_partial_does_not_activate(db):
    s=ConsumerService(db,MetricDefinitions(),Settings())
    e=message();s.process(e) # Simulate lost ACK after commit.
    count=db.financial_facts.count_documents({})
    s.process(e)
    assert db.financial_facts.count_documents({})==count
    head=db.screener_snapshots.find_one({'kind':'head'})
    bad=message();bad['payload']['tables']['profit_loss']['unit_label']=None;bad['content_hash']=digest(bad['payload'])
    s.process(bad)
    assert db.screener_snapshots.find_one({'kind':'head'})['dataset_id']==head['dataset_id']

def test_out_of_order_and_new_normalization_version(db):
    e=message();e['extracted_at']='2026-09-22T00:00:00Z'
    s=ConsumerService(db,MetricDefinitions(),Settings());s.process(e)
    before=db.screener_snapshots.find_one({'kind':'head'})
    old=message();old['extracted_at']='2026-09-21T00:00:00Z';old['payload']['tables']['profit_loss']['rows'][0]['values'][0]='42';old['content_hash']=digest(old['payload']);old['source_document_id']='older-source'
    s.process(old)
    assert db.screener_snapshots.find_one({'kind':'head'})['dataset_id']==before['dataset_id']
    s2=ConsumerService(db,MetricDefinitions(),replace(Settings(),normalization_version='2.0.0',publication_revision=2))
    s2.process(e)
    assert db.screener_snapshots.find_one({'kind':'head'})['dataset_id']!=before['dataset_id']
    assert len(list(MongoFinancialRepository(db).current_facts('ACC','SCREENER','CONSOLIDATED')))==2

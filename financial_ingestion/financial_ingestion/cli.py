import argparse
import json
import logging
import os
from pathlib import Path
from bson import json_util
from .contract import loads, envelope, MessageValidator
from .settings import Settings
from .mappings import MetricDefinitions
from .normalizers import ScreenerNormalizer, XbrlNormalizer

def main():
    p=argparse.ArgumentParser(description='Reported financial ingestion')
    sub=p.add_subparsers(dest='command',required=True)
    n=sub.add_parser('normalize'); n.add_argument('envelope'); n.add_argument('--output',required=True); n.add_argument('--mappings')
    sub.add_parser('init-mongo').add_argument('--mappings'); sub.add_parser('init-rabbit'); sub.add_parser('consume').add_argument('--mappings'); sub.add_parser('publish-pending')
    x=sub.add_parser('process-file'); x.add_argument('envelope'); x.add_argument('--mappings')
    x=sub.add_parser('replay-archive'); x.add_argument('message_id')
    x=sub.add_parser('replay-failed'); x.add_argument('route',choices=['screener','xblr']); x.add_argument('--limit',type=int,default=1)
    args=p.parse_args(); settings=Settings.from_env(); logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    definitions=MetricDefinitions(json.loads(Path(args.mappings).read_text()) if getattr(args,'mappings',None) else None)
    if args.command=='normalize':
        e=MessageValidator(settings.max_message_bytes).validate(loads(Path(args.envelope).read_bytes()))
        normalizer=(ScreenerNormalizer if e['source']=='SCREENER' else XbrlNormalizer)(definitions,settings.normalization_version)
        r=normalizer.normalize(e)
        Path(args.output).write_text(json_util.dumps(dict(facts=r.facts,issues=r.issues,disclosures=r.disclosures,eligible=r.eligible),indent=2))
        print(f'valid={len(r.facts)} issues={len(r.issues)} disclosures={len(r.disclosures)} eligible={r.eligible}')
    elif args.command in ('init-rabbit','publish-pending','replay-failed','replay-archive'):
        from .broker import initialize_topology,flush_outbox,replay_failed,publish,connection,EXCHANGE
        from .contract import SOURCES,canonical
        if args.command=='init-rabbit': initialize_topology(settings)
        elif args.command=='replay-failed': replay_failed(settings,args.route,args.limit)
        else:
            from .archive import Archive
            a=Archive(settings.archive_dir)
            try:
                if args.command=='publish-pending': flush_outbox(a,settings)
                else:
                    e=a.get(args.message_id)
                    # Explicit replay retains original envelope/identity and has its own confirm.
                    c=connection(settings)
                    try:
                        ch=c.channel();ch.confirm_delivery();publish(ch,EXCHANGE,SOURCES[e['source']],canonical(e),e['message_id'])
                    finally: c.close()
            finally:a.close()
    else:
        from .repository import connect,initialize,load_definitions
        from .service import ConsumerService
        if not settings.mongo_uri: raise ValueError('MONGO_URI is required')
        db=connect(settings.mongo_uri,settings.mongo_database)
        try:
            if args.command=='init-mongo':initialize(db,definitions)
            else:
                definitions=load_definitions(db,definitions.version)
                service=ConsumerService(db,definitions,settings)
                if args.command=='process-file':
                    print(json_util.dumps(service.process(loads(Path(args.envelope).read_bytes())),indent=2))
                else:
                    from .broker import consume
                    consume(service,settings)
        finally:db.client.close()

if __name__=='__main__':main()

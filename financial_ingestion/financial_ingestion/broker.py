import base64
from concurrent.futures import ThreadPoolExecutor
import logging
import threading
import time
import pika
from pymongo.errors import ConnectionFailure, ExecutionTimeout, AutoReconnect, OperationFailure
from .contract import SOURCES, PermanentError, MessageValidator, loads, canonical, utc_text

LOG=logging.getLogger(__name__)
EXCHANGE='financial.ingestion'
FAILED='financial.ingestion.failed'

def queue_name(route): return f'financial.{route}.normalize'

def connection(settings):
    if not settings.rabbit_url: raise ValueError('RABBITMQ_URL is required')
    p=pika.URLParameters(settings.rabbit_url)
    p.heartbeat=60; p.blocked_connection_timeout=60; p.socket_timeout=15
    return pika.BlockingConnection(p)

def initialize_topology(settings):
    c=connection(settings)
    try:
        ch=c.channel(); ch.exchange_declare(EXCHANGE,'topic',durable=True); ch.exchange_declare(FAILED,'topic',durable=True)
        for route in SOURCES.values():
            ch.queue_declare(queue_name(route),durable=True,arguments={'x-queue-type':'quorum','x-single-active-consumer':True,'x-dead-letter-exchange':FAILED,'x-dead-letter-routing-key':route,'x-dead-letter-strategy':'at-least-once','x-overflow':'reject-publish'})
            ch.queue_bind(queue_name(route),EXCHANGE,route)
            fq=f'financial.{route}.failed'
            ch.queue_declare(fq,durable=True,arguments={'x-queue-type':'quorum'})
            ch.queue_bind(fq,FAILED,route)
            for delay in sorted(set(settings.retry_delays)):
                rq=f'financial.{route}.retry.{delay}'
                ch.queue_declare(rq,durable=True,arguments={'x-queue-type':'quorum','x-message-ttl':delay*1000,
                    'x-dead-letter-exchange':EXCHANGE,'x-dead-letter-routing-key':route,
                    'x-dead-letter-strategy':'at-least-once','x-overflow':'reject-publish'})
    finally: c.close()

def publish(ch,exchange,route,body,message_id,headers=None):
    ch.basic_publish(exchange=exchange,routing_key=route,body=body,mandatory=True,
        properties=pika.BasicProperties(content_type='application/json',delivery_mode=2,message_id=message_id,headers=headers or {}))

def flush_outbox(archive,settings):
    for mid,body in list(archive.pending()):
        e=MessageValidator(settings.max_message_bytes).validate(loads(body))
        for attempt in range(settings.max_attempts):
            c=None
            try:
                c=connection(settings); ch=c.channel(); ch.confirm_delivery()
                publish(ch,EXCHANGE,SOURCES[e['source']],body,mid)
                archive.mark(mid,'PUBLISHED')
                LOG.info('published symbol=%s message_id=%s source_document_id=%s',e['symbol'],mid,e['source_document_id'])
                break
            except (pika.exceptions.AMQPError,OSError) as ex:
                archive.mark(mid,'PENDING',type(ex).__name__)
                if attempt+1==settings.max_attempts: raise RuntimeError('Publication exhausted; envelope remains in durable outbox') from None
                time.sleep(settings.retry_delays[min(attempt,len(settings.retry_delays)-1)])
            finally:
                if c and c.is_open: c.close()

def transient(error):
    if isinstance(error,(ConnectionFailure,ExecutionTimeout,AutoReconnect,OSError)): return True
    if isinstance(error,OperationFailure):
        return error.has_error_label('TransientTransactionError') or error.has_error_label('UnknownTransactionCommitResult')
    return False

def safe_reason(error):
    # Driver exceptions can contain connection details. Do not archive/log their raw text.
    return str(error) if isinstance(error,PermanentError) else type(error).__name__

def failure_body(body,error):
    return canonical(dict(failed_at=utc_text(),reason=safe_reason(error),original_body_base64=base64.b64encode(body).decode()))

def dispatch_delivery(ch,method,properties,body,route,settings,error=None):
    """Runs on connection thread, after worker finishes. Failure publication must confirm before ACK."""
    if error is None:
        ch.basic_ack(method.delivery_tag); return
    LOG.error('Processing failed route=%s message_id=%s reason=%s',route,properties.message_id,safe_reason(error))
    attempts=int((properties.headers or {}).get('processing_attempt',0))
    if transient(error) and attempts+1<settings.max_attempts:
        delay=settings.retry_delays[min(attempts,len(settings.retry_delays)-1)]
        publish(ch,'',f'financial.{route}.retry.{delay}',body,properties.message_id,
                headers={'processing_attempt':attempts+1})
    else:
        publish(ch,FAILED,route,failure_body(body,error),properties.message_id)
    ch.basic_ack(method.delivery_tag)

def consume_source(source,service,settings,stop):
    route=SOURCES[source]
    while not stop.is_set():
        c=None
        # One worker per source. Connection thread remains free to service heartbeats.
        pool=ThreadPoolExecutor(max_workers=1)
        futures=set()
        try:
            c=connection(settings); ch=c.channel(); ch.confirm_delivery(); ch.basic_qos(prefetch_count=settings.prefetch)
            def received(channel,method,properties,body):
                def work():
                    if len(body)>settings.max_message_bytes: raise PermanentError('Message size limit exceeded')
                    return service.process(loads(body),source)
                future=pool.submit(work); futures.add(future)
                def done(f):
                    def finish():
                        try:
                            dispatch_delivery(channel,method,properties,body,route,settings,f.exception())
                        except Exception:
                            # No ACK on handoff failure: closing returns delivery to original queue.
                            if c.is_open: c.close()
                        finally: futures.discard(f)
                    try: c.add_callback_threadsafe(finish)
                    except pika.exceptions.ConnectionWrongStateError: pass
                future.add_done_callback(done)
            ch.basic_consume(queue=queue_name(route),on_message_callback=received,auto_ack=False)
            while c.is_open and not stop.is_set(): c.process_data_events(time_limit=1)
        except (pika.exceptions.AMQPError,OSError):
            LOG.warning('Broker connection unavailable for source=%s; reconnecting',source)
        finally:
            if c and c.is_open: c.close()
            pool.shutdown(wait=True,cancel_futures=True)
        stop.wait(settings.retry_delays[0])

def consume(service,settings):
    stop=threading.Event()
    threads=[threading.Thread(target=consume_source,args=(s,service,settings,stop),daemon=True) for s in SOURCES]
    for t in threads: t.start()
    try:
        while all(t.is_alive() for t in threads): stop.wait(1)
    except KeyboardInterrupt: pass
    finally:
        stop.set()
        for t in threads: t.join()

def replay_failed(settings,route,limit=1):
    if route not in SOURCES.values(): raise ValueError('Invalid route')
    c=connection(settings)
    try:
        ch=c.channel(); ch.confirm_delivery()
        for _ in range(limit):
            method,props,body=ch.basic_get(f'financial.{route}.failed',auto_ack=False)
            if method is None: break
            failed=loads(body)
            original=base64.b64decode(failed['original_body_base64'],validate=True) if 'original_body_base64' in failed else body
            e=MessageValidator(settings.max_message_bytes).validate(loads(original))
            if SOURCES[e['source']]!=route: raise PermanentError('Failed queue/source mismatch')
            publish(ch,EXCHANGE,route,original,e['message_id'],headers={'processing_attempt':0})
            ch.basic_ack(method.delivery_tag)
    finally: c.close()

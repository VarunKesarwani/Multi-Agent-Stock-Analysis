import os
import math
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    rabbit_url: str = ''
    mongo_uri: str = ''
    mongo_database: str = 'financial_ingestion'
    archive_dir: str = 'archive'
    max_attempts: int = 4
    retry_delays: tuple = (5, 30, 120)
    prefetch: int = 1
    batch_size: int = 250
    max_message_bytes: int = 8_000_000
    normalization_version: str = '1.0.0'
    publication_revision: int = 1
    screener_request_delay: float = 100.0
    screener_request_jitter: float = 5.0
    screener_max_attempts: int = 3
    screener_backoff: float = 30.0
    screener_max_backoff: float = 120.0
    screener_failure_cooldown: float = 300.0

    def __post_init__(self):
        values = (self.screener_request_delay, self.screener_backoff,
                  self.screener_max_backoff, self.screener_failure_cooldown)
        if any(not math.isfinite(x) or x <= 0 for x in values):
            raise ValueError('Screener delays must be finite and positive')
        if not math.isfinite(self.screener_request_jitter) or self.screener_request_jitter < 0:
            raise ValueError('Screener jitter must be finite and non-negative')
        if not 1 <= self.screener_max_attempts <= 10:
            raise ValueError('SCREENER_MAX_ATTEMPTS must be between 1 and 10')
        if self.screener_max_backoff < self.screener_backoff:
            raise ValueError('SCREENER_MAX_BACKOFF_SECONDS must be >= SCREENER_BACKOFF_SECONDS')

    @classmethod
    def from_env(cls):
        # Notebook kernels may start in a different directory. Container-provided
        # values take precedence over the local development .env file.
        load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)

        # Credentials are authoritative when provided. A stale URL in a notebook
        # environment must not silently replace the configured broker account.
        rabbit_user = os.getenv('RABBITMQ_USER')
        rabbit_password = os.getenv('RABBITMQ_PASSWORD')
        if rabbit_user and rabbit_password:
            user = quote(rabbit_user, safe='')
            password = quote(rabbit_password, safe='')
            host = os.getenv('RABBITMQ_HOST', '127.0.0.1')
            rabbit_url = f'amqp://{user}:{password}@{host}:5672/%2F'
        else:
            rabbit_url = os.getenv('RABBITMQ_URL', '')

        result = cls(
            rabbit_url=rabbit_url,
            mongo_uri=os.getenv('MONGO_URI', ''),
            mongo_database=os.getenv('MONGO_DATABASE', 'financial_ingestion'),
            archive_dir=os.getenv('ARCHIVE_DIR', 'archive'),
            max_attempts=int(os.getenv('MAX_ATTEMPTS', '4')),
            retry_delays=tuple(int(x) for x in os.getenv('RETRY_DELAYS', '5,30,120').split(',')),
            prefetch=int(os.getenv('CONSUMER_PREFETCH', '1')),
            batch_size=int(os.getenv('MONGO_BATCH_SIZE', '250')),
            max_message_bytes=int(os.getenv('MAX_MESSAGE_BYTES', '8000000')),
            normalization_version=os.getenv('NORMALIZATION_VERSION', '1.0.0'),
            publication_revision=int(os.getenv('PUBLICATION_REVISION', '1')),
            screener_request_delay=float(os.getenv('SCREENER_REQUEST_DELAY_SECONDS', '100')),
            screener_request_jitter=float(os.getenv('SCREENER_REQUEST_JITTER_SECONDS', '5')),
            screener_max_attempts=int(os.getenv('SCREENER_MAX_ATTEMPTS', '3')),
            screener_backoff=float(os.getenv('SCREENER_BACKOFF_SECONDS', '30')),
            screener_max_backoff=float(os.getenv('SCREENER_MAX_BACKOFF_SECONDS', '120')),
            screener_failure_cooldown=float(os.getenv('SCREENER_FAILURE_COOLDOWN_SECONDS', '300')),
        )
        if min(result.max_attempts, result.prefetch, result.batch_size,
               result.max_message_bytes, result.publication_revision) < 1 or not result.retry_delays or min(result.retry_delays) < 1:
            raise ValueError('Positive configuration values required')
        return result

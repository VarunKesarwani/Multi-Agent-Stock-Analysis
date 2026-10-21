FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
# Include only modules required by the RabbitMQ consumer, normalization, and MongoDB persistence.
COPY financial_ingestion/__init__.py financial_ingestion/broker.py financial_ingestion/cli.py financial_ingestion/contract.py financial_ingestion/mappings.py financial_ingestion/normalizers.py financial_ingestion/repository.py financial_ingestion/service.py financial_ingestion/settings.py ./financial_ingestion/
RUN pip install --no-cache-dir .
CMD ["sh", "-c", "financial-ingestion init-rabbit && financial-ingestion init-mongo && exec financial-ingestion consume"]

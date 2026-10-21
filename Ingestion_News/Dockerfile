FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir confluent-kafka feedparser

COPY news_producer.py ./

CMD ["python", "news_producer.py"]

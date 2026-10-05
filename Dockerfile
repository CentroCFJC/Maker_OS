FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY makeros ./makeros
COPY templates ./templates

RUN pip install --no-cache-dir .

# Content and private trees are mounted; the index lives in /data.
ENV MAKEROS_CONTENT_DIR=/data/content \
    MAKEROS_PRIVATE_DIR=/data/private \
    MAKEROS_DB_PATH=/data/makeros.db

EXPOSE 8000

CMD ["uvicorn", "makeros.main:app", "--host", "0.0.0.0", "--port", "8000"]

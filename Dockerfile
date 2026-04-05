FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DION_DATA_DIR=/app/var
ENV DION_API_HOST=0.0.0.0
ENV DION_API_PORT=8000

COPY pyproject.toml README.md alembic.ini ./
COPY alembic ./alembic
COPY app ./app

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["dion-api"]

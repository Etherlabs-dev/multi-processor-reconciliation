FROM python:3.11.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN apt-get update \
    && apt-get install --no-install-recommends -y postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir ".[dev]"

COPY sql ./sql
COPY n8n ./n8n
COPY tests ./tests

EXPOSE 8000
CMD ["uvicorn", "reconciliation.service:app", "--host", "0.0.0.0", "--port", "8000"]

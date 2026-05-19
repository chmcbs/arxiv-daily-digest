FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/ api/
COPY core/ core/
COPY frontend/ frontend/
COPY scripts/ scripts/
COPY scripts/docker-entrypoint.sh /docker-entrypoint.sh
COPY scripts/worker-entrypoint.sh /worker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh /worker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends default-mysql-client libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN useradd --create-home appuser && mkdir -p storage backups ml_models && chown -R appuser /app
USER appuser
EXPOSE 8000
# Migrations run on start; the scheduler runs in this single API process.
CMD ["sh", "-c", "alembic upgrade head && python -m scripts.download_models && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]

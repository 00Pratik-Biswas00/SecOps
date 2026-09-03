FROM python:3.13-slim

# Non-root user for security
RUN addgroup --system connector && adduser --system --ingroup connector connector

WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Do not run as root
RUN chown -R connector:connector /app
USER connector

EXPOSE 8000

# Cloud Run polls /health to confirm the container is alive.
# HEALTHCHECK here is for local Docker / docker-compose — Cloud Run uses its own probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
  || exit 1

# Production: no --reload, single worker (Cloud Run scales horizontally)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

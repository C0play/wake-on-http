FROM python:3.11-slim

WORKDIR /wake-on-http

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Wakeonlan
RUN apt-get update && apt-get install -y wakeonlan && rm -rf /var/lib/apt/lists/*

COPY app/src/ ./app/src/

ENV PYTHONUNBUFFERED=1
ENV SERVER_PORT=5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request, os; port = os.getenv('SERVER_PORT', '5000'); urllib.request.urlopen(f'http://127.0.0.1:{port}/health')" || exit 1

CMD ["python", "-m", "app.src.main"]
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_HOST=0.0.0.0 APP_PORT=8000 DB_PATH=/app/state/predictions.sqlite3 MODEL_PATH=/app/models/credit_default_model.joblib
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
COPY web/ ./web/
COPY models/ ./models/
RUN mkdir -p /app/state && useradd -r -u 10001 -m appuser && chown -R appuser:appuser /app/state
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3)"
CMD ["python", "-m", "app.server"]

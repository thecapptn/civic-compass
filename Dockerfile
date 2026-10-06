FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

RUN useradd --create-home --uid 10001 civic

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY docs ./docs
COPY tests ./tests

RUN mkdir -p /srv/data && chown -R civic:civic /srv
USER civic

ENV CIVIC_COMPASS_DB=/srv/data/civic_compass.sqlite3

EXPOSE 6021

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:6021/healthz')"

CMD ["sh", "-c", "python -m app.seed --if-empty && uvicorn app.main:app --host 0.0.0.0 --port 6021"]

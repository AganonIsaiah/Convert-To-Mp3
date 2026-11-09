FROM node:22-bookworm-slim AS javascript

FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=10000 \
    MAX_CONCURRENT_JOBS=1
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app
COPY --from=javascript /usr/local/bin/node /usr/local/bin/node
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app app.py worker.py ./
COPY --chown=app:app static/ ./static/
RUN mkdir /app/.downloads && chown app:app /app/.downloads
USER app
EXPOSE 10000
CMD ["python", "app.py"]

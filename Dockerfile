FROM python:3.12-slim

ARG APP_VERSION=dev

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FORWARDED_ALLOW_IPS=* \
    APP_VERSION=${APP_VERSION}

WORKDIR /app

RUN addgroup --system homelab \
    && adduser --system --ingroup homelab homelab \
    && apt-get update \
    && apt-get install -y --no-install-recommends gosu iputils-ping nodejs npm \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY package.json .
RUN npm install --omit=dev --no-audit --no-fund

COPY app ./app
COPY scripts ./scripts
COPY docker-entrypoint.sh /usr/local/bin/homelab-entrypoint

RUN mkdir -p /app/data /app/uploads \
    && chown -R homelab:homelab /app \
    && chmod +x /usr/local/bin/homelab-entrypoint

EXPOSE 8080

ENTRYPOINT ["homelab-entrypoint"]
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8080 --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-*}\""]

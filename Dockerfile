FROM python:3.13-slim

ARG TARGETARCH
ARG SUPERCRONIC_VERSION=v0.2.34

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
        amd64) supercronic_arch="amd64" ;; \
        arm64) supercronic_arch="arm64" ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSLo /usr/local/bin/supercronic \
        "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${supercronic_arch}"; \
    chmod +x /usr/local/bin/supercronic

WORKDIR /app

COPY pyproject.toml ./
COPY bill_notify ./bill_notify
COPY deploy/run-supercronic.sh ./deploy/run-supercronic.sh

RUN python -m pip install --upgrade pip \
    && python -m pip install .

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/downloads /app/.cache/paddlex \
    && chmod +x /app/deploy/run-supercronic.sh \
    && chown -R appuser:appuser /app

USER appuser

ENTRYPOINT ["bill-notify"]

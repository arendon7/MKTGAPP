FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.title="BINARIO Marketing Cloud Social Worker" \
      com.sistemabinario.release-authority="false" \
      com.sistemabinario.physical-uat-authority="false"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/binario/src:/opt/binario

WORKDIR /opt/binario

RUN groupadd --gid 10001 binario \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin binario

# Keep the runtime surface minimal: the worker needs only its source package,
# the gateway storage/contracts, and the fail-fast one-shot wrapper.
COPY gateway ./gateway
COPY src ./src
COPY scripts/run_cloud_social_worker_once.sh ./scripts/run_cloud_social_worker_once.sh
RUN chmod 0555 ./scripts/run_cloud_social_worker_once.sh

USER 10001:10001

ENTRYPOINT ["./scripts/run_cloud_social_worker_once.sh"]

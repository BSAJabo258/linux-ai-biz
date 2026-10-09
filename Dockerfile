# check=skip=SecretsUsedInArgOrEnv
# BAU in a container: try the whole system on any computer with Docker before the laptop.
#   docker compose up -d                 Mission Control on http://localhost:8765 + Governor
#   docker compose run --rm --service-ports jarvis      talk to Jarvis (http://localhost:8766)
#   docker compose --profile glm up -d llm              free local model (GLM-4.7-Flash)
# See docker/README.md. The laptop install (two USB sticks) remains the production path:
# the container has no disk encryption, firewall or AppArmor of its own.
# Docker Hub rate-limited? --build-arg BASE=mirror.gcr.io/library/debian:trixie-slim
ARG BASE=debian:trixie-slim
FROM ${BASE}

ENV DEBIAN_FRONTEND=noninteractive \
    BAU_HOME=/var/lib/bau \
    BAU_AUDIT_KEY=/var/lib/bau/keys/audit.key \
    BAU_UNSUB_KEY=/var/lib/bau/keys/unsubscribe.key \
    BAU_ALLOWED_SIGNERS=/var/lib/bau/keys/allowed_signers \
    BAU_IN_CONTAINER=1 \
    PATH=/opt/bau/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update -q \
 && apt-get install -y -q --no-install-recommends python3 python3-venv python3-yaml ffmpeg \
      openssh-client ca-certificates tini \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE /src/
COPY src /src/src
# Behind a TLS-inspecting proxy? docker build --secret id=extra_ca,src=/path/ca.pem .
RUN --mount=type=secret,id=extra_ca,required=false \
    if [ -s /run/secrets/extra_ca ]; then export PIP_CERT=/run/secrets/extra_ca; fi \
 && python3 -m venv --system-site-packages /opt/bau/venv \
 && /opt/bau/venv/bin/pip install --no-cache-dir "/src[claude]" \
 && rm -rf /src

# One human owner account, the same role the administrator has on the laptop. BAU's
# approvals and confirmations stay with this person; nothing in the image can approve.
RUN useradd --create-home --uid 1000 --shell /bin/bash owner \
 && install -d -m 0770 -o owner -g owner /var/lib/bau
COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/bau-entrypoint
COPY --chmod=0755 docker/approver-setup.sh /usr/local/bin/bau-approver-setup
# A checkout made on Windows before .gitattributes existed still has CRLF scripts, and
# "#!/bin/sh\r" can't start; strip it so the image works from any checkout.
RUN sed -i 's/\r$//' /usr/local/bin/bau-entrypoint /usr/local/bin/bau-approver-setup

USER owner
WORKDIR /home/owner
VOLUME ["/var/lib/bau"]
EXPOSE 8765 8766
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s \
  CMD python3 -c "import urllib.request,sys; r=urllib.request.Request('http://127.0.0.1:8765/api/status', headers={'X-BAU':'1'}); sys.exit(0 if urllib.request.urlopen(r, timeout=4).status==200 else 1)" || exit 1
ENTRYPOINT ["tini", "--", "bau-entrypoint"]
CMD ["bau", "ui", "--port", "8765"]

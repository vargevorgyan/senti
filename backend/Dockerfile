FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv
# Senti runs as this unprivileged user; the entrypoint drops root right after fixing folder ownership
RUN groupadd --system --gid 10001 senti && useradd --system --uid 10001 --gid senti --no-create-home --shell /usr/sbin/nologin senti
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY docker-entrypoint.sh /usr/local/bin/senti-entrypoint
RUN chmod 0755 /usr/local/bin/senti-entrypoint && mkdir -p /data /srv /run/senti-runner
ENV SENTI_DATA_DIR=/data PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)"
ENTRYPOINT ["senti-entrypoint"]
# The backend is reachable only through the bundled nginx (its port is not published), which overwrites
# X-Forwarded-For with the real client address; so trusting forwarded headers here is safe.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]

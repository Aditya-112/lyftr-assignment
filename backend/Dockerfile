FROM python:3.13-slim-bookworm AS builder
WORKDIR /build
RUN python -m venv /opt/venv
COPY requirements.txt .
RUN /opt/venv/bin/pip install --disable-pip-version-check --no-cache-dir -r requirements.txt

FROM python:3.13-slim-bookworm AS runtime
ENV PATH="/opt/venv/bin:${PATH}" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=8000
WORKDIR /app
RUN groupadd --gid 10001 app && useradd --no-create-home --uid 10001 --gid 10001 app \
    && install -d -o app -g app /data
COPY --from=builder /opt/venv /opt/venv
COPY app/ app/
USER app
EXPOSE 8000
CMD ["python", "-m", "app"]

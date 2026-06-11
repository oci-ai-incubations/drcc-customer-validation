FROM python:3.12-slim

# WeasyPrint runtime libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
        libffi-dev libcairo2 shared-mime-info fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY manifest/ ./manifest/
COPY config/ ./config/
COPY pytest.ini .
COPY tests/ ./tests/
COPY docker-entrypoint.sh .
RUN chmod +x /app/docker-entrypoint.sh

ENV PYTHONPATH=/app/src
ENV OCI_ENV=dev
ENV OUTPUT_DIR=/app/output

# Entrypoint resolves the artifacts base (workspace dir in prod), creates
# reports/ + logs/, and runs the live integration suite emitting JUnit + reports.
ENTRYPOINT ["/app/docker-entrypoint.sh"]

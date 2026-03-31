# syntax=docker/dockerfile:1
# Containerfile for Podman (compatible with Docker)
# Optimized for rootless Podman with security hardening

FROM docker.io/library/python:3.11-slim

# Run as non-root user
ARG USER_ID=1000
ARG GROUP_ID=1000

WORKDIR /app

# 1) Install OS packages and build dependencies
# Podman: Minimize attack surface
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && apt-get clean

# 2) Install Poetry 2.x
# curl is not present in this image; install Poetry via pip (stdlib only, no curl needed)
RUN pip install --no-cache-dir poetry \
 && poetry config virtualenvs.create false

# 3) Copy dependency files for layer caching
COPY pyproject.toml poetry.lock README.md ./

# 4) Copy source code (needed for Poetry to find the package)
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./

# 5) Install dependencies (main only, no dev dependencies)
RUN poetry install --only main --no-interaction --no-ansi

# 6) Create non-root user for security (Podman best practice)
RUN groupadd -g ${GROUP_ID} appuser \
 && useradd -m -u ${USER_ID} -g appuser appuser \
 && chown -R appuser:appuser /app

# 7) Switch to non-root user
USER appuser

# 8) Expose port
EXPOSE 8000

# 9) Health check — uses Python stdlib so curl is not required in the image
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 10) Runtime command
CMD ["poetry", "run", "uvicorn", "goldsmith_erp.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

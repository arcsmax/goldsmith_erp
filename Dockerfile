# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# 1) OS packages, build-time deps
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential curl \
 && rm -rf /var/lib/apt/lists/*

# 2) install Poetry 2.x
RUN curl -sSL https://install.python-poetry.org | python3 - \
 && ln -s /root/.local/bin/poetry /usr/local/bin/poetry \
 && poetry config virtualenvs.create false

# 3) copy only the metadata so we get a cached layer
COPY pyproject.toml poetry.lock README.md ./

# 3b) copy your library code so 'poetry install' can actually find it
COPY src ./src

# 4) now install all main dependencies (it will see your package under src/goldsmith_erp)
RUN poetry install --only main --no-interaction --no-ansi

# 5) copy everything else (tests, scripts…)
COPY . .

# 6) runtime command
CMD ["poetry", "run", "uvicorn", "goldsmith_erp.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
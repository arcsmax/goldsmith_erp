FROM python:3.11-slim

WORKDIR /app

# System-Abhängigkeiten installieren
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Poetry installieren
RUN pip install --no-cache-dir poetry==1.6.1

# Poetry für Nicht-Interaktivität und Nicht-Root-Installation konfigurieren
RUN poetry config virtualenvs.create false

# Abhängigkeiten kopieren und installieren
COPY pyproject.toml poetry.lock* /app/
RUN poetry install --no-interaction --no-ansi --no-root

# Anwendungscode kopieren
COPY . /app/

# Poetry-Projekt installieren
RUN poetry install --no-interaction --no-ansi

# Port exponieren
EXPOSE 8000

# Container starten
CMD ["uvicorn", "goldsmith_erp.main:app", "--host", "0.0.0.0", "--port", "8000"]
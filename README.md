[![Build Status](https://img.shields.io/github/actions/workflow/status/your-org/goldsmith_erp/ci.yml?branch=main)](https://github.com/your-org/goldsmith_erp/actions)
[![Coverage Status](https://img.shields.io/codecov/c/github/your-org/goldsmith_erp)](https://codecov.io/gh/your-org/goldsmith_erp)
[![License](https://img.shields.io/github/license/your-org/goldsmith_erp)](LICENSE)

# Goldsmith ERP

Ein skalierbares, sicheres und erweiterbares ERP-System, speziell zugeschnitten auf die Anforderungen moderner Goldschmieden.

---

## Inhaltsverzeichnis

1. [Überblick](#überblick)  
2. [Funktionsumfang & Benutzerstories](#funktionsumfang--benutzerstories)  
   - [Module](#module)  
   - [User Stories](#user-stories)  
3. [Architektur](#architektur)  
   - [Frontend (SPA)](#frontend-spa)  
   - [Backend (FastAPI)](#backend-fastapi)  
   - [Daten & Caching](#daten--caching)  
   - [Echtzeit & NFC-Use-Cases](#echtzeit--nfc-use-cases)  
   - [Maschinelles Lernen & LLM](#maschinelles-lernen--llm)  
4. [Einrichtung & Local Development](#einrichtung--local-development)  
   - [Voraussetzungen](#voraussetzungen)  
   - [Docker‑Compose Setup](#docker-compose-setup)  
   - [Umgebungsvariablen](#umgebungsvariablen)  
5. [Dokumentation & ADRs](#dokumentation--adrs)  
6. [Roadmap](#roadmap)  
7. [Beitrag leisten](#beitrag-leisten)  
8. [Lizenz](#lizenz)  
9. [Kontakt & Support](#kontakt--support)  
10. [Danksagungen](#danksagungen)  

---

## Überblick

Goldsmith ERP bündelt Kernprozesse einer Goldschmiede in einer modernen, containerisierten Anwendung:

- **Frontend:** React (TypeScript) oder Vue.js SPA mit Storybook‑Designsystem  
- **Backend:** Asynchrones Python (FastAPI) mit klar getrennten Layers (API, Services, ORM)  
- **Realtime:** WebSockets für Auftragsstatus & NFC‑Scans  
- **Daten & Cache:** PostgreSQL, Redis, S3-kompatibler Storage  
- **ML/LLM:** OCR (Tesseract & LayoutLM), Bildklassifikation, Predictive Modeling  
- **Sicherheit:** JWT, OAuth2, CORS, Secrets Management, Audit Logs  
- **Infra:** Docker, Kubernetes (Helm), GitHub Actions (Lint, Mypy, Pytest, Bandit)

---

## Funktionsumfang & Benutzerstories

### Module

- **Inventarverwaltung**  
  - Nachverfolgung von Edelmetallen & Edelsteinen  
  - Chargen‑ und Seriennummernverwaltung  
- **CRM**  
  - Kundenprofile, Kommunikation, Angebote  
- **Fertigung**  
  - Auftrags‑Workflows, Arbeitsgänge, Ressourcen‑Planung  
- **POS‑Integration**  
  - Kassenschnittstellen, Zahlungs­abwicklung  
- **Einkauf & Lieferanten**  
  - Bestellungen, Wareneingang, Lieferantenbewertungen  
- **Abrechnung & Rechnungswesen**  
  - Rechnungserstellung, Zahlungsüberwachung, Mahnwesen  
- **Reporting & Analytics**  
  - Lagerbestände, Umsatz‑ und Margenreports  
- **Benutzerverwaltung & Rollen**  
  - Zugriffskontrolle, Audit-Logging  

### User Stories

1. **Inventar**  
   > Als Lagerverwalter möchte ich Edelmetalle mit Gewicht und Reinheitsgrad erfassen, um immer aktuelle Bestände zu sehen. Ressourcen (Materialien, Werkzeuge) sollen dabei direkt zu Aufträgen zugeordnet werden können.  
2. **Auftragsstatus**  
   > Als Geschäftsführer möchte ich Echtzeit‑Updates zum Fertigungsfortschritt per WebSocket erhalten.  
3. **NFC‑Scan**  
   > Als Goldschmied scanne ich Job‑Taschen via NFC am Arbeitsplatz, um Arbeitsbeginn und ‑ende automatisch zu dokumentieren.  
4. **OCR‑Billing**  
   > Als Buchhalter möchte ich eingehende Rechnungen automatisch via OCR erfassen und codieren.  
5. **Predictive Lead‑Time**  
   > Als Planer möchte ich basierend auf historischen Daten die Fertigungsdauer neuer Aufträge prognostizieren.  
6. **Ressourcenverwaltung**  
   > Als Produktionsleiter möchte ich die Materialien und Werkzeuge, die für jeden Auftrag verwendet werden, erfassen und verwalten, um Bestände und Kosten transparent zu halten.  
7. **Arbeitszeitplanung**  
   > Als Teamleiter möchte ich die Arbeitszeiten jedes Goldschmieds erfassen und für die Kapazitätsplanung heranziehen können.  
8. **Rollen‑ & Berechtigungsmanagement**  
   > Als Administrator möchte ich festlegen können, dass bestimmte Aufgaben nur von qualifizierten Mitarbeitenden ausgeführt werden dürfen, um Sicherheit und Qualität zu gewährleisten.  

---

## Architektur

### Frontend (SPA)

- **Technologien:** React + TypeScript oder Vue.js + TypeScript  
- **State Management:** Redux / Pinia  
- **Routing & Build:** Vite oder Webpack  
- **Kommunikation:**  
  - REST für CRUD  
  - WebSockets (`/ws/orders`) für Push‑Updates  
- **Testing:** Jest + React Testing Library oder Vue Test Utils  
- **UI‑Bibliothek:** Storybook

### Backend (FastAPI)

- **Framework:** FastAPI (async, Pydantic)  
- **Layers:**  
  1. **API Layer** (`src/goldsmith_erp/api/`)  
  2. **Service Layer** (`src/goldsmith_erp/services/`)  
  3. **Data Layer** (`src/goldsmith_erp/models/`, `src/goldsmith_erp/db/`)  
- **Auth & Security:**  
  - JWT, OAuth2 Password Flow  
  - CORS Policies, HTTPS/In‐Transit Encryption  
  - Audit-Logging für alle Auftragsänderungen  

### Daten & Caching

- **PostgreSQL** (Cloud‑Hosted in EU, SSL‑Verbindung)  
- **ORM:** SQLAlchemy Async + Alembic Migrations  
- **Redis:**  
  - Session Cache  
  - Pub/Sub für Broadcast (z. B. NFC‑Events)  
- **Object Storage:** S3‑kompatibel (AWS S3 oder MinIO)  

### Echtzeit & NFC-Use-Cases

- **Order Status:** WebSocket‑Endpoint `/ws/orders` liefert Statusupdates in Echtzeit.  
- **NFC‑Scans:**  
  - **Scan-Typen:** Materialien (Rohlinge), Werkzeuge, Job‑Bags, Fertigware  
  - **Workflows:**  
    1. **Wareneingang:** Scan bei Anlieferung → automatische Bestandsbuchung  
    2. **Arbeitsbeginn/-ende:** Scan am Arbeitsplatz → Zeiterfassung  
    3. **Qualitätskontrolle:** Scan nach QC → Status „geprüft“ setzen

### Maschinelles Lernen & LLM

- **OCR für Rechnungen:** Tesseract integration, optional LayoutLM für komplexe Layouts  
- **Bildklassifikation:** PyTorch / TensorFlow – z. B. Materialfehler­erkennung  
- **Predictive Modeling:** scikit-learn / XGBoost für Durchlaufzeit‑Prognosen  
- **Architektur:**  
  - Package `goldsmith_ml` für Pipelines, Modellregistrierung & APIs  
  - ML‑Features als optionale Plugins konfigurierbar  

---

## Einrichtung & Local Development

### Voraussetzungen

- **Docker & Docker‑Compose** (empfohlen)  
- **Git**  
- **Node.js & npm/yarn** (Frontend)  
- **Poetry** (optional für reine Python‑Entwicklung)

### Docker‑Compose Setup

Legt alles in Containern an:

```yaml
version: '3.8'
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_USER: goldsmith
      POSTGRES_PASSWORD: secret
      POSTGRES_DB: goldsmith
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7
    ports:
      - "6379:6379"

  minio:
    image: minio/minio
    command: server /data
    environment:
      MINIO_ACCESS_KEY: minio
      MINIO_SECRET_KEY: minio123
    ports:
      - "9000:9000"
    volumes:
      - miniodata:/data

  backend:
    build: .
    command: uvicorn src.goldsmith_erp.main:app --host 0.0.0.0 --port 8000 --reload
    volumes:
      - ./:/app
    ports:
      - "8000:8000"
    env_file:
      - .env

  frontend:
    working_dir: /app/frontend
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    volumes:
      - ./frontend:/app/frontend
    command: yarn dev

volumes:
  pgdata:
  miniodata:
```

Starten:

```bash
docker-compose up --build
```  

### Umgebungsvariablen

Erstelle eine `.env.example` im Projekt‑Root:

```dotenv
DATABASE_URL=postgresql://goldsmith:secret@db:5432/goldsmith
REDIS_URL=redis://redis:6379/0
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minio
MINIO_SECRET_KEY=minio123
JWT_SECRET_KEY=your_jwt_secret
OAUTH2_CLIENT_ID=...
OAUTH2_CLIENT_SECRET=...
```  

Kopiere dann nach `.env` und passe an.

---

## Dokumentation & ADRs

- **API‑Specs:** Automatisch generiert von FastAPI unter `/docs` (OpenAPI/Swagger)  
- **ADR‑Verzeichnis:** `docs/adrs/` für Architektur-Entscheidungen  
- **User Guide & Dev Guide:** `docs/user/`, `docs/developer/` (optional: MkDocs/Docsify)  

---

## Roadmap

| Version | Fokus (Initial)                            | Geplant (Future)                                        |
|---------|---------------------------------------------|---------------------------------------------------------|
| v1.0    | Kernmodule (Inventar, Aufträge, Abrechnung) | Microservices‑Split (Auth, Orders, Billing)             |
| v1.1    | NFC‑Integration, Basis‑OCR                  | Erweiterte Predictive Analytics, Kafka Event‑Bus        |
| v2.0    | POS & CRM                                   | Mobile App (PWA), Multi‑Tenant Support                  |
| v3.0    | Multiregionale Cloud‑Deploys                | Vollautomatisierte Helm‑Operatoren, ML‑Model‑Service    |

---

## Beitrag leisten

1. Fork des Repos  
2. Branch anlegen: `feature/<kurzbeschreibung>`  
3. Änderungen mit PEP 8, `pylint` & `mypy` prüfen  
4. PR öffnen gegen `main`, Reviews bestehen lassen  
5. Automatisierte Tests müssen grünen (GitHub Actions)

---

## Lizenz

Dieses Projekt steht unter der [MIT Lizenz](LICENSE).

---

## Kontakt & Support

- **Issue Tracker:** https://github.com/your-org/goldsmith_erp/issues  
- **Team‑E‑Mail:** support@goldsmith-erp.example.com  

---

## Danksagungen

- Basierend auf Ideen der Open‑Source ERP‑Community  
- Dank an FastAPI, React, SQLAlchemy und all die großartigen Tools  
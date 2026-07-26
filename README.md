# Goldsmith ERP

Ein skalierbares, sicheres und erweiterbares ERP-System, speziell zugeschnitten auf die Anforderungen moderner Goldschmieden.

[![License](https://img.shields.io/github/license/arcsmax/goldsmith_erp)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.3%2B-61DAFB)](https://reactjs.org/)
[![Podman](https://img.shields.io/badge/Podman-Rootless-892CA0)](https://podman.io/)

---

## 📋 Inhaltsverzeichnis

1. [Überblick](#überblick)
2. [Hauptfunktionen](#hauptfunktionen)
3. [Technologie-Stack](#technologie-stack)
4. [Schnellstart](#schnellstart)
5. [Installation & Setup](#installation--setup)
6. [Dokumentation](#dokumentation)
7. [Roadmap](#roadmap)
8. [Beitrag leisten](#beitrag-leisten)
9. [Lizenz](#lizenz)

---

## 🎯 Überblick

Goldsmith ERP bündelt Kernprozesse einer Goldschmiede in einer modernen, containerisierten Anwendung:

- **Moderne Architektur:** React-Frontend + FastAPI-Backend
- **Echtzeit-Updates:** WebSockets für Live-Benachrichtigungen
- **Sicher:** Rootless Podman, JWT-Authentifizierung, verschlüsselte Verbindungen
- **Skalierbar:** Container-basiert, Kubernetes-ready
- **Erweiterbar:** Modulare Architektur für einfache Anpassungen

---

## ✨ Hauptfunktionen

### Bereits implementiert

- ✅ **Auftragsverwaltung** - Aufträge erstellen, bearbeiten, verfolgen
- ✅ **Materialverwaltung** - Inventar für Edelmetalle und Edelsteine
- ✅ **Benutzerverwaltung** - Authentifizierung und Zugriffskontrolle
- ✅ **Time-Tracking** - Zeiterfassung mit QR/NFC-Support
- ✅ **Tab-Memory System** - Context-Switching für Goldschmiede
- ✅ **WebSocket-Updates** - Echtzeit-Benachrichtigungen über Redis
- ✅ **REST API** - Vollständige OpenAPI/Swagger-Dokumentation

### In Entwicklung

- 🚧 **ML-gestützte Deadline-Berechnung** - Automatische Liefertermine
- 🚧 **Kalender-System** - Kapazitätsplanung und Deadlines
- 🚧 **Quick-Actions Menü** - Scanner-gesteuerte Workflows
- 🚧 **CRM-Modul** - Kundenverwaltung und Kommunikation
- 🚧 **Reporting** - Umsatz- und Bestandsberichte

---

## 🛠 Technologie-Stack

### Backend
- **Python 3.11+** - Moderne Python-Features
- **FastAPI 0.115+** - Hochperformantes async Web-Framework
- **SQLAlchemy 2.0+** - Async ORM mit Type-Safety
- **PostgreSQL 15** - Relationale Datenbank
- **Redis 7** - Caching und Pub/Sub
- **Alembic** - Datenbank-Migrationen

### Frontend
- **React 18.3+** - UI-Framework
- **TypeScript** - Type-Safe JavaScript
- **Vite 5.4+** - Moderner Build-Tool
- **Yarn 4.9+** - Package Manager

### DevOps
- **Podman & podman-compose** - Rootless Container Runtime
- **Poetry** - Python Dependency Management
- **Systemd** - Native Service Integration
- **GitHub Actions** - CI/CD (geplant)

---

## 🚀 Schnellstart

### Voraussetzungen

Stellen Sie sicher, dass folgende Software installiert ist:

- **Podman** + podman-compose (empfohlen) oder Docker
- **Git**

### Automatisches Setup (Empfohlen)

```bash
# 1. Repository klonen
git clone https://github.com/arcsmax/goldsmith_erp.git
cd goldsmith_erp

# 2. Automatisches Setup (installiert Podman + startet Services)
./setup-podman.sh
```

Das Script:
- ✅ Installiert Podman, podman-compose, Buildah
- ✅ Konfiguriert Rootless Mode
- ✅ Erstellt .env mit sicherem SECRET_KEY
- ✅ Baut alle Container
- ✅ Startet alle Services

> ⚠️ **`setup-podman.sh` richtet die ENTWICKLUNGS-Umgebung ein**
> (`podman-compose.yml`, Vite-Dev-Server, `.env` aus `.env.example`, **kein
> TLS**). Für den **Produktivbetrieb** mit echten Kundendaten den gehärteten
> Weg nutzen — `setup.sh` + `podman-compose.prod.yml` (inkl. **Caddy
> TLS-Proxy**), Referenz-Seed, Backups und DSGVO-Löschtimer:
> **→ [Produktions-Deployment](docs/technical/infrastructure/PRODUCTION_DEPLOYMENT.md)**.

### Mit Makefile (Alternative)

```bash
make install  # Installiert Podman
make start    # Startet alle Services
make logs     # Zeigt Logs
make help     # Alle verfügbaren Befehle
```

### Manuelle Installation

```bash
# 1. Repository klonen
git clone https://github.com/arcsmax/goldsmith_erp.git
cd goldsmith_erp

# 2. Umgebungsvariablen konfigurieren
cp .env.example .env
# WICHTIG: SECRET_KEY in .env ändern!

# 3. Mit Podman starten
podman-compose -f podman-compose.yml up -d

# 4. Status prüfen
podman-compose -f podman-compose.yml ps
```

### Die Anwendung ist nun verfügbar:

- **Backend API:** http://localhost:8000
- **API Dokumentation:** http://localhost:8000/docs
- **Frontend:** http://localhost:3000

### Docker-Kompatibilität

Podman ist 100% Docker-kompatibel. Aliase verwenden:
```bash
alias docker=podman
alias docker-compose=podman-compose

# Jetzt funktionieren Docker-Befehle:
docker ps
docker-compose up
```

---

## 📦 Installation & Setup

### Podman vs Docker

Goldsmith ERP nutzt **Podman** für verbesserte Sicherheit:

| Feature | Docker | Podman |
|---------|--------|--------|
| Rootless | ❌ | ✅ |
| Daemon | ❌ Erforderlich | ✅ Nicht nötig |
| Security | ⚠️ Root-Daemon | ✅ User Namespaces |
| Kubernetes | ⚠️ Separate Tools | ✅ `podman play kube` |
| Systemd | ⚠️ Extra Setup | ✅ Native Support |

### Plattform-spezifische Anleitungen

- **[PODMAN_MIGRATION.md](PODMAN_MIGRATION.md)** - **Podman Migration & Best Practices**
- **[ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md)** - Architecture Analysis
- [INSTALLATION.md](INSTALLATION.md) - Detaillierte Installationsanleitung
- [Windows Installation](INSTALLATION.md#windows-installation)
- [macOS Installation](INSTALLATION.md#macos-installation)
- [Linux Installation](INSTALLATION.md#linux-installation)

### Manuelle Installation (ohne Container)

Falls Sie Podman/Docker nicht nutzen möchten:

**Backend:**
```bash
# Python 3.11+ erforderlich
cd goldsmith_erp
poetry install
poetry run alembic upgrade head
poetry run uvicorn goldsmith_erp.main:app --reload
```

**Frontend:**
```bash
cd frontend
yarn install
yarn dev
```

---

## 📚 Dokumentation

### API-Dokumentation

Die API-Dokumentation wird automatisch von FastAPI generiert:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **OpenAPI Schema:** http://localhost:8000/openapi.json

### Feature-Spezifikationen

- **[FEATURE_SPEC_TIME_TRACKING_ML.md](FEATURE_SPEC_TIME_TRACKING_ML.md)** - Time-Tracking & ML System
- **[IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)** - Implementierungs-Roadmap

### Weitere Dokumentation

- **[PRODUCTION_TLS.md](docs/technical/infrastructure/PRODUCTION_TLS.md)** - Produktions-TLS (Caddy Reverse Proxy, Root-CA-Trust, COOKIE_SECURE)
- **[PODMAN_MIGRATION.md](PODMAN_MIGRATION.md)** - Podman Migration & Best Practices
- **[ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md)** - Architecture Analysis & Improvements
- **[INSTALLATION.md](INSTALLATION.md)** - Detaillierte Installationsanleitung
- **[CHANGELOG.md](CHANGELOG.md)** - Version History (wird erstellt)
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Contribution Guidelines (geplant)

### Projektstruktur

```
goldsmith_erp/
├── src/goldsmith_erp/       # Backend-Quellcode
│   ├── api/                 # API-Endpoints
│   │   └── routers/        # API-Router (auth, orders, time-tracking)
│   ├── core/               # Konfiguration, Security
│   ├── db/                 # Datenbank-Models
│   ├── models/             # Pydantic-Schemas
│   └── services/           # Business-Logic
├── frontend/               # React-Frontend
│   ├── src/               # Frontend-Quellcode
│   └── public/            # Statische Assets
├── alembic/               # Datenbank-Migrationen
│   └── versions/          # Migration-Scripts
├── tests/                 # Test-Suite (geplant)
├── podman-compose.yml     # Podman Compose Config
├── podman-pod.yaml        # Kubernetes-style Pod Manifest
├── Containerfile          # Backend Container (Podman)
├── Makefile               # Einfache Befehle (make start, make logs)
├── setup-podman.sh        # Automatisches Podman Setup
├── pyproject.toml         # Python-Dependencies
└── README.md              # Diese Datei
```

---

## 🗺 Roadmap

### Version 0.2.0 (Q1 2025)
- [ ] Phase 5.2: Quick-Actions Frontend
- [ ] Phase 5.3: ML-Modelle für Deadline-Berechnung
- [ ] Kalender-System mit Kapazitätsplanung
- [ ] Umfassende Test-Suite (>80% Coverage)
- [ ] CI/CD-Pipeline
- [ ] Critical Security Fixes (siehe ARCHITECTURE_REVIEW.md)

### Version 0.3.0 (Q2 2025)
- [ ] NFC-Integration (Production-Ready)
- [ ] Photo-Dokumentation System
- [ ] Interruption-Management
- [ ] Mobile-responsive Design
- [ ] CRM-Modul

### Version 1.0.0 (Q4 2025)
- [ ] Produktionsreife
- [ ] ML Feature Store
- [ ] Predictive Analytics
- [ ] Multi-Language-Support
- [ ] OCR-Integration

Siehe [GitHub Projects](https://github.com/arcsmax/goldsmith_erp/projects) für aktuelle Entwicklung.

---

## 🔐 Security & Best Practices

Goldsmith ERP nutzt **Podman** für verbesserte Container-Sicherheit:

- ✅ **Rootless Containers** - Keine Root-Rechte nötig
- ✅ **Daemonless Architecture** - Kein privilegierter Hintergrundprozess
- ✅ **User Namespaces** - Bessere Prozess-Isolation
- ✅ **SELinux/AppArmor** - Native Security-Module-Integration
- ✅ **Systemd Integration** - Container als native Services
- ✅ **No New Privileges** - Security Opt im Container

**Weitere Security-Features:**
- JWT-basierte Authentifizierung
- HTTPS-Ready (TLS-Konfiguration)
- Input Validation mit Pydantic
- SQL Injection Prevention (Parametrisierte Queries)
- CORS-Protection
- Rate Limiting (geplant)
- Secrets Management (geplant)

Siehe [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) für detaillierte Sicherheitsanalyse.

---

## 🛠️ Nützliche Befehle

### Makefile Commands

```bash
make help              # Alle verfügbaren Befehle
make start             # Services starten
make stop              # Services stoppen
make restart           # Services neustarten
make logs              # Logs anzeigen
make logs-backend      # Nur Backend-Logs
make logs-frontend     # Nur Frontend-Logs
make build             # Container neu bauen
make shell-backend     # Backend Shell öffnen
make shell-db          # PostgreSQL Shell
make migrate           # Migrationen ausführen
make test              # Tests ausführen
make lint              # Code-Linting
make format            # Code formatieren
make health            # Service Health Check
make backup-db         # Datenbank-Backup
```

### Podman Commands

```bash
# Container Management
podman ps                  # Laufende Container
podman images              # Vorhandene Images
podman logs <container>    # Container Logs
podman exec -it <container> bash  # Container Shell

# Pod Management (Kubernetes-style)
podman play kube podman-pod.yaml  # Pod starten
podman play kube --down podman-pod.yaml  # Pod stoppen
podman pod ps              # Laufende Pods

# System Management
podman system prune        # Cleanup
podman system df           # Disk Usage
podman system info         # System Info
```

---

## 🤝 Beitrag leisten

Wir freuen uns über Beiträge! Bitte beachten Sie:

1. **Fork** das Repository
2. **Branch** erstellen: `git checkout -b feature/AmazingFeature`
3. **Commit** mit klarer Beschreibung: `git commit -m 'Add amazing feature'`
4. **Push** zum Branch: `git push origin feature/AmazingFeature`
5. **Pull Request** öffnen

### Entwicklungsrichtlinien

- Code-Style: Black (Python), Prettier (TypeScript)
- Type-Checking: mypy (Python), TypeScript
- Testing: pytest (Backend), Jest (Frontend)
- Linting: pylint, ESLint
- Commit Messages: Conventional Commits

---

## 📄 Lizenz

Dieses Projekt steht unter der [MIT Lizenz](LICENSE).

---

## 💬 Support & Kontakt

- **Issues:** [GitHub Issues](https://github.com/arcsmax/goldsmith_erp/issues)
- **Discussions:** [GitHub Discussions](https://github.com/arcsmax/goldsmith_erp/discussions)
- **Email:** support@goldsmith-erp.example.com

---

## 🙏 Danksagungen

- [FastAPI](https://fastapi.tiangolo.com/) - Modernes Python Web-Framework
- [React](https://reactjs.org/) - UI-Library
- [SQLAlchemy](https://www.sqlalchemy.org/) - ORM
- [PostgreSQL](https://www.postgresql.org/) - Datenbank
- [Podman](https://podman.io/) - Rootless Container Runtime
- [Redis](https://redis.io/) - Caching & Pub/Sub

---

**Entwickelt mit ❤️ für moderne Goldschmieden**

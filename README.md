# Goldsmith ERP

Ein skalierbares, sicheres und erweiterbares ERP-System, speziell zugeschnitten auf die Anforderungen moderner Goldschmieden.

[![License](https://img.shields.io/github/license/arcsmax/goldsmith_erp)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18.3%2B-61DAFB)](https://reactjs.org/)

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
- **Sicher:** JWT-Authentifizierung, verschlüsselte Verbindungen
- **Skalierbar:** Docker-basiert, cloud-ready
- **Erweiterbar:** Modulare Architektur für einfache Anpassungen

---

## ✨ Hauptfunktionen

### Bereits implementiert

- ✅ **Auftragsverwaltung** - Aufträge erstellen, bearbeiten, verfolgen
- ✅ **Materialverwaltung** - Inventar für Edelmetalle und Edelsteine
- ✅ **Benutzerverwaltung** - Authentifizierung und Zugriffskontrolle
- ✅ **WebSocket-Updates** - Echtzeit-Benachrichtigungen über Redis
- ✅ **REST API** - Vollständige OpenAPI/Swagger-Dokumentation

### In Entwicklung

- 🚧 **CRM-Modul** - Kundenverwaltung und Kommunikation
- 🚧 **POS-Integration** - Kassensystem-Anbindung
- 🚧 **NFC-Integration** - Arbeitszeit- und Materialerfassung
- 🚧 **Reporting** - Umsatz- und Bestandsberichte
- 🚧 **OCR** - Automatische Rechnungserkennung

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
- **Docker & Docker Compose** - Containerisierung
- **Poetry** - Python Dependency Management
- **GitHub Actions** - CI/CD (geplant)

---

## 🚀 Schnellstart

### Voraussetzungen

Stellen Sie sicher, dass folgende Software installiert ist:

- **Docker Desktop** (empfohlen) oder Docker + Docker Compose
- **Git**

### In 3 Schritten starten

```bash
# 1. Repository klonen
git clone https://github.com/arcsmax/goldsmith_erp.git
cd goldsmith_erp

# 2. Umgebungsvariablen konfigurieren (optional)
cp .env.example .env

# 3. Mit Docker Compose starten
docker-compose up --build
```

Die Anwendung ist nun verfügbar:
- **Backend API:** http://localhost:8000
- **API Dokumentation:** http://localhost:8000/docs
- **Frontend:** http://localhost:3000

---

## 📦 Installation & Setup

Für detaillierte Installationsanleitungen siehe **[INSTALLATION.md](INSTALLATION.md)**

### Plattform-spezifische Anleitungen

- [Windows Installation](INSTALLATION.md#windows-installation)
- [macOS Installation](INSTALLATION.md#macos-installation)
- [Linux Installation](INSTALLATION.md#linux-installation)
- [Entwicklungsumgebung](INSTALLATION.md#entwicklungsumgebung-einrichten)

### Manuelle Installation (ohne Docker)

Falls Sie Docker nicht nutzen möchten:

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

### Weitere Dokumentation

- **[INSTALLATION.md](INSTALLATION.md)** - Detaillierte Installationsanleitung
- **[CHANGELOG.md](CHANGELOG.md)** - Version History (wird erstellt)
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Contribution Guidelines (geplant)

### Projektstruktur

```
goldsmith_erp/
├── src/goldsmith_erp/       # Backend-Quellcode
│   ├── api/                 # API-Endpoints
│   │   └── routers/        # API-Router (auth, orders)
│   ├── core/               # Konfiguration, Security
│   ├── db/                 # Datenbank-Models
│   ├── models/             # Pydantic-Schemas
│   └── services/           # Business-Logic
├── frontend/               # React-Frontend
│   ├── src/               # Frontend-Quellcode
│   └── public/            # Statische Assets
├── alembic/               # Datenbank-Migrationen
│   └── versions/          # Migration-Scripts
├── tests/                 # Test-Suite
├── docker-compose.yml     # Docker-Konfiguration
├── Dockerfile            # Backend-Container
├── pyproject.toml        # Python-Dependencies
└── README.md             # Diese Datei
```

---

## 🗺 Roadmap

### Version 0.2.0 (Nächste Release)
- [ ] Vollständiges CRM-Modul
- [ ] Erweiterte Berichtserstattung
- [ ] Verbesserte Frontend-UI
- [ ] Umfassende Test-Suite
- [ ] CI/CD-Pipeline

### Version 0.3.0
- [ ] NFC-Integration
- [ ] POS-System-Integration
- [ ] Mobile-responsive Design
- [ ] Multi-Tenancy-Support

### Version 1.0.0
- [ ] Produktionsreife
- [ ] OCR-Integration
- [ ] Predictive Analytics
- [ ] Multi-Language-Support

Siehe [GitHub Projects](https://github.com/arcsmax/goldsmith_erp/projects) für aktuelle Entwicklung.

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
- [Docker](https://www.docker.com/) - Containerisierung

---

**Entwickelt mit ❤️ für moderne Goldschmieden**

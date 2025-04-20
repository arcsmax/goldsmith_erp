# Goldsmith ERP

**Skalierbares, sicheres und erweiterbares ERP-System für Goldschmiede**

Dieser README dient als zentrale Dokumentation für Architektur, Modulübersicht und das initiale Setup des Projekts. Bewahre diese Datei im Wurzelverzeichnis deines Repositories (`README.md`) auf.

---

## Architektur & Modulübersicht

### Frontend (Web & Mobile)
- **Technologien:** React (TypeScript) oder Vue.js
- **Architektur:** Single-Page Application (SPA)
- **State Management:** Redux / Pinia
- **Kommunikation:**
  - **REST** für Standard-CRUD-Operationen
  - **WebSocket** (FastAPI) für Echtzeit-Synchronisierung (Auftragsstatus, NFC-Scans)
- **Build-Tool:** Vite oder Webpack
- **Testing:** Jest + React Testing Library bzw. Vue Test Utils
- **Design-System:** Storybook für wiederverwendbare UI-Komponenten

### Backend (Python)
- **Framework:** FastAPI (asynchron, Pydantic-Typisierung)
- **Architektur-Layers:**
  1. **API Layer:** Router/Endpoints in `src/goldsmith_erp/api/`
  2. **Core Layer:** Domänenlogik in `src/goldsmith_erp/services/`
  3. **Data Layer:** ORM-Modelle & Session-Management in `src/goldsmith_erp/models/` und `src/goldsmith_erp/db/`
- **Echtzeit:** WebSocket-Endpunkt `/ws/orders` für Push-Updates
- **Sicherheit:** JWT-Auth, OAuth2, CORS-Policies

### Persistence & Caching
- **Datenbank:** PostgreSQL (Cloud-Hosted in EU-Region)
- **ORM:** SQLAlchemy Async + Alembic (Migrations)
- **Caching & Pub/Sub:** Redis (Session-Cache, Pub/Sub für Broadcast)
- **Dateispeicherung:** S3-kompatibler Storage (AWS S3 / MinIO)

### ML/LLM-Komponente
- **Rechnungs-OCR:** Tesseract + Transformers (z. B. LayoutLM)
- **Bildklassifikation:** PyTorch / TensorFlow
- **Vorhersagen:** scikit-learn / XGBoost
- **Struktur:** Eigenes Package `goldsmith_ml` für Pipelines und Modelle

### Infrastruktur & Cloud
- **Containerisierung:** Docker + Kubernetes (Helm-Charts)
- **CI/CD:** GitHub Actions
  - Linting: `pylint`, `black`
  - Typprüfung: `mypy`
  - Tests: `pytest`
  - Security-Scans: `bandit`
  - Deployment: Helm/Kubectl
- **Secrets & Config:** AWS Secrets Manager / Azure Key Vault
- **Monitoring & Logging:** Prometheus + Grafana; ELK-Stack / CloudWatch
- **TLS & Routing:** Ingress (nginx) mit HTTPS

### Sicherheit & DSGVO
- Speicherung in EU-Region
- Datenverschlüsselung (at-rest & in-transit)
- Anonymisierte Logs
- Audit-Logging für Auftragsänderungen

### Skalierbarkeit & Erweiterbarkeit
- **Microservices-Ansatz:** Später getrennte Services (Auth, Orders, Billing)
- **Event-Driven:** Kafka / AWS SNS für asynchrone Verarbeitung
- **Feature-Flags:** LaunchDarkly oder eigene Implementierung

---

## Initiales Setup & Entwicklungsumgebung

### 1. Voraussetzungen (macOS)
```bash
# Homebrew installieren (falls noch nicht vorhanden)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# System-Tools
brew install python@3.11 git node redis postgresql

# Terminal & Editor
brew install --cask iterm2 visual-studio-code
```  

### 2. Repository & Versionierung
```bash
mkdir goldsmith_erp && cd goldsmith_erp
git init
git remote add origin git@github.com:<username>/goldsmith_erp.git
```
- Erstelle `.gitignore` für `__pycache__/`, `.env`, `dist/`, `.vscode/`

### 3. Virtuelle Umgebung & Paketmanagement
```bash
# Poetry installieren
brew install poetry

# Projekt initialisieren
poetry init --name goldsmith_erp \
  --dependency fastapi pydantic uvicorn[standard] sqlalchemy asyncpg redis python-dotenv \
  --dev-dependency pylint mypy pytest pre-commit

# Python-Version festlegen & installieren
poetry env use $(which python3.11)
poetry install
```  

### 4. Konfiguration in VS Code & iTerm2
- **VS Code Extensions:** Python, Pylance, Prettier, ESLint, Docker
- **`.vscode/settings.json`**
  ```json
  {
    "python.pythonPath": "${workspaceFolder}/.venv/bin/python",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": true,
      "source.fixAll": true
    }
  }
  ```
- **Zsh Config (`~/.zshrc`)**
  ```shell
  export PATH="$HOME/.poetry/bin:$PATH"
  export DATABASE_URL="postgresql://user:pass@localhost:5432/goldsmith"
  source $HOME/goldsmith_erp/.env
  ```

### 5. Pre-Commit & CI/CD
- **`.pre-commit-config.yaml`**
  ```yaml
  repos:
    - repo: https://github.com/pre-commit/pre-commit-hooks
      rev: v4.4.0
      hooks:
        - id: end-of-file-fixer
        - id: trailing-whitespace
    - repo: https://github.com/psf/black
      rev: 23.1.0
      hooks:
        - id: black
    - repo: https://github.com/PyCQA/pylint
      rev: v2.17.0
      hooks:
        - id: pylint
    - repo: https://github.com/pre-commit/mirrors-mypy
      rev: v0.991
      hooks:
        - id: mypy
  ```
- **GitHub Actions** in `.github/workflows/ci.yml` (siehe Infrastruktur-Sektion)

### 6. Erstes Commit & Workflow
```bash
git add .
git commit -m "chore: initial scaffold of project"
```
- **Branches:** `main` (stabil), `feature/<name>`
- **Pull Requests:** Pflicht-Reviews + automatisierte Checks

---

> **Hinweis:** Dieses README ist ein lebendes Dokument. Passe es bei Bedarf an neue Anforderungen oder Technologien an.


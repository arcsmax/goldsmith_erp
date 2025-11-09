# Goldsmith ERP - Installationsanleitung

**Vollständige Schritt-für-Schritt-Anleitung** zur Installation von Goldsmith ERP mit **Podman** (empfohlen) oder Docker auf verschiedenen Betriebssystemen.

> 📢 **Wichtig:** Goldsmith ERP nutzt jetzt **Podman** statt Docker für verbesserte Sicherheit. Podman ist 100% Docker-kompatibel und benötigt **keine Root-Rechte**.

---

## 📋 Inhaltsverzeichnis

1. [Was ist Podman? (vs Docker)](#was-ist-podman-vs-docker)
2. [Schnellstart (Automatisch)](#schnellstart-automatisch)
3. [Linux Installation (Ubuntu/Debian/Fedora)](#linux-installation)
4. [macOS Installation](#macos-installation)
5. [Windows Installation (WSL2)](#windows-installation)
6. [Manuelle Installation (ohne Container)](#manuelle-installation-ohne-container)
7. [Entwicklungsumgebung](#entwicklungsumgebung-einrichten)
8. [Migration von Docker zu Podman](#migration-von-docker-zu-podman)
9. [Problemlösungen](#problemlösungen)
10. [FAQ](#häufig-gestellte-fragen)

---

## 🐳 Was ist Podman? (vs Docker)

**Podman = Docker, aber sicherer!**

| Feature | Docker | Podman |
|---------|--------|--------|
| **Root-Rechte nötig?** | ✅ Ja (Daemon) | ❌ Nein (Rootless) |
| **Hintergrundprozess?** | ✅ Ja (Daemon) | ❌ Nein |
| **CLI-Kompatibilität** | - | ✅ 100% Docker-kompatibel |
| **Kubernetes Support** | ⚠️ Separat | ✅ Nativ (`podman play kube`) |
| **Systemd Integration** | ⚠️ Extra Setup | ✅ Nativ |
| **Security** | ⚠️ Root-Daemon | ✅ User Namespaces |

**Warum Podman?**
- ✅ **Rootless** - Keine Root-Rechte nötig, sicherer
- ✅ **Daemonless** - Kein privilegierter Hintergrundprozess
- ✅ **Docker-kompatibel** - `alias docker=podman` und alles funktioniert
- ✅ **Kubernetes-ready** - Pods wie in K8s

---

## 🚀 Schnellstart (Automatisch)

### Linux (Ubuntu, Debian, Fedora, RHEL)

**1 Befehl installation:**

```bash
# Repository klonen
git clone https://github.com/arcsmax/goldsmith_erp.git
cd goldsmith_erp

# Automatisches Setup (installiert Podman + startet Services)
./setup-podman.sh
```

**Was macht das Script?**
1. ✅ Erkennt automatisch dein OS (Ubuntu/Debian/Fedora/RHEL)
2. ✅ Installiert Podman, podman-compose, Buildah, Skopeo
3. ✅ Konfiguriert Rootless Mode (User Namespaces)
4. ✅ Erstellt `.env` mit sicherem `SECRET_KEY`
5. ✅ Baut alle Container-Images
6. ✅ Startet alle Services (DB, Redis, Backend, Frontend)
7. ✅ Zeigt Status und Access-URLs

**Erwartete Ausgabe:**

```
╔════════════════════════════════════════╗
║     Installation Complete! 🎉         ║
╚════════════════════════════════════════╝

✓ Goldsmith ERP is now running in rootless Podman!

📍 Access points:
   Backend API:     http://localhost:8000
   API Docs:        http://localhost:8000/docs
   Frontend:        http://localhost:3000

🛠️  Useful commands:
   View logs:       podman-compose -f podman-compose.yml logs -f
   Stop services:   podman-compose -f podman-compose.yml down
   Restart:         podman-compose -f podman-compose.yml restart
```

**Fertig!** 🎉 System läuft auf http://localhost:3000

---

## 🐧 Linux Installation (Detailliert)

### Option A: Automatisch (Empfohlen)

Siehe [Schnellstart](#schnellstart-automatisch) oben.

### Option B: Manuell (Schritt-für-Schritt)

#### Schritt 1: System-Voraussetzungen prüfen

```bash
# OS-Version prüfen
cat /etc/os-release

# Erwartete OS:
# - Ubuntu 22.04+ (Jammy, Lunar, Mantic)
# - Debian 12+ (Bookworm)
# - Fedora 38+
# - RHEL 9+ / Rocky Linux 9+
```

#### Schritt 2: Podman installieren

**Ubuntu 22.04+ / Debian 12+:**

```bash
# System aktualisieren
sudo apt-get update

# Podman + Tools installieren
sudo apt-get install -y \
    podman \
    podman-compose \
    buildah \
    skopeo \
    fuse-overlayfs \
    slirp4netns

# Installation prüfen
podman --version
podman-compose --version
```

**Erwartete Ausgabe:**
```
podman version 4.6.2
podman-compose version 1.0.6
```

**Fedora 38+ / RHEL 9+:**

```bash
# Podman installieren (meist vorinstalliert)
sudo dnf install -y \
    podman \
    podman-compose \
    buildah \
    skopeo

# Installation prüfen
podman --version
```

#### Schritt 3: Rootless Mode konfigurieren

**Wichtig:** Podman benötigt User Namespaces für Rootless Mode.

```bash
# 1. Prüfen ob Subuid/Subgid bereits existieren
grep "^$USER:" /etc/subuid
grep "^$USER:" /etc/subgid

# Wenn leer, dann konfigurieren:
echo "$USER:100000:65536" | sudo tee -a /etc/subuid
echo "$USER:100000:65536" | sudo tee -a /etc/subgid

# 2. Podman migrieren
podman system migrate

# 3. Lingering aktivieren (Container überleben Logout)
loginctl enable-linger $USER

# 4. Podman Info prüfen
podman info
```

**Erwartete Ausgabe (wichtige Zeilen):**
```yaml
host:
  security:
    rootless: true    # ✅ Rootless aktiviert!
  uidMappings:
    - containerID: 0
      hostID: 100000  # ✅ User Namespaces konfiguriert
```

#### Schritt 4: Repository klonen

```bash
# Arbeitsverzeichnis erstellen
mkdir -p ~/Projects
cd ~/Projects

# Repository klonen
git clone https://github.com/arcsmax/goldsmith_erp.git
cd goldsmith_erp

# Verzeichnisinhalt prüfen
ls -la
```

**Erwartete Dateien:**
```
drwxr-xr-x  podman-compose.yml    # Podman Compose Config
-rwxr-xr-x  setup-podman.sh       # Auto-Setup Script
-rw-r--r--  Containerfile         # Backend Container
-rw-r--r--  Makefile              # Make-Commands
-rw-r--r--  .env.example          # Umgebungsvariablen-Template
```

#### Schritt 5: Umgebungsvariablen konfigurieren

```bash
# .env aus Template erstellen
cp .env.example .env

# Sicheren SECRET_KEY generieren
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")
echo "Generated SECRET_KEY: $SECRET_KEY"

# SECRET_KEY in .env eintragen
sed -i "s/SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" .env

# Optional: .env bearbeiten
nano .env
```

**Wichtige Variablen in `.env`:**

```env
# Database
POSTGRES_USER=user
POSTGRES_PASSWORD=pass          # ⚠️ ÄNDERN für Production!
POSTGRES_DB=goldsmith
POSTGRES_HOST=db

# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_URL=redis://redis:6379/0

# Security
SECRET_KEY=<generiert>           # ✅ Automatisch generiert

# App
DEBUG=true                       # ⚠️ FALSE für Production!
ENVIRONMENT=development          # development/staging/production

# CORS (Frontend-URLs)
BACKEND_CORS_ORIGINS=http://localhost:3000,http://localhost:8000
```

**Speichern:** `Ctrl+O` → `Enter` → `Ctrl+X`

#### Schritt 6: Container bauen und starten

```bash
# Mit podman-compose (Docker-kompatibel)
podman-compose -f podman-compose.yml build

# Erwartete Ausgabe:
# Building backend...
# Step 1/10 : FROM docker.io/library/python:3.11-slim
# ...
# Successfully built goldsmith-backend:latest
# Building frontend...
# Successfully built goldsmith-frontend:latest
```

**Container starten:**

```bash
# Alle Services starten
podman-compose -f podman-compose.yml up -d

# Status prüfen
podman-compose -f podman-compose.yml ps
```

**Erwartete Ausgabe:**

```
NAME                     STATUS      PORTS
goldsmith-db-1           Up 2 minutes  0.0.0.0:5432->5432/tcp
goldsmith-redis-1        Up 2 minutes  0.0.0.0:6379->6379/tcp
goldsmith-backend-1      Up 1 minute   0.0.0.0:8000->8000/tcp
goldsmith-frontend-1     Up 1 minute   0.0.0.0:3000->3000/tcp
```

**Logs anzeigen:**

```bash
# Alle Logs
podman-compose logs -f

# Nur Backend
podman-compose logs -f backend

# Nur Fehler
podman-compose logs backend | grep ERROR
```

#### Schritt 7: Anwendung testen

**1. Backend API testen:**

```bash
# Health Check
curl http://localhost:8000/health

# Erwartete Antwort:
# {"status":"ok"}

# API Dokumentation im Browser öffnen:
firefox http://localhost:8000/docs
# oder
google-chrome http://localhost:8000/docs
```

**2. Frontend testen:**

```bash
# Frontend im Browser öffnen
firefox http://localhost:3000
```

**3. Login testen:**

Da noch keine User existieren, erstellen wir einen:

```bash
# Python-Shell im Backend-Container öffnen
podman-compose exec backend bash

# Im Container:
poetry run python

# In Python:
from goldsmith_erp.db.models import User
from goldsmith_erp.db.session import AsyncSessionLocal
from goldsmith_erp.core.security import get_password_hash
import asyncio

async def create_admin():
    async with AsyncSessionLocal() as db:
        admin = User(
            email="admin@goldsmith.local",
            hashed_password=get_password_hash("admin123"),
            first_name="Admin",
            last_name="User",
            is_active=True
        )
        db.add(admin)
        await db.commit()
        print("✅ Admin user created!")

asyncio.run(create_admin())
exit()
exit  # Container verlassen
```

**Jetzt einloggen:**
- URL: http://localhost:3000
- Email: `admin@goldsmith.local`
- Password: `admin123`

#### Schritt 8: Services verwalten

```bash
# Services stoppen
podman-compose -f podman-compose.yml stop

# Services neu starten
podman-compose -f podman-compose.yml restart

# Services + Container entfernen
podman-compose -f podman-compose.yml down

# Services + Container + Volumes (Daten!) entfernen
podman-compose -f podman-compose.yml down -v

# Logs live verfolgen
podman-compose -f podman-compose.yml logs -f backend

# Spezifischen Container neu bauen
podman-compose -f podman-compose.yml build --no-cache backend
```

---

## 🍎 macOS Installation

### Voraussetzungen

- **macOS 11 (Big Sur)** oder neuer
- **Homebrew** - Paketmanager
- **8 GB RAM** empfohlen

### Schritt 1: Homebrew installieren

Falls noch nicht installiert:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Schritt 2: Podman installieren

```bash
# Podman + Compose installieren
brew install podman podman-compose

# Podman Machine initialisieren (macOS benötigt VM)
podman machine init

# Podman Machine starten
podman machine start

# Installation prüfen
podman --version
podman-compose --version
```

**Erwartete Ausgabe:**
```
podman version 4.8.0
podman-compose version 1.0.6
Podman machine 'podman-machine-default' started successfully
```

### Schritt 3: Repository klonen

```bash
mkdir -p ~/Projects
cd ~/Projects
git clone https://github.com/arcsmax/goldsmith_erp.git
cd goldsmith_erp
```

### Schritt 4: .env konfigurieren

```bash
# .env erstellen
cp .env.example .env

# SECRET_KEY generieren
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(64))" >> .env

# Optional bearbeiten
open -e .env
```

### Schritt 5: Services starten

```bash
# Mit Makefile (einfachste Methode)
make start

# Oder manuell:
podman-compose -f podman-compose.yml up -d

# Status prüfen
make ps
# oder
podman-compose ps
```

### Schritt 6: Testen

- Backend: http://localhost:8000/docs
- Frontend: http://localhost:3000

### macOS-spezifische Tipps

**Podman Machine verwalten:**

```bash
# Status prüfen
podman machine list

# Stoppen
podman machine stop

# Neustarten
podman machine restart

# Ressourcen erhöhen (bei Performance-Problemen)
podman machine set --cpus 4 --memory 8192
```

**Apple Silicon (M1/M2/M3) Kompatibilität:**

Falls Probleme mit ARM64-Images auftreten:

```bash
# AMD64-Platform erzwingen
export DOCKER_DEFAULT_PLATFORM=linux/amd64

# Dann bauen
podman-compose build
```

---

## 🪟 Windows Installation

### Option 1: WSL2 + Podman (Empfohlen)

**Schritt 1: WSL2 installieren**

```powershell
# PowerShell als Administrator öffnen
wsl --install

# Computer neu starten (wenn nötig)

# Ubuntu installieren
wsl --install -d Ubuntu-22.04

# WSL2 Version prüfen
wsl -l -v

# Sollte Version 2 sein:
# * Ubuntu-22.04    Running    2
```

**Schritt 2: In WSL2 (Ubuntu) wechseln**

```powershell
wsl -d Ubuntu-22.04
```

**Ab jetzt: Folge der [Linux Installation](#linux-installation)**

### Option 2: Podman Desktop für Windows

**Schritt 1: Podman Desktop installieren**

1. Download: https://podman-desktop.io/downloads
2. Datei ausführen: `podman-desktop-setup-x.x.x.exe`
3. Installation durchführen
4. Podman Desktop starten

**Schritt 2: Podman Machine erstellen**

1. Podman Desktop öffnen
2. "Setup Podman" → "Initialize and start"
3. Warten bis "Podman is running"

**Schritt 3: Repository klonen**

```powershell
# Git Bash oder PowerShell
cd C:\Projects
git clone https://github.com/arcsmax/goldsmith_erp.git
cd goldsmith_erp
```

**Schritt 4: Services starten**

```powershell
# .env erstellen
copy .env.example .env

# Services starten
podman-compose -f podman-compose.yml up -d
```

### Windows-spezifische Tipps

**Ports freigeben:**

Falls Firewall-Probleme auftreten:

```powershell
# PowerShell als Admin
New-NetFirewallRule -DisplayName "Goldsmith Backend" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
New-NetFirewallRule -DisplayName "Goldsmith Frontend" -Direction Inbound -LocalPort 3000 -Protocol TCP -Action Allow
```

---

## 📦 Manuelle Installation (ohne Container)

### Backend (Python)

**Voraussetzungen:**
- Python 3.11+
- PostgreSQL 15+
- Redis 7+

**Schritt 1: Python-Dependencies installieren**

```bash
# Poetry installieren
curl -sSL https://install.python-poetry.org | python3 -

# Dependencies installieren
cd goldsmith_erp
poetry install

# Virtual Environment aktivieren
poetry shell
```

**Schritt 2: PostgreSQL + Redis starten**

**Option A: Mit Podman (nur DB/Redis)**

```bash
# Nur DB und Redis starten
podman-compose up -d db redis
```

**Option B: Nativ installiert**

```bash
# PostgreSQL starten
sudo systemctl start postgresql

# Redis starten
sudo systemctl start redis

# Database erstellen
sudo -u postgres psql -c "CREATE DATABASE goldsmith;"
sudo -u postgres psql -c "CREATE USER user WITH PASSWORD 'pass';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE goldsmith TO user;"
```

**Schritt 3: .env konfigurieren**

```bash
cp .env.example .env

# DATABASE_URL anpassen für lokale DB:
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/goldsmith
```

**Schritt 4: Migrationen ausführen**

```bash
# Alembic Migrationen
poetry run alembic upgrade head
```

**Schritt 5: Backend starten**

```bash
poetry run uvicorn goldsmith_erp.main:app --reload --host 0.0.0.0 --port 8000
```

Backend läuft auf: http://localhost:8000

### Frontend (React)

**Voraussetzungen:**
- Node.js 18+ oder 20+

**Schritt 1: Node.js installieren**

```bash
# Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# macOS
brew install node@20

# Verify
node --version
npm --version
```

**Schritt 2: Dependencies installieren**

```bash
cd frontend

# Yarn aktivieren
corepack enable

# Dependencies installieren
yarn install
```

**Schritt 3: Frontend starten**

```bash
yarn dev
```

Frontend läuft auf: http://localhost:3000

---

## 🛠 Entwicklungsumgebung einrichten

### Mit Makefile (Einfachste Methode)

```bash
# Alle verfügbaren Befehle anzeigen
make help

# Services starten
make start

# Logs anzeigen
make logs

# Backend Shell öffnen
make shell-backend

# PostgreSQL Shell öffnen
make shell-db

# Code formatieren
make format

# Tests ausführen
make test

# Migrationen ausführen
make migrate

# Neue Migration erstellen
make migrate-create MESSAGE="add_customer_table"
```

### VSCode Setup (Empfohlen)

**Extensions installieren:**

1. Python (ms-python.python)
2. Pylance (ms-python.vscode-pylance)
3. ESLint (dbaeumer.vscode-eslint)
4. Prettier (esbenp.prettier-vscode)
5. Docker (ms-azuretools.vscode-docker)

**Workspace Settings (`.vscode/settings.json`):**

```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.formatting.provider": "black",
  "editor.formatOnSave": true,
  "[python]": {
    "editor.defaultFormatter": "ms-python.black-formatter"
  },
  "[typescript]": {
    "editor.defaultFormatter": "esbenp.prettier-vscode"
  }
}
```

---

## 🔄 Migration von Docker zu Podman

### Schritt 1: Docker Services stoppen

```bash
# Docker stoppen (falls läuft)
docker-compose down

# Optional: Daten sichern
docker-compose exec db pg_dump -U user goldsmith > backup.sql
```

### Schritt 2: Podman installieren

Siehe [Linux Installation](#linux-installation) oben.

### Schritt 3: Alias erstellen (Docker-Kompatibilität)

```bash
# In ~/.bashrc oder ~/.zshrc
echo "alias docker=podman" >> ~/.bashrc
echo "alias docker-compose=podman-compose" >> ~/.bashrc

# Aktivieren
source ~/.bashrc

# Testen
docker ps
# Sollte jetzt Podman-Container zeigen!
```

### Schritt 4: Services mit Podman starten

```bash
# Mit neuem podman-compose.yml
podman-compose -f podman-compose.yml up -d

# Oder mit Makefile
make start
```

### Schritt 5: Daten wiederherstellen (falls gesichert)

```bash
# Backup einspielen
cat backup.sql | podman-compose exec -T db psql -U user goldsmith
```

**Fertig!** Alles läuft jetzt mit Podman.

---

## 🔧 Problemlösungen

### Problem: "podman: command not found"

**Linux:**
```bash
# Podman installieren
sudo apt-get install podman podman-compose
```

**macOS:**
```bash
brew install podman podman-compose
podman machine init
podman machine start
```

### Problem: "Error: short-name resolution is enforced"

**Fehler:**
```
Error: short-name "postgres:15" did not resolve to an alias
```

**Lösung:** Vollständige Image-Namen verwenden

```yaml
# In podman-compose.yml - BEREITS GEFIXT!
image: docker.io/library/postgres:15-alpine  # ✅
# statt
image: postgres:15  # ❌
```

### Problem: "permission denied" bei Volumes

**Fehler:**
```
Error: error mounting "/path": permission denied
```

**Lösung:** SELinux Labels hinzufügen (`:Z` oder `:z`)

```yaml
# In podman-compose.yml - BEREITS GEFIXT!
volumes:
  - ./src:/app/src:Z  # ✅ :Z für SELinux
```

### Problem: Container können nicht auf Host zugreifen

**Lösung:** `host.containers.internal` verwenden

```env
# Statt localhost:
DATABASE_URL=postgresql://user:pass@host.containers.internal:5432/db
```

### Problem: Port bereits belegt

```bash
# Port 8000 prüfen
sudo lsof -i :8000

# Prozess beenden
kill -9 <PID>

# Oder anderen Port in podman-compose.yml:
ports:
  - "8080:8000"  # Backend jetzt auf 8080
```

### Problem: Podman Machine startet nicht (macOS)

```bash
# Machine neu initialisieren
podman machine stop
podman machine rm
podman machine init --cpus 4 --memory 8192
podman machine start
```

### Problem: Rootless Podman - "unprivileged user namespaces are disabled"

```bash
# Ubuntu/Debian
echo 'kernel.unprivileged_userns_clone=1' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# Fedora (meist voractiviert)
sudo grubby --update-kernel=ALL --args="namespace.unpriv_enable=1"
```

### Problem: Build schlägt fehl mit "no space left on device"

```bash
# Podman Speicher bereinigen
podman system prune -af --volumes

# Speicher prüfen
podman system df
```

---

## ❓ Häufig gestellte Fragen

### Wie aktualisiere ich die Anwendung?

```bash
# Code aktualisieren
git pull origin main

# Container neu bauen und starten
make build
make start

# Oder manuell:
podman-compose down
podman-compose build --no-cache
podman-compose up -d
```

### Wie setze ich die Datenbank zurück?

```bash
# ACHTUNG: Löscht alle Daten!
make clean

# Oder manuell:
podman-compose down -v
podman-compose up -d
```

### Wie greife ich auf die Datenbank zu?

```bash
# Mit Makefile
make shell-db

# Oder manuell
podman-compose exec db psql -U user -d goldsmith

# Mit GUI-Tool (z.B. DBeaver, pgAdmin):
# Host: localhost
# Port: 5432
# User: user
# Password: pass
# Database: goldsmith
```

### Wie sehe ich die Logs?

```bash
# Mit Makefile
make logs              # Alle Logs
make logs-backend      # Nur Backend
make logs-frontend     # Nur Frontend

# Oder manuell
podman-compose logs -f backend
```

### Wie führe ich Migrationen aus?

```bash
# Mit Makefile
make migrate                                # Apply migrations
make migrate-create MESSAGE="add_customer" # Create new migration

# Oder manuell
podman-compose exec backend poetry run alembic upgrade head
podman-compose exec backend poetry run alembic revision --autogenerate -m "message"
```

### Wie führe ich Tests aus?

```bash
# Mit Makefile
make test              # All tests
make test-cov          # With coverage report

# Oder manuell
podman-compose exec backend poetry run pytest -v
```

### Wie erstelle ich Seed-Daten?

```bash
# Standard-Aktivitäten seeden
podman-compose exec backend python -m goldsmith_erp.db.seed_data
```

### Kann ich Docker UND Podman parallel nutzen?

Ja, aber nicht empfohlen. Wenn du Docker entfernen willst:

```bash
# Docker vollständig entfernen (Ubuntu)
sudo apt-get purge docker-ce docker-ce-cli containerd.io
sudo rm -rf /var/lib/docker

# Dann Alias setzen
alias docker=podman
```

### Wie verwende ich es in Production?

**Option 1: Systemd Services (Empfohlen für Single Server)**

```bash
# Systemd Services generieren
cd ~/.config/systemd/user/
podman generate systemd --new --files --name goldsmith-backend

# Services aktivieren
systemctl --user enable container-goldsmith-backend.service
systemctl --user start container-goldsmith-backend.service

# Auto-Start bei Boot
loginctl enable-linger $USER
```

**Option 2: Kubernetes Pod Deployment**

```bash
# Pod Manifest verwenden
podman play kube podman-pod.yaml

# Oder nach Kubernetes deployen
kubectl apply -f podman-pod.yaml
```

### Wie erstelle ich Backups?

```bash
# Mit Makefile
make backup-db

# Backups liegen in ./backups/
ls backups/

# Backup wiederherstellen
make restore-db FILE=backups/goldsmith_20250109_120000.sql
```

---

## 📞 Support

Bei Problemen:

1. **Logs prüfen:**
   ```bash
   make logs
   ```

2. **Podman Docs:**
   - https://docs.podman.io/
   - https://github.com/containers/podman

3. **GitHub Issues:**
   - Durchsuchen: https://github.com/arcsmax/goldsmith_erp/issues
   - Neu erstellen: Mit OS, Podman-Version, Logs

4. **Podman Migration Guide:**
   - [PODMAN_MIGRATION.md](PODMAN_MIGRATION.md)

---

## ✅ Installation erfolgreich?

Prüfe ob alles läuft:

```bash
# Health Check
make health

# Sollte zeigen:
# ✅ Backend: http://localhost:8000/health
# ✅ Frontend: http://localhost:3000
# ✅ Database: Ready
# ✅ Redis: PONG
```

**Nächste Schritte:**
1. Admin-User erstellen (siehe Schritt 7)
2. Frontend öffnen: http://localhost:3000
3. Einloggen und testen!
4. [MVP Analysis](MVP_ANALYSIS.md) lesen für nächste Features

---

**Viel Erfolg mit Goldsmith ERP! 🚀**

**Powered by Podman - Secure, Rootless, Container-Native**

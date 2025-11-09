# Goldsmith ERP - Installationsanleitung

Detaillierte Schritt-für-Schritt-Anleitung zur Installation von Goldsmith ERP auf verschiedenen Betriebssystemen.

---

## 📋 Inhaltsverzeichnis

- [Windows Installation](#windows-installation)
- [macOS Installation](#macos-installation)
- [Linux Installation](#linux-installation)
- [Entwicklungsumgebung einrichten](#entwicklungsumgebung-einrichten)
- [Problemlösungen](#problemlösungen)
- [Häufig gestellte Fragen](#häufig-gestellte-fragen)

---

## 🪟 Windows Installation

### Voraussetzungen

Folgende Software wird benötigt:

- **Windows 10/11** (64-bit)
- **Git for Windows** - [Download](https://git-scm.com/download/win)
- **Docker Desktop für Windows** - [Download](https://www.docker.com/products/docker-desktop)

### Schritt 1: Git installieren

1. **Git herunterladen:**
   - Besuchen Sie https://git-scm.com/download/win
   - Laden Sie die neueste Version herunter (z.B., `Git-2.43.0-64-bit.exe`)

2. **Git installieren:**
   - Führen Sie die heruntergeladene Datei aus
   - Wählen Sie "Git from the command line and also from 3rd-party software"
   - Verwenden Sie die empfohlenen Standardeinstellungen
   - Klicken Sie auf "Install"

3. **Installation überprüfen:**
   ```cmd
   git --version
   ```
   Erwartete Ausgabe: `git version 2.43.0` (oder neuer)

### Schritt 2: Docker Desktop installieren

1. **Docker Desktop herunterladen:**
   - Besuchen Sie https://www.docker.com/products/docker-desktop
   - Klicken Sie auf "Download for Windows"

2. **Docker Desktop installieren:**
   - Führen Sie `Docker Desktop Installer.exe` aus
   - Aktivieren Sie "Use WSL 2 instead of Hyper-V" (empfohlen)
   - Folgen Sie dem Installationsassistenten
   - **Neustart erforderlich**

3. **Docker Desktop starten:**
   - Starten Sie "Docker Desktop" aus dem Startmenü
   - Warten Sie, bis der Docker-Daemon läuft (Whale-Icon in der Taskleiste wird grün)

4. **Installation überprüfen:**
   Öffnen Sie PowerShell oder CMD:
   ```cmd
   docker --version
   docker-compose --version
   ```
   Erwartete Ausgabe:
   ```
   Docker version 24.0.7
   Docker Compose version v2.23.3
   ```

### Schritt 3: Repository klonen

1. **Ordner erstellen (optional):**
   ```cmd
   mkdir C:\Projects
   cd C:\Projects
   ```

2. **Repository klonen:**
   ```cmd
   git clone https://github.com/arcsmax/goldsmith_erp.git
   cd goldsmith_erp
   ```

### Schritt 4: Umgebungsvariablen konfigurieren

1. **`.env` Datei erstellen:**
   ```cmd
   copy .env.example .env
   ```

   Falls `.env.example` nicht existiert, erstellen Sie `.env` manuell:
   ```cmd
   notepad .env
   ```

   Fügen Sie folgenden Inhalt ein:
   ```env
   # Database
   POSTGRES_USER=user
   POSTGRES_PASSWORD=pass
   POSTGRES_DB=goldsmith
   POSTGRES_HOST=db

   # Redis
   REDIS_URL=redis://redis:6379/0

   # Security
   SECRET_KEY=change_this_to_a_secure_random_string_min_32_chars

   # App
   DEBUG=true
   ```

2. **Speichern:** `Strg+S`, dann schließen

### Schritt 5: Anwendung starten

1. **Docker Compose ausführen:**
   ```cmd
   docker-compose up --build
   ```

   **Erster Start dauert 5-10 Minuten** (Downloads von Images und Dependencies)

2. **Erfolgsmeldungen abwarten:**
   ```
   ✓ Container goldsmith_erp-db-1        Started
   ✓ Container goldsmith_erp-redis-1     Started
   ✓ Container goldsmith_erp-backend-1   Started
   ✓ Container goldsmith_erp-frontend-1  Started
   ```

3. **Anwendung testen:**
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - Frontend: http://localhost:3000

### Schritt 6: Anwendung stoppen

```cmd
# Im Terminal: Strg+C drücken

# Container vollständig entfernen:
docker-compose down

# Container + Volumes entfernen (Daten löschen):
docker-compose down -v
```

---

## 🍎 macOS Installation

### Voraussetzungen

Folgende Software wird benötigt:

- **macOS 11 (Big Sur)** oder neuer
- **Homebrew** - Paketmanager für macOS
- **Git** - Version Control
- **Docker Desktop für Mac** - Containerisierung

### Schritt 1: Homebrew installieren

1. **Homebrew installieren:**

   Öffnen Sie Terminal (⌘+Leertaste → "Terminal" eingeben):
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

2. **Installation überprüfen:**
   ```bash
   brew --version
   ```
   Erwartete Ausgabe: `Homebrew 4.x.x`

### Schritt 2: Git installieren

Git ist normalerweise vorinstalliert. Falls nicht:

```bash
brew install git
```

**Installation überprüfen:**
```bash
git --version
```

### Schritt 3: Docker Desktop installieren

**Option A: Mit Homebrew (empfohlen)**
```bash
brew install --cask docker
```

**Option B: Manueller Download**

1. **Docker Desktop herunterladen:**
   - Besuchen Sie https://www.docker.com/products/docker-desktop
   - Klicken Sie auf "Download for Mac"
   - Wählen Sie die richtige Version:
     - **Apple Silicon (M1/M2/M3):** "Mac with Apple chip"
     - **Intel Mac:** "Mac with Intel chip"

2. **Docker Desktop installieren:**
   - Öffnen Sie die heruntergeladene `.dmg` Datei
   - Ziehen Sie Docker in den Applications-Ordner
   - Öffnen Sie Docker aus dem Applications-Ordner
   - Klicken Sie auf "Öffnen" bei der Sicherheitswarnung

3. **Docker Desktop starten:**
   - Docker startet automatisch
   - Warten Sie, bis das Wal-Icon in der Menüleiste erscheint

4. **Installation überprüfen:**
   ```bash
   docker --version
   docker-compose --version
   ```

### Schritt 4: Repository klonen

1. **Arbeitsverzeichnis erstellen (optional):**
   ```bash
   mkdir -p ~/Projects
   cd ~/Projects
   ```

2. **Repository klonen:**
   ```bash
   git clone https://github.com/arcsmax/goldsmith_erp.git
   cd goldsmith_erp
   ```

### Schritt 5: Umgebungsvariablen konfigurieren

1. **`.env` Datei erstellen:**
   ```bash
   cp .env.example .env
   ```

   Falls `.env.example` nicht existiert:
   ```bash
   cat > .env << 'EOF'
   # Database
   POSTGRES_USER=user
   POSTGRES_PASSWORD=pass
   POSTGRES_DB=goldsmith
   POSTGRES_HOST=db

   # Redis
   REDIS_URL=redis://redis:6379/0

   # Security
   SECRET_KEY=change_this_to_a_secure_random_string_min_32_chars

   # App
   DEBUG=true
   EOF
   ```

2. **.env bearbeiten (optional):**
   ```bash
   nano .env
   # oder
   open -e .env
   ```

### Schritt 6: Anwendung starten

1. **Docker Compose ausführen:**
   ```bash
   docker-compose up --build
   ```

   **Hinweis für Apple Silicon (M1/M2/M3):**
   Falls Probleme auftreten, verwenden Sie:
   ```bash
   DOCKER_DEFAULT_PLATFORM=linux/amd64 docker-compose up --build
   ```

2. **Erfolgreich gestartet:**
   ```
   ✓ Container goldsmith_erp-db-1        Started
   ✓ Container goldsmith_erp-redis-1     Started
   ✓ Container goldsmith_erp-backend-1   Started
   ✓ Container goldsmith_erp-frontend-1  Started
   ```

3. **Anwendung öffnen:**
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - Frontend: http://localhost:3000

### Schritt 7: Anwendung stoppen

```bash
# Im Terminal: Ctrl+C drücken

# Container stoppen:
docker-compose down

# Container + Daten löschen:
docker-compose down -v
```

---

## 🐧 Linux Installation

### Voraussetzungen

- **Ubuntu 20.04+** / **Debian 11+** / **Fedora 36+**
- **Root oder sudo Zugriff**

### Schritt 1: Git installieren

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install git -y
```

**Fedora:**
```bash
sudo dnf install git -y
```

**Überprüfen:**
```bash
git --version
```

### Schritt 2: Docker installieren

**Ubuntu/Debian:**
```bash
# Alte Versionen entfernen
sudo apt remove docker docker-engine docker.io containerd runc

# Abhängigkeiten installieren
sudo apt update
sudo apt install ca-certificates curl gnupg lsb-release -y

# Docker GPG Key hinzufügen
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Docker Repository hinzufügen
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Docker installieren
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-compose-plugin -y

# Docker ohne sudo nutzen
sudo usermod -aG docker $USER
newgrp docker
```

**Fedora:**
```bash
sudo dnf install docker docker-compose -y
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
newgrp docker
```

**Überprüfen:**
```bash
docker --version
docker compose version
```

### Schritt 3: Repository klonen

```bash
mkdir -p ~/Projects
cd ~/Projects
git clone https://github.com/arcsmax/goldsmith_erp.git
cd goldsmith_erp
```

### Schritt 4: Umgebungsvariablen konfigurieren

```bash
cp .env.example .env
nano .env  # oder vi .env
```

### Schritt 5: Anwendung starten

```bash
docker compose up --build
```

**Hinweis:** Bei älteren Docker-Versionen: `docker-compose` (mit Bindestrich)

---

## 🛠 Entwicklungsumgebung einrichten

Für aktive Entwicklung ohne Docker:

### Backend-Entwicklung

**Voraussetzungen:**
- Python 3.11 oder höher
- Poetry (Python Package Manager)

**Installation:**

1. **Python 3.11+ installieren:**

   **Windows:**
   - Download: https://www.python.org/downloads/
   - Aktivieren Sie "Add Python to PATH"

   **macOS:**
   ```bash
   brew install python@3.11
   ```

   **Linux:**
   ```bash
   sudo apt install python3.11 python3.11-venv python3-pip
   ```

2. **Poetry installieren:**
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```

   **Windows (PowerShell):**
   ```powershell
   (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
   ```

3. **Dependencies installieren:**
   ```bash
   cd goldsmith_erp
   poetry install
   ```

4. **PostgreSQL & Redis starten (Docker):**
   ```bash
   docker-compose up -d db redis
   ```

5. **Datenbank-Migrationen ausführen:**
   ```bash
   poetry run alembic upgrade head
   ```

6. **Backend-Server starten:**
   ```bash
   poetry run uvicorn goldsmith_erp.main:app --reload --host 0.0.0.0 --port 8000
   ```

### Frontend-Entwicklung

**Voraussetzungen:**
- Node.js 18+ oder 20+
- Yarn 4.x

**Installation:**

1. **Node.js installieren:**

   **Windows:**
   - Download: https://nodejs.org/ (LTS Version)

   **macOS:**
   ```bash
   brew install node@20
   ```

   **Linux:**
   ```bash
   curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
   sudo apt install nodejs -y
   ```

2. **Yarn aktivieren:**
   ```bash
   corepack enable
   ```

3. **Dependencies installieren:**
   ```bash
   cd frontend
   yarn install
   ```

4. **Development-Server starten:**
   ```bash
   yarn dev
   ```

   Frontend läuft auf: http://localhost:3000

---

## 🔧 Problemlösungen

### Problem: Docker startet nicht

**Windows:**
- Stellen Sie sicher, dass Hyper-V oder WSL 2 aktiviert ist
- Öffnen Sie Docker Desktop als Administrator
- Prüfen Sie unter "Settings" → "Resources" ob genug RAM/CPU zugewiesen ist

**macOS:**
- Öffnen Sie "Systemeinstellungen" → "Sicherheit" → Docker erlauben
- Stellen Sie sicher, dass Docker Desktop vollständig installiert ist

### Problem: Port bereits belegt

```bash
# Fehler: "Bind for 0.0.0.0:8000 failed: port is already allocated"
```

**Lösung:**

**Windows:**
```cmd
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

**macOS/Linux:**
```bash
lsof -ti:8000 | xargs kill -9
```

**Alternative:** Ports in `docker-compose.yml` ändern:
```yaml
ports:
  - "8001:8000"  # Externer Port 8001 statt 8000
```

### Problem: Datenbank-Verbindungsfehler

```
sqlalchemy.exc.OperationalError: could not translate host name "db"
```

**Lösung:**
1. Stellen Sie sicher, dass PostgreSQL-Container läuft:
   ```bash
   docker ps | grep postgres
   ```

2. Container neu starten:
   ```bash
   docker-compose restart db
   ```

3. Logs prüfen:
   ```bash
   docker-compose logs db
   ```

### Problem: Migration-Fehler

```
alembic.util.exc.CommandError: Can't locate revision identified by 'xxxx'
```

**Lösung:**
```bash
# Container stoppen und Datenbank zurücksetzen
docker-compose down -v

# Container neu starten
docker-compose up --build
```

### Problem: Frontend lädt nicht

**Symptom:** Weiße Seite oder "Cannot connect to server"

**Lösung:**
1. Prüfen Sie, ob Backend läuft: http://localhost:8000/docs
2. Browser-Console öffnen (F12) → Fehler prüfen
3. Frontend-Container neu starten:
   ```bash
   docker-compose restart frontend
   docker-compose logs frontend
   ```

### Problem: Apple Silicon (M1/M2/M3) Kompatibilität

**Fehler:** "no matching manifest for linux/arm64/v8"

**Lösung:**
```bash
export DOCKER_DEFAULT_PLATFORM=linux/amd64
docker-compose up --build
```

Oder in `docker-compose.yml` hinzufügen:
```yaml
services:
  backend:
    platform: linux/amd64
```

---

## ❓ Häufig gestellte Fragen

### Wie aktualisiere ich die Anwendung?

```bash
# Code aktualisieren
git pull origin main

# Container neu bauen
docker-compose down
docker-compose up --build
```

### Wie setze ich die Datenbank zurück?

```bash
# Alle Container und Volumes löschen
docker-compose down -v

# Neu starten
docker-compose up --build
```

### Wie greife ich auf die Datenbank zu?

```bash
# PostgreSQL CLI öffnen
docker-compose exec db psql -U user -d goldsmith

# Oder mit GUI-Tool (z.B. pgAdmin):
# Host: localhost
# Port: 5432
# User: user
# Password: pass
# Database: goldsmith
```

### Wie sehe ich die Logs?

```bash
# Alle Logs
docker-compose logs

# Nur Backend
docker-compose logs backend

# Logs folgen (live)
docker-compose logs -f backend
```

### Wie führe ich Tests aus?

```bash
# Backend-Tests
docker-compose exec backend poetry run pytest

# Oder lokal:
poetry run pytest

# Frontend-Tests (wenn implementiert)
cd frontend
yarn test
```

### Kann ich einen anderen Port nutzen?

Ja, bearbeiten Sie `docker-compose.yml`:

```yaml
services:
  backend:
    ports:
      - "8080:8000"  # Backend auf Port 8080

  frontend:
    ports:
      - "3001:3000"  # Frontend auf Port 3001
```

### Wie erstelle ich einen Admin-User?

```bash
# Python-Shell im Backend-Container öffnen
docker-compose exec backend poetry run python

# In der Python-Shell:
from goldsmith_erp.db.models import User, Base
from goldsmith_erp.db.session import SessionLocal
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
db = SessionLocal()

admin = User(
    email="admin@goldsmith.local",
    hashed_password=pwd_context.hash("admin123"),
    first_name="Admin",
    last_name="User",
    is_active=True
)

db.add(admin)
db.commit()
print("Admin user created!")
```

---

## 📞 Support

Bei Problemen:

1. **Logs prüfen:** `docker-compose logs`
2. **Issues durchsuchen:** https://github.com/arcsmax/goldsmith_erp/issues
3. **Neues Issue erstellen:** Beschreiben Sie das Problem mit:
   - Betriebssystem und Version
   - Docker-Version
   - Fehlermeldung
   - Schritte zur Reproduktion

---

**Viel Erfolg mit Goldsmith ERP! 🚀**

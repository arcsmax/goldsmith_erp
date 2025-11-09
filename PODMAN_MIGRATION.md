# Podman Migration Guide

## 🎯 Warum Podman?

Goldsmith ERP wurde von Docker auf **Podman** migriert für verbesserte Sicherheit und Performance:

### Vorteile von Podman

| Feature | Docker | Podman |
|---------|--------|--------|
| **Rootless** | ❌ Daemon läuft als Root | ✅ Komplett rootless möglich |
| **Daemon** | ❌ Erfordert Docker Daemon | ✅ Daemonless Architecture |
| **Pods** | ❌ Nur einzelne Container | ✅ Kubernetes-style Pods |
| **Security** | ⚠️ Privileged Daemon | ✅ User Namespaces |
| **Systemd** | ⚠️ Separate Integration | ✅ Native Systemd Support |
| **Kubernetes** | ⚠️ Separate Deployment | ✅ `podman play kube` |
| **Drop-in** | - | ✅ Docker-kompatible CLI |

### Security Improvements

**Docker Architecture:**
```
User (unprivileged)
   ↓
Docker CLI
   ↓
Docker Daemon (ROOT!) ← Security Risk
   ↓
Container (root inside)
```

**Podman Architecture:**
```
User (unprivileged)
   ↓
Podman CLI (rootless)
   ↓
Container (user namespaces)
```

- ✅ Kein privilegierter Daemon
- ✅ Container laufen unter User-UID
- ✅ SELinux/AppArmor kompatibel
- ✅ Kleinere Attack Surface

---

## 🚀 Installation

### Option 1: Automatisches Setup-Script (Empfohlen)

```bash
cd goldsmith_erp
./setup-podman.sh
```

Das Script installiert:
- Podman + podman-compose
- Buildah (Container Build Tool)
- Skopeo (Image Management)
- Konfiguriert Rootless Mode
- Erstellt .env mit sicherem SECRET_KEY
- Startet alle Services

### Option 2: Manuelle Installation

**Ubuntu/Debian 22.04+:**
```bash
sudo apt-get update
sudo apt-get install -y podman podman-compose buildah skopeo
```

**Fedora/RHEL 9+:**
```bash
sudo dnf install -y podman podman-compose buildah skopeo
```

**macOS:**
```bash
brew install podman podman-compose
podman machine init
podman machine start
```

**Windows (WSL2):**
```powershell
# In WSL2 Ubuntu
sudo apt-get install -y podman podman-compose
```

---

## 📦 Projekt-Dateien

### Neue Podman-spezifische Dateien

```
goldsmith_erp/
├── podman-compose.yml          # Podman Compose Config (Docker-kompatibel)
├── Containerfile              # Backend Container (statt Dockerfile)
├── frontend/Containerfile     # Frontend Container
├── podman-pod.yaml            # Kubernetes-style Pod Manifest
├── setup-podman.sh            # Automatisches Setup
├── Makefile                   # Einfache Befehle
└── PODMAN_MIGRATION.md        # Diese Datei
```

### Alte Docker-Dateien (Optional behalten für Kompatibilität)

```
├── docker-compose.yml         # Kann gelöscht werden
├── Dockerfile                 # Kann gelöscht werden
└── frontend/Dockerfile        # Kann gelöscht werden
```

---

## 🛠️ Verwendung

### Methode 1: Makefile (Einfachste)

```bash
# Services starten
make start

# Logs anzeigen
make logs

# Backend Shell
make shell-backend

# Alles anzeigen
make help
```

### Methode 2: podman-compose (Docker-kompatibel)

```bash
# Starten
podman-compose -f podman-compose.yml up -d

# Stoppen
podman-compose -f podman-compose.yml down

# Logs
podman-compose -f podman-compose.yml logs -f

# Rebuild
podman-compose -f podman-compose.yml build --no-cache
```

### Methode 3: Native Podman Pods (Kubernetes-style)

```bash
# Build Images
podman build -t goldsmith-backend:latest -f Containerfile .
podman build -t goldsmith-frontend:latest -f frontend/Containerfile ./frontend

# Pod erstellen und starten
podman play kube podman-pod.yaml

# Pod stoppen
podman play kube --down podman-pod.yaml

# Pod Status
podman pod ps
podman ps -a --pod
```

---

## 🔄 Migration von Docker zu Podman

### Schritt-für-Schritt Migration

**1. Docker-Services stoppen**
```bash
docker-compose down -v  # ACHTUNG: Löscht Volumes!
# Oder ohne -v um Daten zu behalten:
docker-compose down
```

**2. Daten sichern (Falls nötig)**
```bash
# PostgreSQL Backup
docker-compose exec db pg_dump -U user goldsmith > backup.sql

# Redis Backup
docker-compose exec redis redis-cli SAVE
```

**3. Podman installieren**
```bash
./setup-podman.sh
# Oder manuell (siehe oben)
```

**4. Services mit Podman starten**
```bash
make start
# Oder:
podman-compose -f podman-compose.yml up -d
```

**5. Daten wiederherstellen (Falls nötig)**
```bash
# PostgreSQL Restore
cat backup.sql | podman-compose exec -T db psql -U user goldsmith
```

**6. Aliase für Docker-Kompatibilität**
```bash
# In ~/.bashrc oder ~/.zshrc
alias docker=podman
alias docker-compose=podman-compose

source ~/.bashrc
```

### Wichtige Unterschiede

| Befehl | Docker | Podman |
|--------|--------|--------|
| Start | `docker-compose up` | `podman-compose up` |
| Build | `docker build` | `podman build` oder `buildah` |
| Images | `docker images` | `podman images` |
| Push | `docker push` | `podman push` oder `skopeo` |
| Network | `docker network` | `podman network` |
| Volume | `docker volume` | `podman volume` |

---

## 🔒 Rootless Mode

Podman's größter Vorteil ist **rootless mode** - Container laufen komplett ohne Root-Rechte.

### Rootless aktivieren

```bash
# User Namespaces konfigurieren (falls noch nicht)
echo "$USER:100000:65536" | sudo tee -a /etc/subuid
echo "$USER:100000:65536" | sudo tee -a /etc/subgid

# Podman migrieren
podman system migrate

# Lingering aktivieren (Container überleben Logout)
loginctl enable-linger $USER
```

### Rootless Ports < 1024

Standardmäßig können unprivilegierte User keine Ports < 1024 binden.

**Lösung 1: High Ports verwenden (Empfohlen)**
```yaml
# podman-compose.yml
ports:
  - "8000:8000"  # OK
  - "3000:3000"  # OK
```

**Lösung 2: Port-Mapping erlauben**
```bash
# System-weit
echo 'net.ipv4.ip_unprivileged_port_start=80' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### Rootless Storage

```bash
# Storage Config
~/.config/containers/storage.conf

# Volumes Location
~/.local/share/containers/storage/volumes/
```

---

## 🏗️ Development Workflow

### Backend Development

```bash
# Außerhalb Container (direkt)
cd goldsmith_erp
poetry install
poetry run uvicorn goldsmith_erp.main:app --reload

# In Container
make shell-backend
poetry run uvicorn goldsmith_erp.main:app --reload
```

### Frontend Development

```bash
# Außerhalb Container
cd frontend
yarn install
yarn dev

# In Container
make shell-frontend
yarn dev
```

### Database Operations

```bash
# Migrations
make migrate                           # Apply migrations
make migrate-create MESSAGE="add_foo"  # Create migration

# Shell
make shell-db                          # PostgreSQL CLI
make shell-redis                       # Redis CLI

# Backup/Restore
make backup-db                         # Backup to ./backups/
make restore-db FILE=backup.sql        # Restore
```

---

## 🎛️ Systemd Integration

Podman hat **native Systemd Support** - Container können als System Services laufen.

### Service erstellen

```bash
# Pod als Service (rootless)
cd ~/.config/systemd/user/

# Service generieren
podman generate systemd --new --files --name goldsmith-erp

# Services aktivieren
systemctl --user enable container-goldsmith-backend.service
systemctl --user enable container-goldsmith-frontend.service
systemctl --user enable container-goldsmith-db.service

# Starten
systemctl --user start container-goldsmith-backend.service
```

### Auto-Start bei Boot

```bash
# User Lingering aktivieren
loginctl enable-linger $USER

# Services bei Boot starten
systemctl --user enable container-goldsmith-backend.service
```

---

## 🐛 Troubleshooting

### Problem: "short-name resolution is enforced"

**Fehler:**
```
Error: short-name "postgres:15" did not resolve to an alias
```

**Lösung:** Vollständigen Image-Namen verwenden
```yaml
# Statt:
image: postgres:15

# Verwenden:
image: docker.io/library/postgres:15
```

### Problem: "permission denied" bei Volumes

**Fehler:**
```
Error: permission denied
```

**Lösung:** SELinux Labels für Podman
```yaml
volumes:
  - ./src:/app/src:Z  # :Z für SELinux
```

### Problem: Container können nicht auf Host zugreifen

**Lösung:** `host.containers.internal` verwenden
```yaml
environment:
  - DATABASE_URL=postgresql://user:pass@host.containers.internal:5432/db
```

### Problem: Network not found

**Lösung:** Podman erstellt Networks automatisch, aber manchmal:
```bash
podman network create goldsmith-network
```

### Logs aktivieren

```bash
# Debug Logs
export PODMAN_LOG_LEVEL=debug
podman-compose up

# Systemd Journal
journalctl --user -u container-goldsmith-backend -f
```

---

## 🔐 Security Best Practices

### 1. Secrets Management

**NICHT:**
```yaml
environment:
  - SECRET_KEY=hardcoded_secret  # ❌ Niemals!
```

**BESSER:**
```yaml
environment:
  - SECRET_KEY=${SECRET_KEY}  # ✅ Aus .env
```

**AM BESTEN:** Podman Secrets
```bash
# Secret erstellen
echo "super_secure_key" | podman secret create db_password -

# In Compose verwenden
services:
  db:
    secrets:
      - db_password

secrets:
  db_password:
    external: true
```

### 2. Read-Only Root Filesystem

```yaml
services:
  backend:
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp
```

### 3. Capabilities droppen

```yaml
services:
  backend:
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE  # Nur wenn Port < 1024
```

### 4. User Namespaces

```yaml
services:
  backend:
    user: "1000:1000"  # Non-root user
```

---

## 📊 Performance

### Build Performance

**Podman vs Docker:**
- Podman: Nutzt **Buildah** intern
- Ähnliche Performance
- Besseres Layer Caching

**Optimization:**
```bash
# Multi-stage builds nutzen
# Layer caching optimieren
# BuildKit aktivieren (Podman 4.0+)
export BUILDAH_FORMAT=docker
```

### Runtime Performance

**Podman:**
- Kein Daemon-Overhead
- Direkte Container-Prozesse
- Bessere Resource Isolation

**Benchmark:**
```bash
# Container Start Zeit
time podman run --rm alpine echo "hello"
# vs
time docker run --rm alpine echo "hello"
```

---

## 🚢 Production Deployment

### Option 1: Systemd Services (Single Server)

```bash
# Generate unit files
podman generate systemd --new --files --name goldsmith-erp

# Install
sudo cp *.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now container-goldsmith-backend
```

### Option 2: Kubernetes/OpenShift

```bash
# Podman kann direkt Kubernetes YAML generieren!
podman generate kube goldsmith-erp > deployment.yaml

# Deploy zu K8s
kubectl apply -f deployment.yaml
```

### Option 3: Podman Play Kube (K8s-compatible)

```bash
# Nutzt podman-pod.yaml
podman play kube podman-pod.yaml

# Als Service
systemctl --user enable --now pod-goldsmith-erp
```

---

## 📚 Weitere Ressourcen

**Offizielle Dokumentation:**
- [Podman Docs](https://docs.podman.io/)
- [Podman Compose](https://github.com/containers/podman-compose)
- [Buildah](https://buildah.io/)
- [Skopeo](https://github.com/containers/skopeo)

**Tutorials:**
- [Rootless Tutorial](https://github.com/containers/podman/blob/main/docs/tutorials/rootless_tutorial.md)
- [Systemd Integration](https://www.redhat.com/sysadmin/podman-systemd-unit-files)
- [Migration Guide](https://podman.io/blogs/2019/10/29/podman-crun-f31.html)

**Community:**
- [Podman GitHub](https://github.com/containers/podman)
- [Reddit r/podman](https://reddit.com/r/podman)
- [Matrix Chat](https://matrix.to/#/#podman:fedoraproject.org)

---

## ✅ Checkliste: Docker → Podman Migration

- [ ] Podman installiert (`podman --version`)
- [ ] podman-compose installiert
- [ ] Rootless konfiguriert (subuid/subgid)
- [ ] Docker Services gestoppt
- [ ] Daten gesichert (DB Backup)
- [ ] .env Datei erstellt
- [ ] SECRET_KEY generiert
- [ ] Podman Services gestartet (`make start`)
- [ ] Health Checks bestanden (`make health`)
- [ ] Daten migriert (falls nötig)
- [ ] Aliase konfiguriert (`docker=podman`)
- [ ] Systemd Services erstellt (Optional)
- [ ] Auto-Start aktiviert (Optional)
- [ ] Alte Docker-Dateien entfernt (Optional)

---

**🎉 Herzlichen Glückwunsch! Goldsmith ERP läuft jetzt sicher mit Podman!**

Bei Fragen: [GitHub Issues](https://github.com/arcsmax/goldsmith_erp/issues)

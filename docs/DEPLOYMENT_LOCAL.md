# Goldsmith ERP - Local Network Deployment

## Overview

Goldsmith ERP ist designed für **lokalen Betrieb im Werkstatt-Netzwerk**. Das System läuft auf einem zentralen Windows-PC und alle Geräte (Tablets, Smartphones, andere PCs) im gleichen Netzwerk können darauf zugreifen.

---

## Deployment Architecture

### Network Topology

```
                    Internet (optional)
                           │
                           ▼
┌──────────────────────────────────────────────────────┐
│              Local Network (LAN)                      │
│                192.168.1.0/24                         │
│                                                       │
│   ┌─────────────────────────────────┐               │
│   │  Windows Server PC              │               │
│   │  (192.168.1.10)                │               │
│   │                                 │               │
│   │  ┌──────────────────────────┐  │               │
│   │  │  Docker Desktop          │  │               │
│   │  │  ├─ PostgreSQL :5432     │  │               │
│   │  │  ├─ Redis :6379          │  │               │
│   │  │  ├─ Backend :8000        │  │               │
│   │  │  └─ Frontend :3000       │  │               │
│   │  └──────────────────────────┘  │               │
│   └─────────────────────────────────┘               │
│                    ▲                                  │
│                    │ HTTP/WebSocket                  │
│        ┌───────────┴───────────┬──────────┐         │
│        │                       │          │         │
│   ┌────▼─────┐          ┌─────▼───┐  ┌───▼────┐   │
│   │ Tablet 1 │          │ Phone 1 │  │  PC 2  │   │
│   │(Android) │          │  (iOS)  │  │(Windows│   │
│   └──────────┘          └─────────┘  └────────┘   │
└──────────────────────────────────────────────────────┘
```

### Key Points

1. **Central Server**: Ein Windows-PC fungiert als Server
2. **Same Network**: Alle Geräte sind im gleichen LAN (oder WLAN)
3. **No Internet Required**: System funktioniert komplett offline
4. **Simple Access**: Geräte greifen über Webbrowser zu: `http://192.168.1.10:3000`

---

## Installation Options

### Option 1: Docker Desktop (Empfohlen)

**Vorteile:**
- Einfache Installation
- Isolierte Umgebung
- Einfache Updates
- Konsistentes Setup

**Schritte:**

#### 1. Docker Desktop installieren

```powershell
# Download von https://www.docker.com/products/docker-desktop/
# Installation mit Admin-Rechten
# Nach Installation: Docker Desktop starten
```

#### 2. Repository klonen

```powershell
git clone https://github.com/arcsmax/goldsmith_erp.git
cd goldsmith_erp
```

#### 3. Konfiguration

Erstelle `.env` Datei:

```env
# Database
POSTGRES_USER=goldsmith
POSTGRES_PASSWORD=your_secure_password_here
POSTGRES_DB=goldsmith
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# Backend
SECRET_KEY=generate_a_random_secret_key_here
HOST=0.0.0.0
PORT=8000
DEBUG=false

# CORS - Erlaubt Zugriff von allen Geräten im Netzwerk
BACKEND_CORS_ORIGINS=["http://localhost:3000","http://192.168.1.10:3000"]

# Optional: Object Storage (MinIO)
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
```

#### 4. System starten

```powershell
docker-compose up -d
```

#### 5. Datenbank initialisieren

```powershell
# Migration ausführen
docker-compose exec backend alembic upgrade head

# Seed-Daten einfügen (optional)
docker-compose exec backend python scripts/seed_data.py
```

#### 6. Server-IP ermitteln

```powershell
ipconfig

# Suche nach "IPv4-Adresse" des aktiven Netzwerkadapters
# Beispiel: 192.168.1.10
```

#### 7. Firewall-Regel erstellen

```powershell
# PowerShell als Administrator:
New-NetFirewallRule -DisplayName "Goldsmith ERP" -Direction Inbound -Protocol TCP -LocalPort 3000,8000 -Action Allow
```

#### 8. Zugriff testen

Von einem anderen Gerät im Netzwerk:
- Browser öffnen: `http://192.168.1.10:3000`
- Login: `admin@goldsmith.local` / `admin123`

---

### Option 2: Windows Installer (Geplant für v1.0)

**Vorteile:**
- Kein Docker nötig
- Ein-Klick-Installation
- Automatischer Windows-Service
- Einfacher für nicht-technische Nutzer

**Features:**
- Installer (.msi oder .exe)
- Automatische Firewall-Konfiguration
- System Tray Icon
- Automatischer Start mit Windows
- Update-Mechanismus

**Status**: Geplant für Phase 1, Week 7-8

---

## Network Configuration

### Static IP empfohlen

Damit die Server-Adresse stabil bleibt:

```powershell
# Windows Netzwerkeinstellungen:
# 1. Systemsteuerung → Netzwerk → Adaptereinstellungen
# 2. Rechtsklick auf Netzwerkadapter → Eigenschaften
# 3. IPv4 → Eigenschaften
# 4. "Folgende IP-Adresse verwenden":
#    IP-Adresse: 192.168.1.10
#    Subnetzmaske: 255.255.255.0
#    Standardgateway: 192.168.1.1
#    DNS: 192.168.1.1 (Router) oder 8.8.8.8 (Google)
```

### Router-Konfiguration (Optional)

Falls DHCP bevorzugt wird, im Router eine DHCP-Reservierung einrichten:
- MAC-Adresse des Server-PCs ermitteln
- Im Router: DHCP-Reservierung für diese MAC → immer gleiche IP

### DNS-Name (Erweitert, Optional)

Für benutzerfreundlichere URLs:

```powershell
# Im Router: lokaler DNS-Eintrag
goldsmith.local → 192.168.1.10

# Dann Zugriff über:
http://goldsmith.local:3000
```

---

## Client Access

### Web-Browser (Alle Geräte)

**Unterstützte Browser:**
- Chrome/Edge (empfohlen)
- Firefox
- Safari (iOS/macOS)

**URL:**
- Direkte IP: `http://192.168.1.10:3000`
- Mit DNS: `http://goldsmith.local:3000`

**Als App-Icon hinzufügen (Mobile):**

**Android:**
1. Browser öffnen → URL eingeben
2. Menü (⋮) → "Zum Startbildschirm hinzufügen"
3. Icon erscheint wie native App

**iOS:**
1. Safari → URL eingeben
2. Teilen-Button → "Zum Home-Bildschirm"
3. Icon erscheint wie native App

### Mobile Apps (Phase 4)

**React Native Apps mit NFC:**
- Android: APK direkt installieren
- iOS: TestFlight oder Enterprise Distribution

---

## Security Considerations

### Network Security

1. **Firewall:**
   - Nur Ports 3000 (Frontend) und 8000 (Backend) öffnen
   - Nur für lokales Netzwerk (192.168.x.x)

2. **No External Access:**
   - **NICHT** Port-Forwarding im Router einrichten
   - System ist NUR lokal erreichbar
   - Keine Cloud-Verbindung nötig

3. **Authentication:**
   - JWT-basierte Authentifizierung
   - Passwörter mit bcrypt gehasht
   - Session-Timeout nach Inaktivität

4. **HTTPS (Optional, Erweitert):**
   - Selbstsigniertes Zertifikat für `https://192.168.1.10`
   - Verhindert Mitlesen im lokalen Netzwerk

### User Management

**Rollen:**
- **admin**: Volle Rechte, Benutzerverwaltung
- **goldsmith**: Aufträge bearbeiten, Material entnehmen
- **receptionist**: Aufträge anlegen, Kunden verwalten
- **quality_manager**: Qualitätsprüfung

**Best Practices:**
- Jeder Mitarbeiter eigenen Account
- Starke Passwörter (mind. 8 Zeichen)
- Regelmäßige Passwort-Änderung
- Inaktive Accounts deaktivieren

---

## Backup Strategy

### Automated Backups

**Database Backup (täglich):**

```powershell
# PowerShell-Skript: backup_database.ps1

$BACKUP_DIR = "C:\Goldsmith_Backups"
$DATE = Get-Date -Format "yyyy-MM-dd_HH-mm"
$BACKUP_FILE = "$BACKUP_DIR\goldsmith_$DATE.sql"

# Backup erstellen
docker-compose exec -T db pg_dump -U goldsmith goldsmith > $BACKUP_FILE

# Alte Backups löschen (älter als 30 Tage)
Get-ChildItem $BACKUP_DIR -Filter "*.sql" | Where-Object {
    $_.LastWriteTime -lt (Get-Date).AddDays(-30)
} | Remove-Item

Write-Host "Backup erstellt: $BACKUP_FILE"
```

**Windows Task Scheduler:**

```powershell
# Task erstellen, der täglich um 2 Uhr nachts läuft
$action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-File C:\goldsmith_erp\scripts\backup_database.ps1"
$trigger = New-ScheduledTaskTrigger -Daily -At 2am
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
Register-ScheduledTask -TaskName "Goldsmith_Daily_Backup" -Action $action -Trigger $trigger -Principal $principal
```

### Manual Backup

```powershell
# Gesamtes System-Backup (einschließlich Docker-Volumes)
docker-compose down
Copy-Item -Recurse -Path "C:\ProgramData\Docker\volumes" -Destination "E:\Backup\Docker_Goldsmith_2025-01-15"
docker-compose up -d
```

### Restore

```powershell
# Database-Restore
cat C:\Goldsmith_Backups\goldsmith_2025-01-15.sql | docker-compose exec -T db psql -U goldsmith -d goldsmith
```

---

## Monitoring & Maintenance

### Health Checks

**Status prüfen:**

```powershell
# Container-Status
docker-compose ps

# Logs ansehen
docker-compose logs -f backend
docker-compose logs -f db

# Disk Space
docker system df
```

### Updates

**System-Update:**

```powershell
# 1. Backup erstellen (siehe oben)

# 2. Neueste Version holen
git pull origin main

# 3. Container neu bauen
docker-compose down
docker-compose build
docker-compose up -d

# 4. Datenbank-Migration
docker-compose exec backend alembic upgrade head

# 5. Testen
# Browser: http://192.168.1.10:3000
```

### Performance Optimization

**Disk Space Cleanup:**

```powershell
# Docker aufräumen
docker system prune -a
docker volume prune
```

**Database Maintenance:**

```powershell
# Vacuum & Analyze (Performance)
docker-compose exec db psql -U goldsmith -d goldsmith -c "VACUUM ANALYZE;"
```

---

## Troubleshooting

### Problem: Geräte können nicht auf Server zugreifen

**Lösung 1: Firewall-Regel prüfen**

```powershell
# Bestehende Regeln anzeigen
Get-NetFirewallRule | Where-Object { $_.DisplayName -like "*Goldsmith*" }

# Falls nicht vorhanden, erstellen (siehe oben)
```

**Lösung 2: Server-IP prüfen**

```powershell
ipconfig
# IP muss mit URL übereinstimmen
```

**Lösung 3: Container-Status**

```powershell
docker-compose ps
# Alle Container müssen "Up" sein
```

### Problem: Datenbank startet nicht

```powershell
# Logs prüfen
docker-compose logs db

# Häufigste Ursachen:
# - Port 5432 belegt: Andere PostgreSQL-Installation?
# - Disk Space voll: Platz schaffen
# - Korrupte Daten: Restore von Backup
```

### Problem: System langsam

**Ursachen:**
1. **Zu viele Container**: `docker stats` prüfen
2. **Disk Space**: `docker system df`
3. **RAM**: Task-Manager öffnen, Docker-Prozesse prüfen

**Lösungen:**
- Docker mehr RAM zuweisen (Docker Desktop Settings)
- Alte Images löschen: `docker image prune -a`
- Server-PC Upgrade (mehr RAM empfohlen: 8GB+)

---

## Hardware Requirements

### Minimum (Kleine Werkstatt, 1-5 Benutzer)

- **CPU**: Intel Core i3 oder AMD Ryzen 3 (4 Kerne)
- **RAM**: 8 GB
- **Disk**: 128 GB SSD
- **Network**: Gigabit Ethernet oder WiFi 5
- **OS**: Windows 10/11 Pro (64-bit)

### Empfohlen (Mittlere Werkstatt, 5-15 Benutzer)

- **CPU**: Intel Core i5 oder AMD Ryzen 5 (6+ Kerne)
- **RAM**: 16 GB
- **Disk**: 256 GB NVMe SSD
- **Network**: Gigabit Ethernet (fest verdrahtet)
- **OS**: Windows 11 Pro (64-bit)

### High-End (Große Werkstatt, 15+ Benutzer)

- **CPU**: Intel Core i7/i9 oder AMD Ryzen 7/9
- **RAM**: 32 GB
- **Disk**: 512 GB NVMe SSD (+ 1TB HDD für Backups)
- **Network**: 2.5G Ethernet
- **OS**: Windows Server 2019/2022

---

## Scalability

### Wann Cloud/Dedizierter Server?

**Überlegen Sie einen Cloud/Dedicated Server, wenn:**
- Mehr als 20 gleichzeitige Benutzer
- Mehrere Standorte (z.B. Hauptwerkstatt + Filiale)
- Zugriff von unterwegs benötigt
- 24/7 Verfügbarkeit erforderlich

**Dann:**
- Siehe `DEPLOYMENT_CLOUD.md` (geplant)
- Kubernetes-Deployment empfohlen
- Managed Database (PostgreSQL as a Service)

---

## FAQ

**Q: Kann ich das auf einem normalen Windows-Laptop betreiben?**
A: Ja, solange er immer eingeschaltet und im Netzwerk bleibt. Ein Desktop-PC ist aber stabiler.

**Q: Funktioniert es auch mit WiFi?**
A: Ja, aber Ethernet ist stabiler und schneller. Server-PC sollte per Kabel verbunden sein.

**Q: Können mobile Geräte auch offline arbeiten?**
A: In Phase 4 (Mobile Apps) ja, mit lokalem Sync. Web-Version benötigt immer Netzwerkverbindung zum Server.

**Q: Was passiert bei Stromausfall?**
A: Nach Neustart von Windows startet Docker Desktop automatisch und die Container laufen weiter. Daten sind sicher (PostgreSQL ist transaktional).

**Q: Kann ich von zuhause zugreifen?**
A: Nicht standardmäßig (Sicherheitsgründe). Erweiterte Lösung: VPN zum Werkstatt-Netzwerk.

**Q: Wie viel Traffic erzeugt das System?**
A: Minimal. Typische Order-Erstellung: ~100KB. Bilder: ~2-5MB. Streaming: WebSocket ~10KB/s bei aktiver Nutzung.

---

**Document Version**: 1.0
**Last Updated**: 2025-01-15
**Status**: Complete

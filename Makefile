# Makefile for Goldsmith ERP with Podman
# Makes development easier with simple commands

.PHONY: help install start stop restart logs clean build test test-integration-pg lint format seed-demo validate-compose

# Default target
.DEFAULT_GOAL := help

# Podman compose file
COMPOSE_FILE := podman-compose.yml
COMPOSE := podman-compose -f $(COMPOSE_FILE)

# Colors for output
GREEN := \033[0;32m
YELLOW := \033[1;33m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(GREEN)Goldsmith ERP - Podman Commands$(NC)"
	@echo ""
	@echo "$(YELLOW)Available targets:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""

install: ## Install Podman and setup environment
	@echo "$(GREEN)Installing Podman...$(NC)"
	@./setup-podman.sh

start: ## Start all services
	@echo "$(GREEN)Starting Goldsmith ERP...$(NC)"
	@$(COMPOSE) up -d
	@echo "$(GREEN)✓ Services started$(NC)"
	@echo "Backend: http://localhost:8000"
	@echo "Frontend: http://localhost:3000"
	@echo "API Docs: http://localhost:8000/docs"

stop: ## Stop all services
	@echo "$(YELLOW)Stopping services...$(NC)"
	@$(COMPOSE) down
	@echo "$(GREEN)✓ Services stopped$(NC)"

restart: ## Restart all services
	@echo "$(YELLOW)Restarting services...$(NC)"
	@$(COMPOSE) restart
	@echo "$(GREEN)✓ Services restarted$(NC)"

logs: ## Show logs (use 'make logs-backend' or 'make logs-frontend' for specific service)
	@$(COMPOSE) logs -f

logs-backend: ## Show backend logs only
	@$(COMPOSE) logs -f backend

logs-frontend: ## Show frontend logs only
	@$(COMPOSE) logs -f frontend

logs-db: ## Show database logs only
	@$(COMPOSE) logs -f db

ps: ## Show running containers
	@$(COMPOSE) ps

build: ## Build all containers
	@echo "$(GREEN)Building containers...$(NC)"
	@$(COMPOSE) build --no-cache
	@echo "$(GREEN)✓ Build complete$(NC)"

build-backend: ## Build backend container only
	@echo "$(GREEN)Building backend...$(NC)"
	@$(COMPOSE) build --no-cache backend

build-frontend: ## Build frontend container only
	@echo "$(GREEN)Building frontend...$(NC)"
	@$(COMPOSE) build --no-cache frontend

clean: ## Remove all containers, volumes, and images
	@echo "$(YELLOW)⚠️  This will remove all containers, volumes, and images!$(NC)"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		$(COMPOSE) down -v; \
		podman system prune -af --volumes; \
		echo "$(GREEN)✓ Cleanup complete$(NC)"; \
	else \
		echo "$(YELLOW)Cleanup cancelled$(NC)"; \
	fi

shell-backend: ## Open shell in backend container
	@$(COMPOSE) exec backend /bin/bash

shell-db: ## Open PostgreSQL shell
	@$(COMPOSE) exec db psql -U user -d goldsmith

shell-redis: ## Open Redis CLI
	@$(COMPOSE) exec redis redis-cli

# Development commands
dev-backend: ## Run backend in development mode (outside container)
	@echo "$(GREEN)Starting backend in dev mode...$(NC)"
	@cd src && poetry run uvicorn goldsmith_erp.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend: ## Run frontend in development mode (outside container)
	@echo "$(GREEN)Starting frontend in dev mode...$(NC)"
	@cd frontend && yarn dev

migrate: ## Run database migrations
	@echo "$(GREEN)Running migrations...$(NC)"
	@$(COMPOSE) exec backend poetry run alembic upgrade head
	@echo "$(GREEN)✓ Migrations complete$(NC)"

migrate-create: ## Create new migration (usage: make migrate-create MESSAGE="your message")
	@echo "$(GREEN)Creating migration: $(MESSAGE)$(NC)"
	@$(COMPOSE) exec backend poetry run alembic revision --autogenerate -m "$(MESSAGE)"

seed: ## Seed database with sample data
	@echo "$(GREEN)Seeding database...$(NC)"
	@$(COMPOSE) exec backend python -m goldsmith_erp.db.seed_data
	@echo "$(GREEN)✓ Database seeded$(NC)"

seed-demo: ## Load demo data for showcasing all features
	@echo "$(GREEN)Loading comprehensive demo data...$(NC)"
	@cd src && poetry run python ../scripts/seed_demo.py
	@echo "$(GREEN)✓ Demo data loaded$(NC)"

# Testing
test: ## Run tests
	@echo "$(GREEN)Running tests...$(NC)"
	@$(COMPOSE) exec backend poetry run pytest -v

test-cov: ## Run tests with coverage
	@echo "$(GREEN)Running tests with coverage...$(NC)"
	@$(COMPOSE) exec backend poetry run pytest --cov=goldsmith_erp --cov-report=html

test-integration-pg: ## F1 — run integration tests against real Postgres (not SQLite)
	@echo "$(GREEN)Starting db + redis services...$(NC)"
	@$(COMPOSE) up -d db redis
	@echo "$(GREEN)Running integration tests against Postgres...$(NC)"
	@cd src && \
	  TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/goldsmith_test \
	  DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/goldsmith_test \
	  REDIS_URL=redis://localhost:6379/0 \
	  SECRET_KEY=local-test-secret-key-minimum-32-characters-long-enough \
	  ENCRYPTION_KEY=dGVzdGtleTEyMzQ1Njc4OTBhYmNkZWZnaGlqa2w= \
	  ANONYMIZATION_SALT=testsalt1234567890abcdef \
	  DEBUG=true \
	  poetry run pytest ../tests/integration/ -v --tb=short

# Linting and formatting
lint: ## Run linters (pylint, mypy, black check)
	@echo "$(GREEN)Running linters...$(NC)"
	@$(COMPOSE) exec backend poetry run black --check src/
	@$(COMPOSE) exec backend poetry run isort --check src/
	@$(COMPOSE) exec backend poetry run pylint src/
	@$(COMPOSE) exec backend poetry run mypy src/

format: ## Format code with black and isort
	@echo "$(GREEN)Formatting code...$(NC)"
	@$(COMPOSE) exec backend poetry run black src/
	@$(COMPOSE) exec backend poetry run isort src/
	@echo "$(GREEN)✓ Code formatted$(NC)"

security: ## Run security scan with bandit
	@echo "$(GREEN)Running security scan...$(NC)"
	@$(COMPOSE) exec backend poetry run bandit -r src/

validate-compose: ## A4 fix — verify compose files require POSTGRES_PASSWORD and bind DB to 127.0.0.1
	@echo "$(GREEN)Validating compose files (A4)...$(NC)"
	@bash scripts/test-compose-validation.sh

check-bundle: ## V1.1 Slice 13 — scanner-route bundle-size gate (<=250 KB gzip)
	@echo "$(GREEN)Building frontend and running scanner bundle gate...$(NC)"
	@cd frontend && yarn build
	@node frontend/scripts/check-scanner-bundle.mjs

# Pod operations (alternative to compose)
pod-create: ## Create Kubernetes-style pod
	@echo "$(GREEN)Creating pod from manifest...$(NC)"
	@podman play kube podman-pod.yaml
	@echo "$(GREEN)✓ Pod created$(NC)"

pod-destroy: ## Destroy pod
	@echo "$(YELLOW)Destroying pod...$(NC)"
	@podman play kube --down podman-pod.yaml
	@echo "$(GREEN)✓ Pod destroyed$(NC)"

# Utility commands
health: ## Check health of all services
	@echo "$(GREEN)Checking service health...$(NC)"
	@curl -f http://localhost:8000/health || echo "$(YELLOW)Backend: unhealthy$(NC)"
	@curl -f http://localhost:3000 || echo "$(YELLOW)Frontend: unhealthy$(NC)"
	@$(COMPOSE) exec db pg_isready -U user || echo "$(YELLOW)Database: unhealthy$(NC)"
	@$(COMPOSE) exec redis redis-cli ping || echo "$(YELLOW)Redis: unhealthy$(NC)"

backup-db: ## Backup database to ./backups/
	@echo "$(GREEN)Creating database backup...$(NC)"
	@mkdir -p backups
	@$(COMPOSE) exec -T db pg_dump -U user goldsmith > backups/goldsmith_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "$(GREEN)✓ Backup created in ./backups/$(NC)"

restore-db: ## Restore database from backup (usage: make restore-db FILE=backup.sql)
	@echo "$(YELLOW)Restoring database from $(FILE)...$(NC)"
	@$(COMPOSE) exec -T db psql -U user goldsmith < $(FILE)
	@echo "$(GREEN)✓ Database restored$(NC)"

# Docker compatibility aliases (for migration)
docker-start: start ## Alias for 'start' (Docker compatibility)
docker-stop: stop ## Alias for 'stop' (Docker compatibility)
docker-compose-up: start ## Alias for 'start' (Docker compatibility)
docker-compose-down: stop ## Alias for 'stop' (Docker compatibility)

# =============================================================================
# Production targets (podman-compose.prod.yml)
# =============================================================================

.PHONY: setup prod-start prod-stop prod-restart prod-logs prod-status \
        update backup-now restore install-service install-backup-cron rotate-secrets

PROD_COMPOSE := podman-compose --env-file .env.production -f podman-compose.prod.yml

setup: ## First-time production setup (interactive, idempotent)
	@echo "$(GREEN)Goldsmith ERP – Ersteinrichtung startet…$(NC)"
	@chmod +x setup.sh
	@./setup.sh

prod-start: ## Start all production services
	@echo "$(GREEN)Produktionsdienste starten…$(NC)"
	@$(PROD_COMPOSE) up -d
	@echo "$(GREEN)✓ Produktionsdienste gestartet$(NC)"

prod-stop: ## Stop all production services
	@echo "$(YELLOW)Produktionsdienste stoppen…$(NC)"
	@$(PROD_COMPOSE) down
	@echo "$(GREEN)✓ Produktionsdienste gestoppt$(NC)"

prod-restart: ## Restart all production services
	@echo "$(YELLOW)Produktionsdienste neustarten…$(NC)"
	@$(PROD_COMPOSE) restart
	@echo "$(GREEN)✓ Produktionsdienste neugestartet$(NC)"

prod-logs: ## Follow production logs (all services)
	@$(PROD_COMPOSE) logs -f

prod-status: ## Show production container status and health
	@echo "$(GREEN)Produktionsstatus:$(NC)"
	@$(PROD_COMPOSE) ps
	@echo ""
	@echo "$(YELLOW)Health-Checks:$(NC)"
	@curl -sf http://localhost:8000/health && echo "$(GREEN)Backend: OK$(NC)" || echo "$(YELLOW)Backend: nicht erreichbar$(NC)"
	@$(PROD_COMPOSE) exec -T db pg_isready -U $${POSTGRES_USER:-goldsmith} \
		&& echo "$(GREEN)Datenbank: OK$(NC)" || echo "$(YELLOW)Datenbank: nicht erreichbar$(NC)"
	@$(PROD_COMPOSE) exec -T redis redis-cli ping \
		&& echo "$(GREEN)Redis: OK$(NC)" || echo "$(YELLOW)Redis: nicht erreichbar$(NC)"

update: ## Pull latest images, rebuild, and restart production services
	@echo "$(GREEN)Update: Container neu bauen und starten…$(NC)"
	@$(PROD_COMPOSE) build --no-cache
	@$(PROD_COMPOSE) up -d --remove-orphans
	@$(PROD_COMPOSE) exec -T backend poetry run alembic upgrade head
	@echo "$(GREEN)✓ Update abgeschlossen$(NC)"

backup-now: ## Create a compressed, verified database backup via scripts/backup.sh
	@bash scripts/backup.sh

restore: ## Restore database from backup (usage: make restore FILE=path/to/backup.sql)
	@if [ -z "$(FILE)" ]; then \
		echo "$(YELLOW)Verwendung: make restore FILE=pfad/zum/backup.sql$(NC)"; \
		exit 1; \
	fi
	@echo "$(YELLOW)Datenbank wiederherstellen aus: $(FILE)$(NC)"
	@read -p "Sicher? Alle aktuellen Daten werden überschrieben. [j/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Jj]$$ ]]; then \
		$(PROD_COMPOSE) exec -T db psql \
			-U $${POSTGRES_USER:-goldsmith} $${POSTGRES_DB:-goldsmith} < $(FILE); \
		echo "$(GREEN)✓ Wiederherstellung abgeschlossen$(NC)"; \
	else \
		echo "$(YELLOW)Wiederherstellung abgebrochen$(NC)"; \
	fi

install-service: ## Install Goldsmith ERP as a systemd user service (auto-start on boot)
	@echo "$(GREEN)Systemd-Dienst installieren…$(NC)"
	@mkdir -p ~/.config/systemd/user
	@if ! podman generate systemd --name goldsmith-backend-prod --files --new 2>/dev/null; then \
		echo "Fallback: Einfache Unit-Datei wird aus Template erstellt…"; \
		sed 's|@PWD@|$(PWD)|g' scripts/goldsmith-erp.service.template \
			> ~/.config/systemd/user/goldsmith-erp.service; \
	fi
	@systemctl --user daemon-reload
	@systemctl --user enable goldsmith-erp.service
	@echo "$(GREEN)✓ Systemd-Dienst installiert und aktiviert$(NC)"
	@echo "  Starten mit: systemctl --user start goldsmith-erp"

install-backup-cron: ## Install daily 02:00 backup cron job
	@echo "$(GREEN)Backup-Cronjob einrichten (täglich 02:00)…$(NC)"
	@(crontab -l 2>/dev/null | grep -v 'goldsmith.*backup'; \
	echo "0 2 * * * cd $(PWD) && bash scripts/backup.sh >> $(PWD)/logs/backup.log 2>&1") | crontab -
	@echo "$(GREEN)✓ Backup-Cronjob installiert (täglich 02:00)$(NC)"
	@echo "  Prüfen mit: crontab -l"

rotate-secrets: ## Rotate SECRET_KEY in .env.production via scripts/rotate-secrets.sh (requires restart)
	@bash scripts/rotate-secrets.sh

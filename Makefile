# Makefile for Goldsmith ERP with Podman
# Makes development easier with simple commands

.PHONY: help install start stop restart logs clean build test lint format

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

# Testing
test: ## Run tests
	@echo "$(GREEN)Running tests...$(NC)"
	@$(COMPOSE) exec backend poetry run pytest -v

test-cov: ## Run tests with coverage
	@echo "$(GREEN)Running tests with coverage...$(NC)"
	@$(COMPOSE) exec backend poetry run pytest --cov=goldsmith_erp --cov-report=html

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

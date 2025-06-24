.PHONY: up down stop logs build ps sh-backend sh-frontend install backend-run frontend-run venv-backend install-backend install-frontend

# ==============================================================================
# Docker
# ==============================================================================
up: ## Start services in detached mode
	COMPOSE_BAKE=true docker compose up -d --build

down: ## Stop and remove containers, networks, and volumes
	docker compose down

stop: ## Stop services
	docker compose stop

logs: ## Follow service logs
	docker compose logs -f

build: ## Build or rebuild services
	docker compose build

ps: ## List containers
	docker compose ps

sh-backend: ## Get a shell into the backend container
	docker compose exec backend bash

sh-frontend: ## Get a shell into the frontend container
	docker compose exec frontend sh


# ==============================================================================
# Local Development
# ==============================================================================
install: install-backend install-frontend ## Install all dependencies

backend-run: ## Run backend dev server
	@cd backend && uv run fastapi dev app/main.py

frontend-run: ## Run frontend dev server
	pnpm --filter frontend dev


# ==============================================================================
# Python Environment (uv)
# ==============================================================================
venv-backend: ## Create virtual environment in backend/
	@echo "Creating virtual environment in backend/.venv..."
	@cd backend && uv venv

install-backend: venv-backend ## Install backend dependencies
	@echo "Installing backend dependencies from backend/pyproject.toml..."
	@cd backend && uv pip install -e .


# ==============================================================================
# Frontend Environment (pnpm)
# ==============================================================================
install-frontend: ## Install frontend dependencies
	@echo "Installing frontend dependencies from frontend/package.json..."
	@cd frontend && pnpm install
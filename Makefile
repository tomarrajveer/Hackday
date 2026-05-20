IMAGE_NAME  := cricbuzz-api
IMAGE_TAG   := latest
PORT        := 8000
PF_PID_FILE := .port-forward.pid
PF_LOG      := /tmp/cricbuzz-pf.log

# Ensure macOS+Rancher and Apple Silicon brew binaries are findable when
# `make` is launched from a non-login shell or IDE. Harmless on Linux.
export PATH := $(HOME)/.rd/bin:/opt/homebrew/bin:/usr/local/bin:$(PATH)

.PHONY: help up down restart logs status test smoke clean

help:
	@echo "Targets:"
	@echo "  make up      Start minikube, build image, apply manifests, port-forward"
	@echo "  make down    Stop port-forward and tear down k8s resources"
	@echo "  make restart down + up"
	@echo "  make logs    Tail API pod logs"
	@echo "  make status  Show pods/services/deployments"
	@echo "  make test    Run pytest suite (offline, in-memory SQLite)"
	@echo "  make smoke   Curl /health against a running deployment"
	@echo "  make clean   make down + minikube delete"

up:
	@command -v minikube >/dev/null 2>&1 || { echo "ERROR: minikube not installed"; exit 1; }
	@command -v kubectl  >/dev/null 2>&1 || { echo "ERROR: kubectl not installed";  exit 1; }
	@command -v docker   >/dev/null 2>&1 || { echo "ERROR: docker not installed";   exit 1; }
	@echo "==> Starting Minikube..."
	@minikube status 2>/dev/null | grep -q "host: Running" || minikube start --driver=docker
	@echo "==> Building Docker image inside Minikube..."
	@eval "$$(minikube docker-env)" && docker build -t $(IMAGE_NAME):$(IMAGE_TAG) .
	@echo "==> Applying Kubernetes manifests..."
	@kubectl apply -f k8s/postgres-configmap.yaml
	@kubectl apply -f k8s/postgres-secret.yaml
	@kubectl apply -f k8s/postgres-headless-service.yaml
	@kubectl apply -f k8s/postgres-service.yaml
	@kubectl apply -f k8s/postgres-statefulset.yaml
	@kubectl apply -f k8s/api-service.yaml
	@kubectl apply -f k8s/api-deployment.yaml
	@echo "==> Waiting for PostgreSQL..."
	@kubectl rollout status statefulset/postgres --timeout=180s
	@echo "==> Waiting for API..."
	@kubectl rollout restart deployment/cricbuzz-api >/dev/null
	@kubectl rollout status  deployment/cricbuzz-api --timeout=180s
	@echo "==> Starting port-forward in background..."
	@if [ -f $(PF_PID_FILE) ] && kill -0 $$(cat $(PF_PID_FILE)) 2>/dev/null; then \
	  kill $$(cat $(PF_PID_FILE)) 2>/dev/null || true; rm -f $(PF_PID_FILE); \
	fi
	@nohup kubectl port-forward svc/cricbuzz-api-service $(PORT):80 >$(PF_LOG) 2>&1 & echo $$! > $(PF_PID_FILE)
	@echo "==> Waiting for app to respond..."
	@for i in $$(seq 1 20); do \
	  if curl -sf http://localhost:$(PORT)/health >/dev/null 2>&1; then break; fi; \
	  sleep 1; \
	done
	@curl -sf http://localhost:$(PORT)/health >/dev/null || { \
	  echo "✗ App did not become reachable. Check $(PF_LOG) and 'make logs'."; exit 1; \
	}
	@echo ""
	@echo "✓ App is reachable at: http://localhost:$(PORT)"
	@echo "  Swagger UI:           http://localhost:$(PORT)/docs"
	@echo "  Health check:         http://localhost:$(PORT)/health"
	@echo ""
	@echo "Stop with: make down"

down:
	@if [ -f $(PF_PID_FILE) ]; then \
	  kill $$(cat $(PF_PID_FILE)) 2>/dev/null || true; \
	  rm -f $(PF_PID_FILE); \
	  echo "==> Port-forward stopped."; \
	fi
	@kubectl delete -f k8s/api-deployment.yaml         --ignore-not-found
	@kubectl delete -f k8s/api-service.yaml            --ignore-not-found
	@kubectl delete -f k8s/postgres-statefulset.yaml   --ignore-not-found
	@kubectl delete -f k8s/postgres-service.yaml       --ignore-not-found
	@kubectl delete -f k8s/postgres-headless-service.yaml --ignore-not-found
	@kubectl delete -f k8s/postgres-secret.yaml        --ignore-not-found
	@kubectl delete -f k8s/postgres-configmap.yaml     --ignore-not-found

restart: down up

logs:
	@kubectl logs -l app=cricbuzz-api --tail=200 -f

status:
	@kubectl get pods,svc,statefulset,deployment -o wide

test:
	@if [ ! -d .venv ]; then \
	  echo "==> Creating .venv..."; \
	  python3 -m venv .venv; \
	  .venv/bin/pip install --quiet --upgrade pip; \
	  .venv/bin/pip install --quiet -r requirements-dev.txt; \
	fi
	@SECRET_KEY=test-secret .venv/bin/pytest -q tests/

smoke:
	@curl -sf http://localhost:$(PORT)/health && echo "" && echo "✓ /health OK" \
	  || { echo "✗ /health failed — is 'make up' running?"; exit 1; }

clean: down
	@minikube delete

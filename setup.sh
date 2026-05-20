#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="cricbuzz-api"
IMAGE_TAG="latest"

# ── Prerequisites ──────────────────────────────────────────────────────────────
check_cmd() {
  if ! command -v "$1" &>/dev/null; then
    echo "ERROR: '$1' is not installed or not in PATH. Please install it first."
    exit 1
  fi
}

check_cmd docker
check_cmd minikube
check_cmd kubectl

# ── Minikube ───────────────────────────────────────────────────────────────────
echo "==> Starting Minikube..."
if ! minikube status | grep -q "Running"; then
  minikube start --driver=docker
fi

# ── Docker image inside Minikube ───────────────────────────────────────────────
echo "==> Building Docker image inside Minikube..."
eval "$(minikube docker-env)"
docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" .

# ── Deploy to Kubernetes ───────────────────────────────────────────────────────
echo "==> Applying Kubernetes manifests..."
kubectl apply -f k8s/postgres-configmap.yaml
kubectl apply -f k8s/postgres-secret.yaml
kubectl apply -f k8s/postgres-headless-service.yaml
kubectl apply -f k8s/postgres-service.yaml
kubectl apply -f k8s/postgres-statefulset.yaml
kubectl apply -f k8s/api-service.yaml
kubectl apply -f k8s/api-deployment.yaml

# ── Wait for rollout ───────────────────────────────────────────────────────────
echo "==> Waiting for PostgreSQL to be ready..."
kubectl rollout status statefulset/postgres --timeout=120s

echo "==> Waiting for API deployment to be ready..."
kubectl rollout status deployment/cricbuzz-api --timeout=120s

# ── Print access URL ───────────────────────────────────────────────────────────
API_URL=$(minikube service cricbuzz-api-service --url 2>/dev/null || true)
if [ -n "$API_URL" ]; then
  echo ""
  echo "✓ App is reachable at: ${API_URL}"
  echo "  Swagger UI:           ${API_URL}/docs"
  echo "  Health check:         ${API_URL}/health"
else
  NODE_IP=$(minikube ip)
  echo ""
  echo "✓ App is reachable at: http://${NODE_IP}:30080"
  echo "  Swagger UI:           http://${NODE_IP}:30080/docs"
  echo "  Health check:         http://${NODE_IP}:30080/health"
fi

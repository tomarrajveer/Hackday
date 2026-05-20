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

# ── Print access instructions ──────────────────────────────────────────────────
NODE_IP=$(minikube ip)
echo ""
echo "✓ Deployment complete."
echo ""
echo "To access the API, pick one:"
echo ""
echo "  # 1) Open a tunnel (recommended on macOS — leave it running):"
echo "     minikube service cricbuzz-api-service --url"
echo ""
echo "  # 2) Direct NodePort (works on Linux; not reachable from macOS Docker driver):"
echo "     http://${NODE_IP}:30080"
echo ""
echo "  # 3) kubectl port-forward (alternative — leave it running):"
echo "     kubectl port-forward svc/cricbuzz-api-service 8000:80"
echo ""
echo "Useful endpoints once a URL is available:"
echo "  /health          health check"
echo "  /docs            Swagger UI"
echo "  /openapi.json    OpenAPI schema"

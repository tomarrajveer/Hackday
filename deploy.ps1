<#
.SYNOPSIS
Deploy CricBuzz API locally on Minikube

.DESCRIPTION
This script will check if required tools are installed, attempt to install them via winget if not, 
start Minikube, build the Docker image in the Minikube environment, and deploy all Kubernetes manifests.
#>

$ErrorActionPreference = "Stop"

Function Check-Command {
    param ($Command)
    try {
        $null = Get-Command $Command -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

Write-Host "Checking for winget..." -ForegroundColor Cyan
if (-Not (Check-Command "winget")) {
    Write-Host "winget is not installed. Please install it from the Microsoft Store." -ForegroundColor Red
    exit 1
}

Write-Host "Checking for Docker..." -ForegroundColor Cyan
if (-Not (Check-Command "docker")) {
    Write-Host "Docker is not installed. Installing via winget..." -ForegroundColor Yellow
    winget install --id Docker.DockerDesktop -e --accept-package-agreements --accept-source-agreements
    Write-Host "Docker Desktop has been installed. Please start Docker Desktop, accept the terms, wait for the engine to start, and run this script again." -ForegroundColor Red
    exit 0
}

Write-Host "Checking for Minikube..." -ForegroundColor Cyan
if (-Not (Check-Command "minikube")) {
    Write-Host "Minikube is not installed. Installing via winget..." -ForegroundColor Yellow
    winget install --id Kubernetes.minikube -e --accept-package-agreements --accept-source-agreements
    # Refresh PATH to ensure minikube command is available
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

Write-Host "Checking for Kubectl..." -ForegroundColor Cyan
if (-Not (Check-Command "kubectl")) {
    Write-Host "Kubectl is not installed. Installing via winget..." -ForegroundColor Yellow
    winget install --id Kubernetes.kubectl -e --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

Write-Host "Starting Minikube..." -ForegroundColor Cyan
minikube start --driver=docker

Write-Host "Setting Docker environment to Minikube..." -ForegroundColor Cyan
& minikube -p minikube docker-env --shell powershell | Invoke-Expression

Write-Host "Building Docker Image..." -ForegroundColor Cyan
docker build -t cricbuzz-api:latest .

Write-Host "Applying Kubernetes manifests..." -ForegroundColor Cyan
kubectl apply -f k8s/

Write-Host "Waiting for deployments to roll out..." -ForegroundColor Cyan
kubectl rollout status deployment/cricbuzz-api -w

Write-Host "Deployment completed successfully!" -ForegroundColor Green
Write-Host "To access the API, you can use the Minikube IP and NodePort or run the following command to get the service URL:" -ForegroundColor Yellow
Write-Host "minikube service cricbuzz-api-service --url" -ForegroundColor Yellow

$url = minikube service cricbuzz-api-service --url
Write-Host "API URL: $url" -ForegroundColor Green
Write-Host "Swagger UI: $url/docs" -ForegroundColor Green

.PHONY: help startgcvpn stopgcvpn status pods logs cost test-e2e test-e2e-flows test-e2e-overlay test-e2e-smoke test-e2e-setup test-e2e-install

# GKE Configuration
PROJECT := hocuspocus-vpn
ZONE := europe-west1-b
CLUSTER := hocuspocus-vpn
NODE_POOL := vpn-pool
NAMESPACE := hocuspocus

help:
	@echo "Hocuspocus VPN - Google Kubernetes Engine"
	@echo ""
	@echo "Daily Usage:"
	@echo "  make startgcvpn    - Start VPN (scale up nodes + deploy services)"
	@echo "  make stopgcvpn     - Stop VPN (delete LB + scale down nodes)"
	@echo "  make status        - Check current status and running costs"
	@echo ""
	@echo "Monitoring:"
	@echo "  make pods          - Show all pods"
	@echo "  make logs          - Show mitmproxy logs"
	@echo "  make logs-vpn      - Show VPN server logs"
	@echo ""
	@echo "VPN:"
	@echo "  make vpn-ip        - Get VPN LoadBalancer IP"
	@echo "  make vpn-status    - Check VPN connection status"
	@echo ""
	@echo "E2E Testing:"
	@echo "  make test-e2e         - Run all E2E tests"
	@echo "  make test-e2e-flows   - Run proxy flow tests only"
	@echo "  make test-e2e-overlay - Run location overlay tests only"
	@echo "  make test-e2e-smoke   - Run smoke tests (quick check)"
	@echo "  make test-e2e-setup   - First-time WebDriverAgent setup"
	@echo "  make test-e2e-install - Install test dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make build-push       - Build and push mitmproxy image"
	@echo "  make deploy-mitmproxy - Build, push, and restart mitmproxy"
	@echo ""
	@echo "Infrastructure:"
	@echo "  make init          - Initialize Terraform"
	@echo "  make apply         - Deploy full GKE cluster"
	@echo "  make destroy       - Tear down everything (careful!)"
	@echo ""
	@echo "Cost:"
	@echo "  make cost          - Show cost breakdown"

# ============================================================================
# Daily Start/Stop (RECOMMENDED)
# ============================================================================

startgcvpn:
	@echo "Starting VPN infrastructure..."
	@echo ""
	@echo "Step 1/3: Scaling up node pool..."
	gcloud container clusters resize $(CLUSTER) \
		--node-pool $(NODE_POOL) \
		--num-nodes 1 \
		--zone $(ZONE) \
		--project $(PROJECT) \
		--quiet
	@echo ""
	@echo "Step 2/3: Waiting for node to be ready..."
	@sleep 10
	kubectl wait --for=condition=Ready nodes --all --timeout=120s
	@echo ""
	@echo "Step 3/3: Deploying services..."
	kubectl apply -k k8s/
	@echo ""
	@echo "Waiting for pods to start..."
	@sleep 15
	kubectl get pods -n $(NAMESPACE)
	@echo ""
	@echo "VPN IP: $$(kubectl get svc vpn-service -n $(NAMESPACE) -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo 'pending...')"
	@echo ""
	@echo "VPN is starting! It may take 1-2 minutes for the Load Balancer IP."
	@echo "Run 'make vpn-ip' to check the IP."

stopgcvpn:
	@echo "Stopping VPN infrastructure..."
	@echo ""
	@echo "Step 1/2: Deleting Load Balancer service (saves ~$$0.60/day)..."
	-kubectl delete svc vpn-service -n $(NAMESPACE) 2>/dev/null || true
	@echo ""
	@echo "Step 2/2: Scaling down node pool (saves ~$$0.14/day)..."
	gcloud container clusters resize $(CLUSTER) \
		--node-pool $(NODE_POOL) \
		--num-nodes 0 \
		--zone $(ZONE) \
		--project $(PROJECT) \
		--quiet
	@echo ""
	@echo "VPN stopped. Idle cost: ~$$0.05/day (disk storage only)"
	@echo "Run 'make startgcvpn' to restart."

status:
	@echo "=== GKE Cluster Status ==="
	@echo ""
	@echo "Node Pool:"
	@gcloud container node-pools describe $(NODE_POOL) \
		--cluster $(CLUSTER) \
		--zone $(ZONE) \
		--project $(PROJECT) \
		--format="table(name,config.machineType,initialNodeCount,autoscaling.enabled)" 2>/dev/null || echo "  Unable to fetch"
	@echo ""
	@echo "Current Nodes:"
	@kubectl get nodes 2>/dev/null || echo "  No nodes running (scaled to 0)"
	@echo ""
	@echo "Pods:"
	@kubectl get pods -n $(NAMESPACE) 2>/dev/null || echo "  No pods running"
	@echo ""
	@echo "Services:"
	@kubectl get svc -n $(NAMESPACE) 2>/dev/null || echo "  No services"
	@echo ""
	@echo "=== Current Hourly Cost ==="
	@if kubectl get nodes 2>/dev/null | grep -q Ready; then \
		echo "  Node (e2-small spot): ~$$0.006/hr"; \
		if kubectl get svc vpn-service -n $(NAMESPACE) 2>/dev/null | grep -q LoadBalancer; then \
			echo "  Load Balancer:        ~$$0.025/hr"; \
			echo "  --------------------------------"; \
			echo "  TOTAL:                ~$$0.031/hr (~$$0.74/day)"; \
		else \
			echo "  Load Balancer:        $$0 (not running)"; \
			echo "  --------------------------------"; \
			echo "  TOTAL:                ~$$0.006/hr (~$$0.14/day)"; \
		fi \
	else \
		echo "  Nodes: $$0 (scaled to 0)"; \
		echo "  Load Balancer: $$0 (not running)"; \
		echo "  Disk storage: ~$$0.002/hr"; \
		echo "  --------------------------------"; \
		echo "  TOTAL: ~$$0.05/day (idle)"; \
	fi

# ============================================================================
# Monitoring
# ============================================================================

pods:
	kubectl get pods -n $(NAMESPACE) -o wide

logs:
	kubectl logs -n $(NAMESPACE) -l app=mitmproxy -f

logs-vpn:
	kubectl logs -n $(NAMESPACE) -l app.kubernetes.io/name=hocuspocus-vpn,app=vpn-server -c strongswan -f

# ============================================================================
# VPN
# ============================================================================

vpn-ip:
	@echo "VPN IP: $$(kubectl get svc vpn-service -n $(NAMESPACE) -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo 'Not available - run make start')"

vpn-status:
	kubectl exec -n $(NAMESPACE) -it $$(kubectl get pods -n $(NAMESPACE) -l app=vpn-server -o jsonpath='{.items[0].metadata.name}') -c strongswan -- ipsec statusall

vpn-creds:
	@echo ""
	@echo "=== VPN Connection Details ==="
	@echo "Server:   $$(kubectl get svc vpn-service -n $(NAMESPACE) -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo 'Not available')"
	@echo "Type:     IKEv2"
	@echo "Username: $$(kubectl get secret vpn-secrets -n $(NAMESPACE) -o jsonpath='{.data.VPN_USERNAME}' | base64 -d)"
	@echo "Password: $$(kubectl get secret vpn-secrets -n $(NAMESPACE) -o jsonpath='{.data.VPN_PASSWORD}' | base64 -d)"
	@echo ""

# ============================================================================
# Infrastructure (Terraform)
# ============================================================================

init:
	cd terraform/gke && terraform init

plan:
	cd terraform/gke && terraform plan

apply:
	cd terraform/gke && terraform apply

destroy:
	@echo "WARNING: This will delete the entire GKE cluster!"
	@read -p "Are you sure? (yes/no): " confirm && [ "$$confirm" = "yes" ] || exit 1
	cd terraform/gke && terraform destroy

kubeconfig:
	gcloud container clusters get-credentials $(CLUSTER) --zone $(ZONE) --project $(PROJECT)

# ============================================================================
# Cost Information
# ============================================================================

cost:
	@echo ""
	@echo "=== GKE VPN Cost Breakdown ==="
	@echo ""
	@echo "Running (5 hrs/day, 30 days):"
	@echo "  Node (e2-small spot):     ~$$0.90/month  ($$0.006/hr × 5hr × 30)"
	@echo "  Load Balancer:            ~$$3.75/month  ($$0.025/hr × 5hr × 30)"
	@echo "  Disk Storage (12GB):      ~$$0.50/month"
	@echo "  GKE Control Plane:        $$0 (free for 1 zonal cluster)"
	@echo "  Static IP (in use):       $$0"
	@echo "  ----------------------------------------"
	@echo "  TOTAL (5hr/day):          ~$$5-6/month"
	@echo ""
	@echo "If running 24/7:"
	@echo "  Node:                     ~$$4.50/month"
	@echo "  Load Balancer:            ~$$18.00/month"
	@echo "  ----------------------------------------"
	@echo "  TOTAL (24/7):             ~$$23/month"
	@echo ""
	@echo "Idle (stopped with 'make stop'):"
	@echo "  Disk storage only:        ~$$1.50/month"
	@echo ""

# ============================================================================
# Development
# ============================================================================

REGISTRY := europe-west1-docker.pkg.dev/hocuspocus-vpn/hocuspocus-vpn
PLATFORM := linux/amd64

build-local:
	docker build --platform $(PLATFORM) -t hocuspocus-vpn/mitmproxy:latest -f docker/mitmproxy/Dockerfile .
	docker build --platform $(PLATFORM) -t hocuspocus-vpn/vpn:latest -f docker/vpn/Dockerfile docker/vpn/

build-push: ## Build and push mitmproxy image to Artifact Registry
	docker build --platform $(PLATFORM) -t $(REGISTRY)/mitmproxy:latest -f docker/mitmproxy/Dockerfile .
	docker push $(REGISTRY)/mitmproxy:latest

deploy:
	kubectl apply -k k8s/

deploy-mitmproxy: build-push ## Build, push, and restart mitmproxy
	kubectl rollout restart deployment mitmproxy -n $(NAMESPACE)
	kubectl rollout status deployment mitmproxy -n $(NAMESPACE) --timeout=90s

restart-vpn:
	kubectl rollout restart daemonset vpn-server -n $(NAMESPACE)

restart-mitmproxy:
	kubectl rollout restart deployment mitmproxy -n $(NAMESPACE)

# ============================================================================
# E2E Testing
# ============================================================================

# Prerequisites:
#   1. iPhone connected via USB with VPN profile installed and connected
#   2. Appium running: appium (in separate terminal)
#   3. Virtual environment: make test-e2e-install
#   4. GKE cluster running: make startgcvpn

# Python/pytest from virtual environment
VENV := .venv
PYTEST := $(VENV)/bin/pytest
PYTHON := $(VENV)/bin/python

.PHONY: test-e2e test-e2e-flows test-e2e-overlay test-e2e-smoke test-e2e-setup

test-e2e: ## Run all E2E tests (requires Appium + connected iPhone)
	@echo "Running E2E tests..."
	@echo "Prerequisites: Appium running + iPhone connected + GKE VPN started"
	cd tests/e2e && $(CURDIR)/$(PYTEST) -v --tb=short

test-e2e-flows: ## Run main proxy flow tests only
	cd tests/e2e && $(CURDIR)/$(PYTEST) test_ios_flows.py -v --tb=short

test-e2e-overlay: ## Run location overlay tests only
	cd tests/e2e && $(CURDIR)/$(PYTEST) test_location_overlay.py -v --tb=short

test-e2e-smoke: ## Run smoke tests only (quick connectivity check)
	cd tests/e2e && $(CURDIR)/$(PYTEST) test_smoke.py -v --tb=short

test-e2e-setup: ## Build and install WebDriverAgent (first-time setup)
	@echo "Building WebDriverAgent for real device..."
	@echo "This will compile and install WDA on your connected iPhone."
	cd tests/e2e && USE_PREBUILT_WDA=false $(CURDIR)/$(PYTEST) test_smoke.py -v -k "test_can_connect" --tb=short || true
	@echo ""
	@echo "If this failed, you may need to manually set up WDA in Xcode:"
	@echo "  1. Open: ~/.appium/node_modules/appium-xcuitest-driver/node_modules/appium-webdriveragent/WebDriverAgent.xcodeproj"
	@echo "  2. Select WebDriverAgentRunner target"
	@echo "  3. Set Team ID and Bundle ID (com.hocuspocus.WebDriverAgentRunner)"
	@echo "  4. Build and run on your iPhone (Cmd+U)"

test-e2e-install: ## Install E2E test dependencies
	$(PYTHON) -m pip install -r tests/e2e/requirements.txt

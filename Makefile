.PHONY: help startgcvpn stopgcvpn status pods logs cost test-e2e test-e2e-flows test-e2e-overlay test-e2e-smoke test-e2e-setup test-e2e-install test-location-whitelist vpn-profile vpn-profile-serve vpn-profile-install vpn-profile-mdm verify-vpn verify-vpn-appium-prod verify-vpn-macos appium appium-stop appium-restart appium-logs macos-vpn-profile macos-vpn-profile-mdm macos-pf-killswitch macos-pf-install macos-pf-uninstall

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
	@echo "  make vpn-ip              - Get VPN LoadBalancer IP"
	@echo "  make vpn-status          - Check VPN connection status"
	@echo "  make vpn-profile DEVICE=iphone         - Generate VPN profile for device"
	@echo "  make vpn-profile-install DEVICE=iphone - Push profile via Apple Configurator"
	@echo "  make vpn-profile-mdm DEVICE=iphone     - Push profile via SimpleMDM"
	@echo "    Devices: iphone (IP: 10.10.10.10), macbook-air (IP: 10.10.10.20)"
	@echo "  make verify-vpn             - Quick VPN verification (uses pymobiledevice3)"
	@echo "  make verify-vpn-appium-prod - Full VPN verification (uses Appium, prod DB)"
	@echo ""
	@echo "E2E Testing:"
	@echo "  make appium           - Start Appium server"
	@echo "  make appium-stop      - Stop Appium server"
	@echo "  make appium-restart   - Restart Appium server"
	@echo "  make appium-logs      - Show Appium logs"
	@echo "  make test-e2e         - Run all E2E tests"
	@echo "  make test-e2e-flows   - Run proxy flow tests only"
	@echo "  make test-e2e-overlay - Run location overlay tests only"
	@echo "  make test-e2e-smoke   - Run smoke tests (quick check)"
	@echo "  make test-e2e-setup   - First-time WebDriverAgent setup"
	@echo "  make test-e2e-install - Install test dependencies"
	@echo "  make test-location-whitelist - Test per-location whitelist (must be at blocked location)"
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
	@echo ""
	@echo "macOS VPN Setup:"
	@echo "  make macos-vpn-profile     - Generate macOS VPN profile"
	@echo "  make macos-vpn-profile-mdm - Push macOS VPN profile via SimpleMDM"
	@echo "  make macos-pf-killswitch   - Generate pf firewall kill switch config"
	@echo "  make macos-pf-install      - Install pf kill switch (requires sudo)"
	@echo "  make macos-pf-uninstall    - Uninstall pf kill switch (requires sudo)"

# ============================================================================
# Daily Start/Stop (RECOMMENDED)
# ============================================================================

startgcvpn:
	@echo "Starting VPN infrastructure..."
	@echo ""
	@echo "Step 1/3: Scaling up node pool..."
	gcloud container clusters resize $(CLUSTER) \
		--node-pool $(NODE_POOL) \
		--num-nodes 2 \
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
	@echo ""
	@echo "Step 4/4: Verifying VPN connection..."
	@sleep 20
	@./scripts/verify-vpn.sh || echo "⚠️  Verification skipped or failed. Check manually."

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

verify-vpn: ## Quick VPN verification (uses pymobiledevice3)
	@./scripts/verify-vpn.sh

verify-vpn-appium-prod: ## Full VPN verification using Appium (bypasses browser cache, uses prod DB)
	@echo "Starting Appium-based verification..."
	@echo "NOTE: Requires Appium server running (make appium)"
	@source .venv/bin/activate && pytest tests/e2e_prod/test_verify_vpn.py -v -s --tb=short

test-location-whitelist: ## Test per-location whitelist (requires being at blocked location)
	@echo "Testing per-location whitelist..."
	@echo "NOTE: Must be at a blocked location (e.g., The Social Hub Vienna)"
	@source .venv/bin/activate && pytest tests/e2e_prod/test_verify_vpn.py::TestLocationWhitelist -v -s --tb=short

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

vpn-profile: ## Generate VPN profile for device (Usage: make vpn-profile DEVICE=iphone)
	@if [ -z "$(DEVICE)" ]; then \
		echo "Usage: make vpn-profile DEVICE=<device-name>"; \
		echo "  DEVICE: 'iphone' (IP: 10.10.10.10) or 'macbook-air' (IP: 10.10.10.20)"; \
		exit 1; \
	fi
	@./scripts/generate-vpn-profile.sh $(DEVICE)

vpn-profile-serve: ## Serve VPN profiles via HTTP
	@echo "Serving VPN profiles at http://$$(ipconfig getifaddr en0):8000/"
	@cd vpn-profiles && python3 -m http.server 8000

vpn-profile-install: ## Push VPN profile via Apple Configurator (Usage: make vpn-profile-install DEVICE=iphone)
	@if [ -z "$(DEVICE)" ]; then \
		echo "Usage: make vpn-profile-install DEVICE=<device-name>"; \
		echo "  DEVICE: 'iphone' (IP: 10.10.10.10) or 'macbook-air' (IP: 10.10.10.20)"; \
		exit 1; \
	fi
	@./scripts/generate-vpn-profile.sh $(DEVICE)
	@echo "Pushing VPN profile to connected device..."
	@"/Applications/Apple Configurator.app/Contents/MacOS/cfgutil" --foreach install-profile vpn-profiles/hocuspocus-vpn-$(DEVICE).mobileconfig
	@echo "Profile pushed! Tap 'Install' on the device to complete installation."

vpn-profile-mdm: ## Push VPN profile via SimpleMDM (Usage: make vpn-profile-mdm DEVICE=iphone)
	@if [ -z "$(DEVICE)" ]; then \
		echo "Usage: make vpn-profile-mdm DEVICE=<device-name>"; \
		echo "  DEVICE: 'iphone' (IP: 10.10.10.10) or 'macbook-air' (IP: 10.10.10.20)"; \
		exit 1; \
	fi
	@./scripts/push-vpn-profile-mdm.sh $(DEVICE)

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

build-push-vpn: ## Build and push VPN image to Artifact Registry
	docker build --platform $(PLATFORM) -t $(REGISTRY)/vpn:latest -f docker/vpn/Dockerfile docker/vpn/
	docker push $(REGISTRY)/vpn:latest

deploy-vpn: build-push-vpn ## Build, push, and restart VPN server
	kubectl rollout restart daemonset vpn-server -n $(NAMESPACE)
	@echo "Waiting for VPN server to restart..."
	@sleep 10
	kubectl get pods -n $(NAMESPACE) -l app=vpn-server

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
#   2. Appium running: make appium
#   3. Virtual environment: make test-e2e-install
#   4. GKE cluster running: make startgcvpn

# Appium server management
appium: ## Start Appium server in background
	@if pgrep -f "appium" > /dev/null; then \
		echo "Appium is already running (PID: $$(pgrep -f 'appium'))"; \
	else \
		echo "Starting Appium server..."; \
		appium > /tmp/appium.log 2>&1 & \
		sleep 3; \
		if curl -s http://127.0.0.1:4723/status | grep -q "ready"; then \
			echo "✅ Appium started (PID: $$(pgrep -f 'appium'))"; \
		else \
			echo "⚠️  Appium may still be starting. Check: tail -f /tmp/appium.log"; \
		fi \
	fi

appium-stop: ## Stop Appium server
	@if pgrep -f "appium" > /dev/null; then \
		echo "Stopping Appium (PID: $$(pgrep -f 'appium'))..."; \
		pkill -f "appium" || true; \
		sleep 1; \
		echo "✅ Appium stopped"; \
	else \
		echo "Appium is not running"; \
	fi

appium-restart: appium-stop ## Restart Appium server
	@sleep 2
	@$(MAKE) appium

appium-logs: ## Show Appium logs
	@tail -f /tmp/appium.log

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

# ============================================================================
# macOS VPN Setup
# ============================================================================

macos-vpn-profile: ## Generate macOS VPN profile (.mobileconfig)
	@./macos/scripts/generate-macos-vpn-profile.sh

macos-vpn-profile-mdm: ## Push macOS VPN profile via SimpleMDM
	@./macos/scripts/push-macos-vpn-profile-mdm.sh

macos-pf-killswitch: ## Generate pf firewall kill switch configuration
	@./macos/scripts/generate-pf-killswitch.sh

macos-pf-install: ## Install pf kill switch (blocks internet without VPN)
	@echo "Installing pf kill switch (requires sudo)..."
	@sudo ./macos/scripts/install-pf-killswitch.sh

macos-pf-uninstall: ## Uninstall pf kill switch (restores normal networking)
	@echo "Uninstalling pf kill switch (requires sudo)..."
	@sudo ./macos/scripts/uninstall-pf-killswitch.sh

macos-location-install: ## Install location sender daemon on macOS (sends GPS to proxy)
	@./macos/location-daemon/install.sh

macos-location-uninstall: ## Uninstall location sender daemon from macOS
	@echo "Uninstalling location sender..."
	@launchctl unload ~/Library/LaunchAgents/com.hocuspocus.location-sender.plist 2>/dev/null || true
	@rm -f ~/Library/LaunchAgents/com.hocuspocus.location-sender.plist
	@sudo rm -f /usr/local/bin/hocuspocus-location-sender.py
	@echo "Location sender uninstalled."

macos-location-logs: ## View location sender logs
	@tail -f /var/log/hocuspocus-location-sender.log

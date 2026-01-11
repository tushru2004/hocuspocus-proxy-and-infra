.PHONY: help init plan apply destroy kubeconfig argocd-password logs vpn-ip clean

# Default region
REGION ?= eu-frankfurt-1

help:
	@echo "Hocuspocus VPN - Oracle Kubernetes Engine"
	@echo ""
	@echo "Infrastructure:"
	@echo "  make init          - Initialize Terraform"
	@echo "  make plan          - Preview infrastructure changes"
	@echo "  make apply         - Deploy OKE cluster and ArgoCD"
	@echo "  make destroy       - Tear down all infrastructure"
	@echo ""
	@echo "Kubernetes:"
	@echo "  make kubeconfig    - Configure kubectl for the cluster"
	@echo "  make pods          - Show all pods"
	@echo "  make logs          - Show mitmproxy logs"
	@echo "  make logs-vpn      - Show VPN server logs"
	@echo ""
	@echo "ArgoCD:"
	@echo "  make argocd-password - Get ArgoCD admin password"
	@echo "  make argocd-url      - Get ArgoCD URL"
	@echo ""
	@echo "VPN:"
	@echo "  make vpn-ip        - Get VPN LoadBalancer IP"
	@echo "  make vpn-status    - Check VPN connection status"
	@echo ""
	@echo "Development:"
	@echo "  make build-local   - Build Docker images locally"
	@echo "  make push-local    - Push images to OCIR (local build)"
	@echo ""
	@echo "Cost:"
	@echo "  make cost          - Show estimated monthly cost"

# ============================================================================
# Infrastructure
# ============================================================================

init:
	cd terraform/oke && terraform init

plan:
	cd terraform/oke && terraform plan

apply:
	cd terraform/oke && terraform apply

destroy:
	cd terraform/oke && terraform destroy

# ============================================================================
# Kubernetes
# ============================================================================

kubeconfig:
	@cd terraform/oke && terraform output -raw kubeconfig_command | sh

pods:
	kubectl get pods -n hocuspocus -o wide

logs:
	kubectl logs -n hocuspocus -l app=mitmproxy -f

logs-vpn:
	kubectl logs -n hocuspocus -l app=vpn-server -f

# ============================================================================
# ArgoCD
# ============================================================================

argocd-password:
	@kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d && echo

argocd-url:
	@echo "ArgoCD URL: http://$$(kubectl get svc argocd-server -n argocd -o jsonpath='{.status.loadBalancer.ingress[0].ip}')"

argocd-sync:
	kubectl -n argocd patch application hocuspocus-vpn --type merge -p '{"operation": {"initiatedBy": {"username": "admin"}, "sync": {"syncStrategy": {"apply": {"force": true}}}}}'

# ============================================================================
# VPN
# ============================================================================

vpn-ip:
	@echo "VPN IP: $$(kubectl get svc vpn-service -n hocuspocus -o jsonpath='{.status.loadBalancer.ingress[0].ip}')"

vpn-status:
	kubectl exec -n hocuspocus -it $$(kubectl get pods -n hocuspocus -l app=vpn-server -o jsonpath='{.items[0].metadata.name}') -- ipsec statusall

# ============================================================================
# Development
# ============================================================================

build-local:
	docker build -t hocuspocus-vpn/mitmproxy:latest -f docker/mitmproxy/Dockerfile .
	docker build -t hocuspocus-vpn/vpn:latest -f docker/vpn/Dockerfile docker/vpn/

push-local:
	@echo "Getting OCIR namespace..."
	$(eval NAMESPACE := $(shell oci os ns get --query 'data' --raw-output))
	docker tag hocuspocus-vpn/mitmproxy:latest $(REGION).ocir.io/$(NAMESPACE)/hocuspocus-vpn/mitmproxy:latest
	docker tag hocuspocus-vpn/vpn:latest $(REGION).ocir.io/$(NAMESPACE)/hocuspocus-vpn/vpn:latest
	docker push $(REGION).ocir.io/$(NAMESPACE)/hocuspocus-vpn/mitmproxy:latest
	docker push $(REGION).ocir.io/$(NAMESPACE)/hocuspocus-vpn/vpn:latest

# ============================================================================
# Secrets
# ============================================================================

create-secrets:
	@echo "Creating secrets from secrets.yaml..."
	@if [ -f k8s/secrets.yaml ]; then \
		kubectl apply -f k8s/secrets.yaml; \
	else \
		echo "ERROR: k8s/secrets.yaml not found. Copy from secrets.yaml.example and fill in values."; \
		exit 1; \
	fi

create-ocir-secret:
	@echo "Creating OCIR pull secret..."
	@read -p "OCI Auth Token: " TOKEN; \
	read -p "OCI Username (e.g., oracleidentitycloudservice/user@email.com): " USERNAME; \
	NAMESPACE=$$(oci os ns get --query 'data' --raw-output); \
	kubectl create secret docker-registry ocir-secret \
		--namespace=hocuspocus \
		--docker-server=$(REGION).ocir.io \
		--docker-username="$$NAMESPACE/$$USERNAME" \
		--docker-password="$$TOKEN"

# ============================================================================
# Cost
# ============================================================================

cost:
	@echo ""
	@echo "Estimated Monthly Cost (~$$29/month):"
	@echo "  - OKE Control Plane (basic): $$0 (FREE)"
	@echo "  - Worker Node (2 OCPU, 4GB):  ~$$18.00"
	@echo "  - Network Load Balancer:      ~$$9.80"
	@echo "  - Block Storage (50GB):       ~$$1.28"
	@echo "  - OCIR:                       $$0 (included)"
	@echo "  - Egress (10TB free):         $$0"
	@echo ""
	@echo "Compare to AWS EKS: ~$$132/month"
	@echo "Compare to GKE:     ~$$54/month"
	@echo ""

# ============================================================================
# Cleanup
# ============================================================================

clean:
	rm -rf terraform/oke/.terraform
	rm -f terraform/oke/.terraform.lock.hcl
	rm -f terraform/oke/terraform.tfstate*

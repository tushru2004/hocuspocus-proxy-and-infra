# Hocuspocus VPN - Oracle Kubernetes Engine (GitOps)

Full Kubernetes-based VPN setup on Oracle Cloud with GitOps deployment via ArgoCD.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       Oracle Cloud (OCI)                         │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                      OKE Cluster                            │ │
│  │                                                              │ │
│  │   ┌─────────────────────────────────────────────────────┐  │ │
│  │   │              Worker Node (E4.Flex)                   │  │ │
│  │   │              2 OCPU, 4GB RAM                         │  │ │
│  │   │                                                      │  │ │
│  │   │  ┌──────────┐  ┌───────────┐  ┌──────────┐         │  │ │
│  │   │  │   VPN    │  │ mitmproxy │  │ Postgres │         │  │ │
│  │   │  │DaemonSet │  │Deployment │  │StatefulSet│         │  │ │
│  │   │  │(hostNet) │  │ (hostNet) │  │          │         │  │ │
│  │   │  └──────────┘  └───────────┘  └──────────┘         │  │ │
│  │   └─────────────────────────────────────────────────────┘  │ │
│  │                          │                                  │ │
│  │                 Network Load Balancer                       │ │
│  │               (UDP 500, 4500 for IKEv2)                     │ │
│  └──────────────────────────┼─────────────────────────────────┘ │
│                             │                                    │
│  ┌──────────────────────────┴─────────────────────────────────┐ │
│  │                   OCIR (Container Registry)                 │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ ArgoCD syncs from GitHub
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          GitHub                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ hocuspocus-oracle/                                       │   │
│  │  ├── src/           ← Application code                   │   │
│  │  ├── k8s/           ← K8s manifests (ArgoCD watches)     │   │
│  │  └── docker/        ← Dockerfiles                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  GitHub Actions: Push code → Build images → Push to OCIR        │
└─────────────────────────────────────────────────────────────────┘
```

## Cost Comparison

| Component | AWS EKS | Google GKE | Oracle OKE |
|-----------|---------|------------|------------|
| Control Plane | $72.00 | $0 (free tier) | **$0** (basic) |
| Worker Node | $30.37 | $24.27 | **$18.00** |
| Static IP | $3.60 | $2.88 | **$0** |
| Load Balancer | $16.20 | $18.00 | **$9.80** |
| Container Registry | ~$1.00 | ~$1.00 | **$0** |
| Egress (50GB) | $4.50 | $6.00 | **$0** |
| **TOTAL/month** | **~$132** | **~$54** | **~$29** |

## Prerequisites

1. **OCI Account** with API key configured
2. **OCI CLI** installed and configured (`oci setup config`)
3. **kubectl** installed
4. **Terraform** >= 1.0.0
5. **GitHub repository** for this project (for GitOps)

## Quick Start

### 1. Configure OCI Credentials

```bash
# Create terraform.tfvars
cd terraform/oke
cp terraform.tfvars.example terraform.tfvars
# Edit with your OCI OCIDs
```

### 2. Deploy Infrastructure

```bash
make init
make apply
```

### 3. Configure kubectl

```bash
make kubeconfig
kubectl get nodes
```

### 4. Create Secrets

```bash
# Copy and edit secrets
cp k8s/secrets.yaml.example k8s/secrets.yaml
# Edit k8s/secrets.yaml with real values

# Create OCIR pull secret
make create-ocir-secret

# Apply secrets
make create-secrets
```

### 5. Get ArgoCD Credentials

```bash
make argocd-url       # Get ArgoCD UI URL
make argocd-password  # Get admin password
```

### 6. Get VPN IP

```bash
make vpn-ip
```

## GitOps Workflow

1. **Push code** to `main` branch
2. **GitHub Actions** automatically:
   - Builds Docker images
   - Pushes to OCIR
   - Updates image tags in `k8s/kustomization.yaml`
3. **ArgoCD** automatically:
   - Detects manifest changes
   - Syncs new images to cluster
   - Rolls back on failure

## GitHub Secrets Required

Set these in your GitHub repository settings:

| Secret | Description |
|--------|-------------|
| `OCI_CONFIG` | Contents of ~/.oci/config |
| `OCI_KEY` | Contents of ~/.oci/oci_api_key.pem |
| `OCI_AUTH_TOKEN` | OCI Auth Token for OCIR |
| `OCI_USERNAME` | OCI username (e.g., oracleidentitycloudservice/user@email.com) |

## Commands

```bash
# Infrastructure
make init            # Initialize Terraform
make plan            # Preview changes
make apply           # Deploy cluster
make destroy         # Tear down everything

# Kubernetes
make kubeconfig      # Configure kubectl
make pods            # Show all pods
make logs            # Mitmproxy logs
make logs-vpn        # VPN server logs

# ArgoCD
make argocd-url      # Get ArgoCD URL
make argocd-password # Get admin password
make argocd-sync     # Force sync

# VPN
make vpn-ip          # Get VPN LoadBalancer IP
make vpn-status      # Check connection status

# Development
make build-local     # Build images locally
make push-local      # Push to OCIR

# Info
make cost            # Show cost breakdown
make help            # Show all commands
```

## Project Structure

```
hocuspocus-oracle/
├── terraform/
│   └── oke/                    # OKE infrastructure
│       ├── main.tf             # VCN, cluster, node pool
│       ├── argocd.tf           # ArgoCD installation
│       ├── variables.tf
│       └── outputs.tf
├── k8s/                        # Kubernetes manifests
│   ├── namespace.yaml
│   ├── vpn-daemonset.yaml      # StrongSwan VPN
│   ├── mitmproxy-deployment.yaml
│   ├── postgres-statefulset.yaml
│   ├── services.yaml           # LoadBalancer for VPN
│   ├── configmaps.yaml
│   ├── pvcs.yaml
│   ├── secrets.yaml.example
│   └── kustomization.yaml
├── docker/
│   ├── vpn/                    # StrongSwan container
│   │   ├── Dockerfile
│   │   └── entrypoint.sh
│   └── mitmproxy/              # Mitmproxy container
│       └── Dockerfile
├── src/                        # Application code
│   ├── proxy_handler.py
│   └── ...
├── .github/
│   └── workflows/
│       └── build-push.yaml     # CI pipeline
├── docker-requirements.txt
├── Makefile
└── README.md
```

## Troubleshooting

### Check pod status
```bash
kubectl get pods -n hocuspocus -o wide
kubectl describe pod <pod-name> -n hocuspocus
```

### View logs
```bash
make logs           # mitmproxy
make logs-vpn       # strongswan
```

### Check ArgoCD sync status
```bash
kubectl get application -n argocd
```

### VPN not connecting
1. Check LoadBalancer IP: `make vpn-ip`
2. Verify security lists allow UDP 500, 4500
3. Check VPN pod logs: `make logs-vpn`

### Force ArgoCD sync
```bash
make argocd-sync
```

## iOS Configuration

After deployment, generate the iOS VPN profile:

```bash
# Get VPN server IP
VPN_IP=$(make vpn-ip | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+')

# Copy CA cert from VPN pod
kubectl cp hocuspocus/<vpn-pod>:/etc/ipsec.d/cacerts/ca-cert.pem ./ca-cert.pem

# Generate .mobileconfig profile (use existing script or create manually)
```

## Security Notes

- Never commit `k8s/secrets.yaml` to git
- Use strong VPN passwords
- Regularly rotate OCI auth tokens
- Consider using OCI Vault for secrets management in production

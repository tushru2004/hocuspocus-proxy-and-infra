# =============================================================================
# GCP Configuration
# =============================================================================

variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "hocuspocus-vpn"
}

variable "region" {
  description = "GCP region"
  type        = string
  default     = "europe-west1"
}

variable "zone" {
  description = "GCP zone for zonal cluster"
  type        = string
  default     = "europe-west1-b"
}

# =============================================================================
# GKE Cluster Configuration
# =============================================================================

variable "cluster_name" {
  description = "Name of the GKE cluster"
  type        = string
  default     = "hocuspocus-vpn"
}

variable "kubernetes_version" {
  description = "Kubernetes version (use 'latest' for most recent)"
  type        = string
  default     = "latest"
}

# =============================================================================
# Node Pool Configuration
# =============================================================================

variable "node_pool_name" {
  description = "Name of the node pool"
  type        = string
  default     = "vpn-pool"
}

variable "machine_type" {
  description = "Machine type for worker nodes"
  type        = string
  default     = "e2-small"  # 2 vCPU, 2GB - cheapest option
}

variable "node_count" {
  description = "Number of nodes"
  type        = number
  default     = 1
}

variable "disk_size_gb" {
  description = "Boot disk size in GB"
  type        = number
  default     = 30
}

variable "preemptible" {
  description = "Use preemptible (spot) VMs for cost savings"
  type        = bool
  default     = true
}

# =============================================================================
# ArgoCD Configuration
# =============================================================================

variable "install_argocd" {
  description = "Whether to install ArgoCD"
  type        = bool
  default     = true
}

variable "argocd_namespace" {
  description = "Kubernetes namespace for ArgoCD"
  type        = string
  default     = "argocd"
}

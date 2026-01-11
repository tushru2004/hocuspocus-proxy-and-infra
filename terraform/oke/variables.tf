# =============================================================================
# OCI Authentication
# =============================================================================

variable "tenancy_ocid" {
  description = "OCID of your OCI tenancy"
  type        = string
}

variable "user_ocid" {
  description = "OCID of the user calling the API"
  type        = string
}

variable "fingerprint" {
  description = "Fingerprint for the API key"
  type        = string
}

variable "private_key_path" {
  description = "Path to the private key for API authentication"
  type        = string
  default     = "~/.oci/oci_api_key.pem"
}

variable "region" {
  description = "OCI region"
  type        = string
  default     = "eu-frankfurt-1"
}

variable "compartment_ocid" {
  description = "OCID of the compartment to create resources in"
  type        = string
}

# =============================================================================
# OKE Cluster Configuration
# =============================================================================

variable "cluster_name" {
  description = "Name of the OKE cluster"
  type        = string
  default     = "hocuspocus-vpn"
}

variable "kubernetes_version" {
  description = "Kubernetes version for the cluster"
  type        = string
  default     = "v1.31.1"
}

# =============================================================================
# Node Pool Configuration
# =============================================================================

variable "node_pool_name" {
  description = "Name of the node pool"
  type        = string
  default     = "hocuspocus-vpn-pool"
}

variable "node_shape" {
  description = "Shape for worker nodes"
  type        = string
  default     = "VM.Standard.E4.Flex"
}

variable "node_ocpus" {
  description = "Number of OCPUs per node"
  type        = number
  default     = 2
}

variable "node_memory_gb" {
  description = "Memory in GB per node"
  type        = number
  default     = 4
}

variable "node_count" {
  description = "Number of worker nodes"
  type        = number
  default     = 1
}

variable "node_boot_volume_size_gb" {
  description = "Boot volume size in GB per node"
  type        = number
  default     = 50
}

variable "use_preemptible_nodes" {
  description = "Use preemptible (spot) instances for cost savings"
  type        = bool
  default     = true
}

# =============================================================================
# Networking
# =============================================================================

variable "vcn_cidr" {
  description = "CIDR block for the VCN"
  type        = string
  default     = "10.0.0.0/16"
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

# =============================================================================
# Container Registry (OCIR)
# =============================================================================

variable "ocir_repo_name" {
  description = "Name of the OCIR repository"
  type        = string
  default     = "hocuspocus-vpn"
}

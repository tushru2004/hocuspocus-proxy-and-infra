terraform {
  required_version = ">= 1.0.0"

  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 5.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.25"
    }
  }
}

provider "oci" {
  tenancy_ocid     = var.tenancy_ocid
  user_ocid        = var.user_ocid
  fingerprint      = var.fingerprint
  private_key_path = var.private_key_path
  region           = var.region
}

# Kubernetes provider - configured after cluster creation
provider "kubernetes" {
  host                   = local.cluster_endpoint
  cluster_ca_certificate = base64decode(local.cluster_ca_certificate)
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "oci"
    args = [
      "ce", "cluster", "generate-token",
      "--cluster-id", oci_containerengine_cluster.oke_cluster.id,
      "--region", var.region
    ]
  }
}

# Helm provider for ArgoCD installation
provider "helm" {
  kubernetes {
    host                   = local.cluster_endpoint
    cluster_ca_certificate = base64decode(local.cluster_ca_certificate)
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "oci"
      args = [
        "ce", "cluster", "generate-token",
        "--cluster-id", oci_containerengine_cluster.oke_cluster.id,
        "--region", var.region
      ]
    }
  }
}

locals {
  cluster_endpoint       = "https://${oci_containerengine_cluster.oke_cluster.endpoints[0].public_endpoint}"
  cluster_ca_certificate = oci_containerengine_cluster.oke_cluster.endpoints[0].public_endpoint != "" ? data.oci_containerengine_cluster_kube_config.cluster_kube_config.content : ""
}

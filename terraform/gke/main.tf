# =============================================================================
# GKE Cluster
# =============================================================================

resource "google_container_cluster" "primary" {
  name     = var.cluster_name
  location = var.zone  # Zonal cluster (cheaper than regional)

  # We manage node pools separately
  remove_default_node_pool = true
  initial_node_count       = 1

  # Network configuration
  network    = "default"
  subnetwork = "default"

  # Cluster settings
  deletion_protection = false  # Allow terraform destroy

  # Release channel for auto-upgrades
  release_channel {
    channel = "REGULAR"
  }

  # Workload Identity (recommended)
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Logging and monitoring (use defaults, can disable to save ~$10/mo)
  logging_config {
    enable_components = ["SYSTEM_COMPONENTS"]
  }

  monitoring_config {
    enable_components = ["SYSTEM_COMPONENTS"]
    managed_prometheus {
      enabled = false  # Disable to save costs
    }
  }
}

# =============================================================================
# Node Pool
# =============================================================================

resource "google_container_node_pool" "primary_nodes" {
  name       = var.node_pool_name
  location   = var.zone
  cluster    = google_container_cluster.primary.name
  node_count = var.node_count

  node_config {
    machine_type = var.machine_type
    disk_size_gb = var.disk_size_gb
    disk_type    = "pd-standard"  # Cheaper than SSD

    # Use spot VMs for cost savings (replaces deprecated preemptible)
    spot = var.preemptible

    # OAuth scopes
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    # Labels
    labels = {
      app = "hocuspocus-vpn"
    }

    # Workload Identity
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }

  # Auto-repair and auto-upgrade
  management {
    auto_repair  = true
    auto_upgrade = true
  }
}

# =============================================================================
# Static IP for VPN
# =============================================================================

resource "google_compute_address" "vpn_ip" {
  name         = "${var.cluster_name}-vpn-ip"
  region       = var.region
  address_type = "EXTERNAL"
  network_tier = "STANDARD"  # Cheaper than PREMIUM
}

# =============================================================================
# Firewall Rules for VPN (IKEv2)
# =============================================================================

resource "google_compute_firewall" "vpn_ikev2" {
  name    = "${var.cluster_name}-vpn-ikev2"
  network = "default"

  allow {
    protocol = "udp"
    ports    = ["500", "4500"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["gke-${var.cluster_name}-${var.node_pool_name}"]
}

# =============================================================================
# Artifact Registry for Container Images
# =============================================================================

resource "google_artifact_registry_repository" "vpn_repo" {
  location      = var.region
  repository_id = "hocuspocus-vpn"
  description   = "Docker repository for Hocuspocus VPN images"
  format        = "DOCKER"
}

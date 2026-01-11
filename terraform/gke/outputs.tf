# =============================================================================
# Cluster Outputs
# =============================================================================

output "cluster_name" {
  description = "GKE cluster name"
  value       = google_container_cluster.primary.name
}

output "cluster_endpoint" {
  description = "GKE cluster endpoint"
  value       = google_container_cluster.primary.endpoint
  sensitive   = true
}

output "cluster_ca_certificate" {
  description = "GKE cluster CA certificate"
  value       = google_container_cluster.primary.master_auth[0].cluster_ca_certificate
  sensitive   = true
}

# =============================================================================
# Network Outputs
# =============================================================================

output "vpn_static_ip" {
  description = "Static IP for VPN service"
  value       = google_compute_address.vpn_ip.address
}

# =============================================================================
# Registry Outputs
# =============================================================================

output "artifact_registry_url" {
  description = "Artifact Registry URL for pushing images"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.vpn_repo.repository_id}"
}

# =============================================================================
# kubectl Configuration
# =============================================================================

output "kubectl_config_command" {
  description = "Command to configure kubectl"
  value       = "gcloud container clusters get-credentials ${google_container_cluster.primary.name} --zone ${var.zone} --project ${var.project_id}"
}

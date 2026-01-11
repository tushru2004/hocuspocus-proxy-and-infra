output "cluster_id" {
  description = "OCID of the OKE cluster"
  value       = oci_containerengine_cluster.oke_cluster.id
}

output "cluster_endpoint" {
  description = "Kubernetes API endpoint"
  value       = oci_containerengine_cluster.oke_cluster.endpoints[0].public_endpoint
}

output "kubeconfig_command" {
  description = "Command to configure kubectl"
  value       = "oci ce cluster create-kubeconfig --cluster-id ${oci_containerengine_cluster.oke_cluster.id} --file $HOME/.kube/config --region ${var.region} --token-version 2.0.0 --kube-endpoint PUBLIC_ENDPOINT"
}

output "vcn_id" {
  description = "OCID of the VCN"
  value       = oci_core_vcn.oke_vcn.id
}

output "node_pool_id" {
  description = "OCID of the node pool"
  value       = oci_containerengine_node_pool.oke_node_pool.id
}

output "ocir_mitmproxy_repo" {
  description = "OCIR repository for mitmproxy images"
  value       = "${var.region}.ocir.io/${data.oci_objectstorage_namespace.ns.namespace}/${oci_artifacts_container_repository.mitmproxy_repo.display_name}"
}

output "ocir_vpn_repo" {
  description = "OCIR repository for VPN images"
  value       = "${var.region}.ocir.io/${data.oci_objectstorage_namespace.ns.namespace}/${oci_artifacts_container_repository.vpn_repo.display_name}"
}

output "argocd_url" {
  description = "ArgoCD UI URL (get LoadBalancer IP after deployment)"
  value       = var.install_argocd ? "Run: kubectl get svc argocd-server -n ${var.argocd_namespace} -o jsonpath='{.status.loadBalancer.ingress[0].ip}'" : "ArgoCD not installed"
}

output "argocd_initial_password" {
  description = "Command to get ArgoCD initial admin password"
  value       = var.install_argocd ? "kubectl -n ${var.argocd_namespace} get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d" : "ArgoCD not installed"
}

output "estimated_monthly_cost" {
  description = "Estimated monthly cost breakdown"
  value       = <<-EOT
    Estimated Monthly Cost (~$29/month):
    - OKE Control Plane (basic): $0 (FREE)
    - Worker Node (${var.node_ocpus} OCPU, ${var.node_memory_gb}GB): ~$18.00
    - Load Balancer (flexible 10Mbps): ~$9.80
    - Block Storage (${var.node_boot_volume_size_gb}GB): ~$1.28
    - OCIR: $0 (included)
    - Egress (10TB free): $0

    Note: Using preemptible nodes saves ~50%. Actual costs may vary.
  EOT
}

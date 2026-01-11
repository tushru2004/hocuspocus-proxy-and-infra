# =============================================================================
# Data Sources
# =============================================================================

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

data "oci_containerengine_cluster_option" "cluster_option" {
  cluster_option_id = "all"
}

# Get latest OKE node image
data "oci_containerengine_node_pool_option" "node_pool_option" {
  node_pool_option_id = "all"
  compartment_id      = var.compartment_ocid
}

data "oci_core_images" "oke_images" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Oracle Linux"
  operating_system_version = "8"
  shape                    = var.node_shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"

  filter {
    name   = "display_name"
    values = ["^.*OKE.*$"]
    regex  = true
  }
}

# =============================================================================
# Networking - VCN
# =============================================================================

resource "oci_core_vcn" "oke_vcn" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.cluster_name}-vcn"
  cidr_blocks    = [var.vcn_cidr]
  dns_label      = "okevpn"
}

resource "oci_core_internet_gateway" "oke_igw" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.oke_vcn.id
  display_name   = "${var.cluster_name}-igw"
  enabled        = true
}

resource "oci_core_route_table" "oke_public_rt" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.oke_vcn.id
  display_name   = "${var.cluster_name}-public-rt"

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_internet_gateway.oke_igw.id
  }
}

# =============================================================================
# Networking - Security Lists
# =============================================================================

# Security list for K8s API endpoint
resource "oci_core_security_list" "oke_api_sl" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.oke_vcn.id
  display_name   = "${var.cluster_name}-api-sl"

  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
    stateless   = false
  }

  ingress_security_rules {
    protocol    = "6" # TCP
    source      = "0.0.0.0/0"
    stateless   = false
    description = "Kubernetes API"
    tcp_options {
      min = 6443
      max = 6443
    }
  }
}

# Security list for worker nodes
resource "oci_core_security_list" "oke_nodes_sl" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.oke_vcn.id
  display_name   = "${var.cluster_name}-nodes-sl"

  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
    stateless   = false
  }

  # K8s API
  ingress_security_rules {
    protocol    = "6"
    source      = "0.0.0.0/0"
    stateless   = false
    description = "Kubernetes API"
    tcp_options {
      min = 6443
      max = 6443
    }
  }

  # Kubelet
  ingress_security_rules {
    protocol    = "6"
    source      = "0.0.0.0/0"
    stateless   = false
    description = "Kubelet"
    tcp_options {
      min = 10250
      max = 10250
    }
  }

  # SSH
  ingress_security_rules {
    protocol    = "6"
    source      = "0.0.0.0/0"
    stateless   = false
    description = "SSH"
    tcp_options {
      min = 22
      max = 22
    }
  }

  # NodePort range
  ingress_security_rules {
    protocol    = "6"
    source      = "0.0.0.0/0"
    stateless   = false
    description = "NodePort TCP"
    tcp_options {
      min = 30000
      max = 32767
    }
  }

  ingress_security_rules {
    protocol    = "17"
    source      = "0.0.0.0/0"
    stateless   = false
    description = "NodePort UDP"
    udp_options {
      min = 30000
      max = 32767
    }
  }

  # IKEv2 VPN ports
  ingress_security_rules {
    protocol    = "17"
    source      = "0.0.0.0/0"
    stateless   = false
    description = "IKEv2 - IKE"
    udp_options {
      min = 500
      max = 500
    }
  }

  ingress_security_rules {
    protocol    = "17"
    source      = "0.0.0.0/0"
    stateless   = false
    description = "IKEv2 - NAT-T"
    udp_options {
      min = 4500
      max = 4500
    }
  }

  # HTTP/HTTPS for Load Balancer
  ingress_security_rules {
    protocol    = "6"
    source      = "0.0.0.0/0"
    stateless   = false
    description = "HTTP"
    tcp_options {
      min = 80
      max = 80
    }
  }

  ingress_security_rules {
    protocol    = "6"
    source      = "0.0.0.0/0"
    stateless   = false
    description = "HTTPS"
    tcp_options {
      min = 443
      max = 443
    }
  }

  # VCN internal communication
  ingress_security_rules {
    protocol    = "all"
    source      = var.vcn_cidr
    stateless   = false
    description = "VCN internal"
  }

  # ICMP
  ingress_security_rules {
    protocol    = "1"
    source      = "0.0.0.0/0"
    stateless   = false
    description = "ICMP Path Discovery"
    icmp_options {
      type = 3
      code = 4
    }
  }
}

# =============================================================================
# Networking - Subnets
# =============================================================================

resource "oci_core_subnet" "oke_api_subnet" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.oke_vcn.id
  display_name               = "${var.cluster_name}-api-subnet"
  cidr_block                 = cidrsubnet(var.vcn_cidr, 12, 0) # /28
  dns_label                  = "api"
  route_table_id             = oci_core_route_table.oke_public_rt.id
  security_list_ids          = [oci_core_security_list.oke_api_sl.id]
  prohibit_public_ip_on_vnic = false
}

resource "oci_core_subnet" "oke_nodes_subnet" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.oke_vcn.id
  display_name               = "${var.cluster_name}-nodes-subnet"
  cidr_block                 = cidrsubnet(var.vcn_cidr, 8, 1) # /24
  dns_label                  = "nodes"
  route_table_id             = oci_core_route_table.oke_public_rt.id
  security_list_ids          = [oci_core_security_list.oke_nodes_sl.id]
  prohibit_public_ip_on_vnic = false
}

resource "oci_core_subnet" "oke_lb_subnet" {
  compartment_id             = var.compartment_ocid
  vcn_id                     = oci_core_vcn.oke_vcn.id
  display_name               = "${var.cluster_name}-lb-subnet"
  cidr_block                 = cidrsubnet(var.vcn_cidr, 8, 2) # /24
  dns_label                  = "lb"
  route_table_id             = oci_core_route_table.oke_public_rt.id
  security_list_ids          = [oci_core_security_list.oke_nodes_sl.id]
  prohibit_public_ip_on_vnic = false
}

# =============================================================================
# OKE Cluster
# =============================================================================

resource "oci_containerengine_cluster" "oke_cluster" {
  compartment_id     = var.compartment_ocid
  kubernetes_version = var.kubernetes_version
  name               = var.cluster_name
  vcn_id             = oci_core_vcn.oke_vcn.id

  cluster_pod_network_options {
    cni_type = "FLANNEL_OVERLAY"
  }

  endpoint_config {
    is_public_ip_enabled = true
    subnet_id            = oci_core_subnet.oke_api_subnet.id
  }

  options {
    service_lb_subnet_ids = [oci_core_subnet.oke_lb_subnet.id]

    add_ons {
      is_kubernetes_dashboard_enabled = false
      is_tiller_enabled               = false
    }

    kubernetes_network_config {
      pods_cidr     = "10.244.0.0/16"
      services_cidr = "10.96.0.0/16"
    }
  }
}

# =============================================================================
# Node Pool
# =============================================================================

resource "oci_containerengine_node_pool" "oke_node_pool" {
  cluster_id         = oci_containerengine_cluster.oke_cluster.id
  compartment_id     = var.compartment_ocid
  kubernetes_version = var.kubernetes_version
  name               = var.node_pool_name

  node_shape = var.node_shape

  node_shape_config {
    ocpus         = var.node_ocpus
    memory_in_gbs = var.node_memory_gb
  }

  node_source_details {
    source_type             = "IMAGE"
    image_id                = data.oci_core_images.oke_images.images[0].id
    boot_volume_size_in_gbs = var.node_boot_volume_size_gb
  }

  node_config_details {
    size = var.node_count

    placement_configs {
      availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
      subnet_id           = oci_core_subnet.oke_nodes_subnet.id
    }

    # Preemptible (spot) instances for cost savings
    dynamic "node_pool_pod_network_option_details" {
      for_each = var.use_preemptible_nodes ? [1] : []
      content {
        cni_type = "FLANNEL_OVERLAY"
      }
    }

    is_pv_encryption_in_transit_enabled = false
  }

  initial_node_labels {
    key   = "app"
    value = "hocuspocus-vpn"
  }

  # Use preemptible capacity if enabled
  node_eviction_node_pool_settings {
    eviction_grace_duration              = "PT1H"
    is_force_delete_after_grace_duration = true
  }
}

# =============================================================================
# Kubeconfig Data Source
# =============================================================================

data "oci_containerengine_cluster_kube_config" "cluster_kube_config" {
  cluster_id = oci_containerengine_cluster.oke_cluster.id
}

# =============================================================================
# Container Registry (OCIR)
# =============================================================================

data "oci_objectstorage_namespace" "ns" {
  compartment_id = var.compartment_ocid
}

resource "oci_artifacts_container_repository" "mitmproxy_repo" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.ocir_repo_name}/mitmproxy"
  is_public      = false
}

resource "oci_artifacts_container_repository" "vpn_repo" {
  compartment_id = var.compartment_ocid
  display_name   = "${var.ocir_repo_name}/vpn"
  is_public      = false
}

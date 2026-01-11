# =============================================================================
# ArgoCD Installation via Helm
# =============================================================================

resource "kubernetes_namespace" "argocd" {
  count = var.install_argocd ? 1 : 0

  metadata {
    name = var.argocd_namespace
  }

  depends_on = [oci_containerengine_node_pool.oke_node_pool]
}

resource "helm_release" "argocd" {
  count = var.install_argocd ? 1 : 0

  name       = "argocd"
  repository = "https://argoproj.github.io/argo-helm"
  chart      = "argo-cd"
  version    = "5.51.6"
  namespace  = var.argocd_namespace

  values = [
    <<-EOT
    server:
      service:
        type: LoadBalancer
        annotations:
          oci.oraclecloud.com/load-balancer-type: "lb"
          service.beta.kubernetes.io/oci-load-balancer-shape: "flexible"
          service.beta.kubernetes.io/oci-load-balancer-shape-flex-min: "10"
          service.beta.kubernetes.io/oci-load-balancer-shape-flex-max: "10"
      extraArgs:
        - --insecure  # For initial setup; remove in production

    configs:
      params:
        server.insecure: true

    controller:
      resources:
        requests:
          cpu: 100m
          memory: 256Mi
        limits:
          cpu: 500m
          memory: 512Mi

    repoServer:
      resources:
        requests:
          cpu: 50m
          memory: 128Mi
        limits:
          cpu: 250m
          memory: 256Mi

    redis:
      resources:
        requests:
          cpu: 50m
          memory: 64Mi
        limits:
          cpu: 100m
          memory: 128Mi

    applicationSet:
      enabled: false

    notifications:
      enabled: false
    EOT
  ]

  depends_on = [kubernetes_namespace.argocd]
}

# =============================================================================
# ArgoCD Application for Hocuspocus VPN
# =============================================================================

resource "kubernetes_manifest" "argocd_app" {
  count = var.install_argocd ? 1 : 0

  manifest = {
    apiVersion = "argoproj.io/v1alpha1"
    kind       = "Application"
    metadata = {
      name      = "hocuspocus-vpn"
      namespace = var.argocd_namespace
    }
    spec = {
      project = "default"
      source = {
        repoURL        = "https://github.com/tushru2004/hocuspocus-oracle.git"
        targetRevision = "main"
        path           = "k8s"
      }
      destination = {
        server    = "https://kubernetes.default.svc"
        namespace = "hocuspocus"
      }
      syncPolicy = {
        automated = {
          prune    = true
          selfHeal = true
        }
        syncOptions = [
          "CreateNamespace=true"
        ]
      }
    }
  }

  depends_on = [helm_release.argocd]
}

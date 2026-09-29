# Installs kube-prometheus-stack (Prometheus Operator, Prometheus, Alertmanager, Grafana,
# node-exporter, kube-state-metrics) with one shared values file, so the local kind
# cluster, CI and EKS all run the same monitoring configuration.

terraform {
  required_version = ">= 1.6"
  required_providers {
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.17"
    }
  }
}

resource "helm_release" "kube_prometheus_stack" {
  name             = "kube-prometheus-stack"
  repository       = "https://prometheus-community.github.io/helm-charts"
  chart            = "kube-prometheus-stack"
  version          = var.chart_version
  namespace        = var.namespace
  create_namespace = true
  timeout          = 900
  wait             = true

  values = concat(
    [file("${path.module}/../../../observability/kube-prometheus-stack.values.yaml")],
    var.extra_values,
  )

  set_sensitive {
    name  = "grafana.adminPassword"
    value = var.grafana_admin_password
  }
}

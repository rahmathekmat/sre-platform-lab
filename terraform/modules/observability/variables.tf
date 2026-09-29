variable "namespace" {
  description = "Namespace for the monitoring stack. The orders-api NetworkPolicy allows scrapes from this namespace."
  type        = string
  default     = "monitoring"
}

variable "chart_version" {
  description = "kube-prometheus-stack chart version. Keep in sync with KPS_CHART_VERSION in the Makefile and CI."
  type        = string
  default     = "75.0.0"
}

variable "extra_values" {
  description = "Additional Helm values documents layered on top of the shared values file (for example, persistent storage on EKS)."
  type        = list(string)
  default     = []
}

variable "grafana_admin_password" {
  description = "Grafana admin password."
  type        = string
  sensitive   = true
}

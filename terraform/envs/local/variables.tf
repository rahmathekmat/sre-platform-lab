variable "cluster_name" {
  description = "kind cluster name."
  type        = string
  default     = "sre-lab"
}

variable "node_image" {
  description = "kindest/node image, which pins the Kubernetes version."
  type        = string
  default     = "kindest/node:v1.31.4"
}

variable "grafana_admin_password" {
  description = "Grafana admin password for the local cluster."
  type        = string
  sensitive   = true
  default     = "sre-lab-admin"
}

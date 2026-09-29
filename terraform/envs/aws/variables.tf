variable "region" {
  description = "AWS region."
  type        = string
  default     = "ap-southeast-2"
}

variable "cluster_name" {
  description = "EKS cluster name, also used to name the VPC."
  type        = string
  default     = "sre-lab"
}

variable "kubernetes_version" {
  description = "EKS Kubernetes version."
  type        = string
  default     = "1.31"
}

variable "vpc_cidr" {
  description = "VPC CIDR block."
  type        = string
  default     = "10.40.0.0/16"
}

variable "single_nat_gateway" {
  description = "One shared NAT gateway (cheap, single AZ failure domain) or one per AZ (resilient)."
  type        = bool
  default     = true
}

variable "node_instance_types" {
  description = "Instance types for the managed node group."
  type        = list(string)
  default     = ["t3.large"]
}

variable "node_min_size" {
  description = "Minimum nodes. Three spreads orders-api replicas across AZs."
  type        = number
  default     = 3
}

variable "node_max_size" {
  description = "Maximum nodes."
  type        = number
  default     = 6
}

variable "grafana_admin_password" {
  description = "Grafana admin password. Pass via TF_VAR_grafana_admin_password, never commit it."
  type        = string
  sensitive   = true
}

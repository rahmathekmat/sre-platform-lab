output "namespace" {
  description = "Namespace the monitoring stack runs in."
  value       = helm_release.kube_prometheus_stack.namespace
}

output "chart_version" {
  description = "Deployed kube-prometheus-stack chart version."
  value       = helm_release.kube_prometheus_stack.version
}

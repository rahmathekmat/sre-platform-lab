output "kubeconfig_context" {
  description = "kubectl context for the cluster."
  value       = "kind-${kind_cluster.this.name}"
}

output "grafana" {
  description = "How to reach Grafana."
  value       = "kubectl -n ${module.observability.namespace} port-forward svc/kube-prometheus-stack-grafana 3000:80"
}

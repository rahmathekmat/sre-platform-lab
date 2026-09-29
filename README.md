# sre-platform-lab

[![ci](https://github.com/rahmathekmat/sre-platform-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/rahmathekmat/sre-platform-lab/actions/workflows/ci.yml)

A small service run the way I think production services should be run: infrastructure as code, Kubernetes manifests hardened by default, SLOs defined up front, alerts that page on error budget burn instead of raw thresholds, runbooks for every page, and a CI pipeline that proves the alerting works by breaking the service on purpose.

The app is deliberately boring (`orders-api`, a few endpoints). Everything interesting is around it.

## What's in here

| Area | What it shows |
|---|---|
| `terraform/` | kind cluster for local work and a production-shaped AWS reference (VPC over 3 AZs, EKS managed node group), both sharing one `observability` module that installs kube-prometheus-stack |
| `k8s/` | Kustomize base with probes (startup, liveness, readiness), graceful drain, PodDisruptionBudget, HPA, topology spread, default-deny NetworkPolicy, restricted Pod Security, read-only root filesystem, non-root user |
| `k8s/base/prometheusrule.yaml` | SLOs as code: 99.9% availability and 99% under 300ms, with multiwindow, multi-burn-rate alerts from the Google SRE Workbook |
| `observability/tests/` | `promtool` unit tests for every alert: healthy traffic stays quiet, 10% errors page, 0.5% errors open a ticket without paging, slow requests page, dead targets page |
| `k8s/base/dashboards/` | Grafana SLO dashboard loaded automatically by the Grafana sidecar: availability, budget remaining, burn rate, latency percentiles |
| `docs/runbooks/` | A runbook for every alert, linked from the alert's `runbook_url` |
| `scripts/gameday.sh` | Fault injection: error rate, latency, pod kill, node drain |
| `.github/workflows/ci.yml` | Lint and tests, promtool, kubeconform against Kubernetes and CRD schemas, terraform validate, then a full deploy to kind that injects 50% errors and fails the build unless the fast burn alert fires |

## Architecture

```
                 ┌──────────────────────── kind (local/CI) or EKS ────────────────────────┐
                 │                                                                         │
  loadgen Job ──►│  Service orders-api ──► orders-api pods x3 (spread across nodes, PDB 2) │
                 │                               │ /metrics                                │
                 │                               ▼                                         │
                 │  ServiceMonitor ──► Prometheus ──► SLO recording rules ──► burn alerts  │
                 │                         │                                    │          │
                 │                         ▼                                    ▼          │
                 │                      Grafana (SLO dashboard)          Alertmanager      │
                 │                                                   page / ticket routes  │
                 └─────────────────────────────────────────────────────────────────────────┘
```

## SLOs

| SLI | Target | Window | Page when | Ticket when |
|---|---|---|---|---|
| Availability: share of `/api/orders` requests that are not 5xx | 99.9% | 30 days | burn rate over 14.4x (1h and 5m) or over 6x (6h and 30m) | burn rate over 3x (1d and 2h) or over 1x (3d and 6h) |
| Latency: share of `/api/orders` requests under 300ms | 99% | 30 days | burn rate over 14.4x (1h and 5m) | |

Why burn rates instead of "error rate > 1% for 5 minutes": a threshold either pages on every short blip or misses a slow leak that quietly spends the month's budget. The two-window pairs page quickly on a real outage, reset quickly after recovery, and send slow burns to a ticket queue instead of waking someone up. The reasoning and the numbers are in [docs/slo.md](docs/slo.md).

## Run it locally

Needs Docker, kind, kubectl, Terraform and Python 3.11+.

```bash
make up        # kind cluster (1 control plane, 2 workers) + kube-prometheus-stack via Terraform
make build     # build the image and load it into kind
make deploy    # orders-api, SLO rules, dashboard
make load      # start synthetic traffic
make e2e       # the same end to end checks CI runs, including the game day

kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80
# http://localhost:3000  admin / sre-lab-admin  →  "orders-api / SLO overview"

make down
```

Checks that don't need a cluster:

```bash
make test        # ruff + pytest
make test-rules  # promtool check and unit tests for the alerts
make lint-k8s    # kustomize build | kubeconform
make tf-check    # terraform fmt + validate
```

## Game day

[docs/gameday.md](docs/gameday.md) walks through four experiments with a hypothesis, the command, what to watch and what "pass" looks like:

1. Inject 10% errors: the fast burn page fires within minutes, then resolves after recovery
2. Add 400ms latency: the latency page fires, the availability alerts stay quiet
3. Kill a pod: no failed requests, because readiness and the Service route around it
4. Drain a node: the PodDisruptionBudget keeps at least 2 pods serving throughout

CI runs a version of experiment 1 on every push.

## Design notes

- **One source of truth for alert rules.** The `PrometheusRule` in `k8s/base` is what gets deployed. CI extracts its `.spec` and runs the promtool tests against it, so the tested rules and the deployed rules cannot drift.
- **One values file for the monitoring stack.** Terraform (local and EKS) and CI install kube-prometheus-stack from `observability/kube-prometheus-stack.values.yaml`. EKS layers persistent storage and longer retention on top.
- **Graceful shutdown.** On SIGTERM the app fails readiness first, waits for endpoints to update, then stops accepting connections, so rolling deploys don't drop requests. Liveness stays green while draining so the kubelet doesn't kill a pod that is shutting down cleanly.
- **Bounded metric cardinality.** Unknown paths are recorded as `route="unmatched"` rather than the raw path, so a scanner can't create unlimited time series.
- **Rollouts never reduce capacity.** `maxUnavailable: 0`, `maxSurge: 1`, and a PDB of 2 out of 3.

## Not done yet

- Canary or progressive delivery (Argo Rollouts gated on the burn rate)
- Tracing with OpenTelemetry
- Real Alertmanager receivers (routes are defined, receivers point at `null`)
- Applying the AWS environment from CI with OIDC and a plan/apply approval step

## License

MIT

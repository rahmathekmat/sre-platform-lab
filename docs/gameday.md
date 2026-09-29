# Game day

Run these on the local kind cluster (`make up build deploy load`). Keep Grafana open on the "orders-api / SLO overview" dashboard and Prometheus alerts at `kubectl -n monitoring port-forward svc/kube-prometheus-stack-prometheus 9090` → http://localhost:9090/alerts.

Write down the hypothesis before each experiment, and record what actually happened, especially when it doesn't match.

## 1. Error spike

- **Hypothesis:** at 10% errors, `OrdersApiErrorBudgetBurnFast` goes pending within a minute and fires about 2 minutes later. `OrdersApiErrorBudgetBurnSlow` also goes pending. After recovery the page clears within about 5 minutes because the 5m window drops below threshold.
- **Run:** `scripts/gameday.sh errors 0.1`, wait 10 minutes, then `scripts/gameday.sh recover`
- **Watch:** "Burn rate (1h)" stat goes above 14.4, "Error budget remaining" drops.
- **Pass:** page fires, resolves after recovery, and the runbook link in the alert leads to steps that would have found the cause.

## 2. Latency regression

- **Hypothesis:** at +400ms every request misses the 300ms threshold, so `OrdersApiLatencyBudgetBurnFast` fires. Availability alerts stay quiet because nothing returns 5xx.
- **Run:** `scripts/gameday.sh latency 400`, wait 5 minutes, then `scripts/gameday.sh recover`
- **Pass:** only the latency page fires. This is the reason latency and availability are separate SLOs.

## 3. Pod failure

- **Hypothesis:** killing one of three pods causes zero failed requests. Readiness removes it from the Service and the Deployment replaces it.
- **Run:** `scripts/gameday.sh kill-pod` while loadgen is running
- **Watch:** "Request rate by status" panel should show no 5xx.
- **Pass:** no 5xx, replacement pod Ready in under 30 seconds.

## 4. Node drain

- **Hypothesis:** draining a worker never takes serving pods below 2, because of the PodDisruptionBudget, and requests keep succeeding.
- **Run:** `scripts/gameday.sh drain-node`, then `kubectl uncordon <node>`
- **Watch:** `kubectl -n orders get pods -o wide -w` and `kubectl -n orders get pdb`
- **Pass:** evictions happen one at a time, ALLOWED DISRUPTIONS never goes negative, no 5xx.

## Automated version

CI runs experiment 1 at 50% errors on every push (`scripts/e2e_check.py`). The build fails if the page does not fire, which means a change that silently breaks metrics, scraping, recording rules or the alert expression cannot merge.

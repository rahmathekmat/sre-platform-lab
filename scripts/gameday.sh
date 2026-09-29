#!/usr/bin/env bash
# Game day fault injection for orders-api. See docs/gameday.md for the full exercise.
#
#   scripts/gameday.sh errors 0.1     # 10% of requests return 500
#   scripts/gameday.sh latency 400    # add 400ms to every request
#   scripts/gameday.sh kill-pod       # delete one pod, watch the PDB and readiness hold
#   scripts/gameday.sh drain-node     # drain a worker node (kind), watch the PDB hold
#   scripts/gameday.sh recover        # clear all injected faults
set -euo pipefail

NS=orders
DEPLOY=deployment/orders-api

case "${1:-}" in
  errors)
    kubectl -n "$NS" set env "$DEPLOY" FAULT_ERROR_RATE="${2:?error rate, e.g. 0.1}"
    ;;
  latency)
    kubectl -n "$NS" set env "$DEPLOY" FAULT_LATENCY_MS="${2:?latency in ms, e.g. 400}"
    ;;
  kill-pod)
    pod=$(kubectl -n "$NS" get pods -l app.kubernetes.io/name=orders-api -o name | shuf -n1)
    echo "deleting $pod"
    kubectl -n "$NS" delete "$pod" --wait=false
    kubectl -n "$NS" get pods -l app.kubernetes.io/name=orders-api -w &
    sleep 20; kill $! 2>/dev/null || true
    exit 0
    ;;
  drain-node)
    node=$(kubectl get nodes -l '!node-role.kubernetes.io/control-plane' -o name | shuf -n1)
    echo "draining $node (uncordon with: kubectl uncordon ${node#node/})"
    kubectl drain "${node#node/}" --ignore-daemonsets --delete-emptydir-data --timeout=120s
    exit 0
    ;;
  recover)
    kubectl -n "$NS" set env "$DEPLOY" FAULT_ERROR_RATE=0 FAULT_LATENCY_MS=0
    ;;
  *)
    sed -n '2,9p' "$0"
    exit 1
    ;;
esac

kubectl -n "$NS" rollout status "$DEPLOY" --timeout=180s

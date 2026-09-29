# OrdersApiLatencyBudgetBurnFast

**Severity:** page. **Meaning:** more than 14.4% of `/api/orders` requests are slower than 300ms against an SLO of 99% under 300ms. Requests are succeeding but users are waiting.

## First 5 minutes

1. Open the "Latency percentiles" panel. Is it every request (p50 up) or a tail (only p99 up)?
   - **Everything is slower:** something added fixed latency. Check recent deploys and config, and that `FAULT_LATENCY_MS` is `0`. Roll back if a change lines up.
   - **Only the tail:** usually saturation. Go to step 2.
2. Check saturation:
   ```bash
   kubectl -n orders top pods
   kubectl -n orders get hpa orders-api
   ```
   ```promql
   sum(http_requests_in_flight{job="orders-api"})
   ```
   If pods are CPU bound and the HPA is at `maxReplicas`, raise the ceiling or scale manually:
   `kubectl -n orders scale deployment/orders-api --replicas=6` (the HPA will adjust from there).
3. If CPU is fine, the delay is likely downstream. Check dependency latency and error rates.

## Resolved when

The 5m share of slow requests is back under 1% and the alert has cleared.

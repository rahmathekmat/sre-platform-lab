# OrdersApiErrorBudgetBurnFast

**Severity:** page. **Meaning:** orders-api is returning enough 5xx errors to spend at least 2% of the 30 day error budget per hour. Users are affected now.

## First 5 minutes

1. Acknowledge the page and open the "orders-api / SLO overview" dashboard.
2. Check whether it's getting worse or better: compare the 5m and 1h lines on "Error ratio vs SLO".
3. Check what changed recently. Most incidents follow a change.
   ```bash
   kubectl -n orders rollout history deployment/orders-api
   kubectl -n orders get events --sort-by=.lastTimestamp | tail -20
   kubectl -n orders describe deployment/orders-api | grep -A3 -i env
   ```
4. **If a deploy or config change lines up with the start of errors, roll it back first and investigate after:**
   ```bash
   kubectl -n orders rollout undo deployment/orders-api
   kubectl -n orders rollout status deployment/orders-api
   ```

## If nothing changed

- Are errors on every pod or one? A single bad pod points to the node or that instance.
  ```promql
  sum by (pod) (rate(http_requests_total{job="orders-api",code=~"5.."}[5m]))
  ```
  If it's one pod: `kubectl -n orders delete pod <pod>` and check the node it was on.
- Read the logs for the error:
  ```bash
  kubectl -n orders logs -l app.kubernetes.io/name=orders-api --tail=100 | grep -i error
  ```
- Check resource pressure: restarts, OOMKilled, CPU throttling.
  ```bash
  kubectl -n orders get pods
  kubectl -n orders top pods
  ```
- Check that no fault injection is active: `FAULT_ERROR_RATE` must be `0`. Clear it with `scripts/gameday.sh recover`.

## Resolved when

The 5m error ratio is back under 0.1% and the alert has cleared. Note how much budget was spent (the "Error budget remaining" stat). If it was more than 20%, open a postmortem.

# OrdersApiErrorBudgetBurnSlow

**Severity:** ticket. **Meaning:** orders-api's error rate has been above its 0.1% SLO for hours to days. Nobody needs to wake up, but if it keeps going the 30 day budget runs out.

## Triage during business hours

1. On the dashboard, find when "Error ratio vs SLO" first went above the red line. Match it to deploys (`kubectl -n orders rollout history deployment/orders-api`) or dependency changes.
2. Look for a pattern in the errors:
   ```promql
   sum by (code) (rate(http_requests_total{job="orders-api"}[1h]))
   sum by (pod) (rate(http_requests_total{job="orders-api",code=~"5.."}[1h]))
   ```
   Errors on one pod point to a bad node or instance. Errors on every pod point to code, config or a dependency.
3. Raise a fix with an owner and a date, linked to this alert.
4. If the remaining budget is under 25%, apply the error budget policy in [docs/slo.md](../slo.md): pause feature releases until it recovers.

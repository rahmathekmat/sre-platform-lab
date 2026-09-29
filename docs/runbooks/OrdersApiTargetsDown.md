# OrdersApiTargetsDown

**Severity:** page. **Meaning:** Prometheus can't scrape a single orders-api pod. Either the service is completely down, or monitoring has lost sight of it. **In both cases the SLO alerts are blind**, which is why this pages.

## First 5 minutes

1. Is the service actually down?
   ```bash
   kubectl -n orders get pods,endpoints
   kubectl -n orders port-forward svc/orders-api 8080:80 & curl -s localhost:8080/api/orders
   ```
   - **Pods not running or not Ready:** treat it as an outage. `kubectl -n orders describe pod <pod>` for image pull errors, crash loops, failed probes, or pods stuck Pending. Roll back if a deploy caused it.
   - **Pods fine and answering:** monitoring has lost them. Go to step 2.
2. Check discovery in Prometheus (http://localhost:9090/targets after port-forwarding `svc/kube-prometheus-stack-prometheus`). Look for the `orders-api` ServiceMonitor.
   - **Target missing:** the ServiceMonitor selector or the Service labels changed. They must both match `app.kubernetes.io/name: orders-api`, and the port name must be `http`.
   - **Target present but down:** read the scrape error. A NetworkPolicy change is the usual cause; ingress from the `monitoring` namespace must be allowed on port `http`.

## Resolved when

`up{job="orders-api"}` is 1 for every pod and the alert has cleared.

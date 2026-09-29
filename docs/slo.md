# SLOs for orders-api

## Availability

- **SLI:** requests to `/api/orders` that did not return a 5xx, divided by all requests to `/api/orders`, measured at the service from Prometheus metrics.
- **SLO:** 99.9% over a rolling 30 days.
- **Error budget:** 0.1% of requests, about 43 minutes of full outage per 30 days.

## Latency

- **SLI:** requests to `/api/orders` that completed in under 300ms (`le="0.3"` histogram bucket), divided by all requests.
- **SLO:** 99% over a rolling 30 days.

## Why multiwindow, multi-burn-rate alerts

Burn rate is how fast the budget is being spent relative to plan. A burn rate of 1 spends exactly the whole budget over 30 days. A burn rate of 14.4 spends 2% of the monthly budget in one hour.

| Severity | Long window | Short window | Burn rate | Budget spent when it fires | Why |
|---|---|---|---|---|---|
| page | 1h | 5m | 14.4x | 2% | A real outage. Fires in about 2 minutes at 100% errors. |
| page | 6h | 30m | 6x | 5% | A serious partial failure that the 1h window would miss. |
| ticket | 1d | 2h | 3x | 10% | A leak that needs fixing this week, not at 3am. |
| ticket | 3d | 6h | 1x | 10% | Slowly on track to miss the SLO. |

The long window stops short blips from paging. The short window makes the alert stop firing soon after the problem is fixed, instead of staying red for an hour while the long window catches up.

Compared with a plain threshold like "error rate above 1% for 5 minutes":

- **Precision:** a 5 minute spike to 2% on a 99.9% SLO spends a tiny share of the budget. The threshold pages for it; these alerts don't.
- **Recall:** a steady 0.4% error rate never crosses 1% but blows the budget in about 8 days. The threshold never fires; the 3x ticket does.
- **Reset time:** the 5m and 30m short windows clear the page within minutes of recovery.

Reference: Google SRE Workbook, chapter 5, "Alerting on SLOs".

## What happens when the budget runs out

This is policy rather than code, but it is what makes an SLO mean something:

1. Feature releases to orders-api pause until the 30 day budget is positive again.
2. Only reliability fixes and rollbacks ship.
3. Any single incident that spent more than 20% of the budget gets a written postmortem with owned action items.

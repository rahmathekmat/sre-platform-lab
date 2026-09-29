#!/usr/bin/env python3
"""End to end checks against a running cluster (kind in CI, or your own).

1. orders-api answers through its Service
2. Prometheus discovered and is scraping it (up == 1)
3. The SLO rule groups are loaded into Prometheus
4. Game day: inject 50% errors and confirm the fast burn alert goes pending or firing,
   then roll back and confirm the service recovers

Needs kubectl pointed at the cluster. Stdlib only.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager

NS_APP = "orders"
NS_MON = "monitoring"
PROM_SVC = "svc/kube-prometheus-stack-prometheus"


def log(msg: str) -> None:
    print(f"[e2e] {msg}", flush=True)


def kubectl(*args: str) -> str:
    return subprocess.run(["kubectl", *args], check=True, capture_output=True, text=True).stdout


@contextmanager
def port_forward(namespace: str, target: str, local: int, remote: int):
    proc = subprocess.Popen(
        ["kubectl", "-n", namespace, "port-forward", target, f"{local}:{remote}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for(
            lambda: http_get(f"http://127.0.0.1:{local}/")[0] > 0, 30, f"port-forward {target}"
        )
        yield f"http://127.0.0.1:{local}"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def http_get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        return 0, ""


def wait_for(check, timeout: int, what: str, interval: float = 5) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if check():
                log(f"ok: {what}")
                return
        except Exception as exc:  # keep polling through transient errors
            log(f"  retrying {what}: {exc}")
        time.sleep(interval)
    sys.exit(f"[e2e] FAILED after {timeout}s: {what}")


def prom_query(base: str, query: str) -> list[dict]:
    url = f"{base}/api/v1/query?" + urllib.parse.urlencode({"query": query})
    code, body = http_get(url)
    if code != 200:
        raise RuntimeError(f"query returned HTTP {code}")
    return json.loads(body)["data"]["result"]


def rule_groups(base: str) -> set[str]:
    code, body = http_get(f"{base}/api/v1/rules")
    if code != 200:
        return set()
    return {g["name"] for g in json.loads(body)["data"]["groups"]}


def set_error_rate(rate: str) -> None:
    kubectl("-n", NS_APP, "set", "env", "deployment/orders-api", f"FAULT_ERROR_RATE={rate}")
    kubectl("-n", NS_APP, "rollout", "status", "deployment/orders-api", "--timeout=180s")
    log(f"FAULT_ERROR_RATE={rate} rolled out")


def main() -> None:
    with port_forward(NS_APP, "svc/orders-api", 18080, 80) as app:
        code, body = http_get(f"{app}/api/orders")
        assert code == 200, f"/api/orders returned {code}"
        log("ok: /api/orders returns 200 through the Service")

    with port_forward(NS_MON, PROM_SVC, 19090, 9090) as prom:
        wait_for(
            lambda: any(s["value"][1] == "1" for s in prom_query(prom, 'up{job="orders-api"}')),
            240,
            "Prometheus is scraping orders-api",
        )
        wait_for(
            lambda: {"orders-api-slo.recording", "orders-api-slo.alerts"} <= rule_groups(prom),
            240,
            "SLO rule groups loaded",
        )

        log("game day: injecting 50% errors")
        set_error_rate("0.5")
        wait_for(
            lambda: bool(prom_query(prom, 'ALERTS{alertname="OrdersApiErrorBudgetBurnFast"}')),
            420,
            "OrdersApiErrorBudgetBurnFast is pending or firing",
            interval=10,
        )

        log("game day: rolling back")
        set_error_rate("0")
        time.sleep(10)  # let old pods finish draining so port-forward picks a new one

    with port_forward(NS_APP, "svc/orders-api", 18080, 80) as app:
        codes = [http_get(f"{app}/api/orders")[0] for _ in range(20)]
        assert codes.count(200) == 20, f"expected full recovery, got {codes}"
        log("ok: 20/20 requests succeed after rollback")

    log("all checks passed")


if __name__ == "__main__":
    main()

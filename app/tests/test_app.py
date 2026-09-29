import json
import random
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from orders_api.main import App, Config, make_handler


@pytest.fixture
def running():
    """Start a server on an ephemeral port and yield (app, base_url)."""
    servers = []

    def start(config: Config, seed: int = 0):
        app = App(config, rng=random.Random(seed))
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return app, f"http://127.0.0.1:{server.server_address[1]}"

    yield start
    for s in servers:
        s.shutdown()


def get(url: str, headers: dict | None = None) -> tuple[int, bytes]:
    return get_full(url, headers)[:2]


def get_full(url: str, headers: dict | None = None) -> tuple[int, bytes, dict]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def metric_value(metrics: str, name: str, labels: str) -> float:
    """Return a sample value, matching labels regardless of their order."""
    wanted = set(labels.split(","))
    for line in metrics.splitlines():
        if not line.startswith(f"{name}{{"):
            continue
        series, value = line.rsplit(" ", 1)
        present = set(series[len(name) + 1 : -1].split(","))
        if wanted <= present:
            return float(value)
    return 0.0


def test_orders_ok(running):
    _, base = running(Config())
    code, body = get(f"{base}/api/orders")
    assert code == 200
    assert json.loads(body)["orders"][0]["status"] == "shipped"


def test_health_endpoints(running):
    _, base = running(Config())
    assert get(f"{base}/healthz")[0] == 200
    assert get(f"{base}/readyz")[0] == 200


def test_readiness_fails_while_draining(running):
    app, base = running(Config())
    app.ready.clear()
    code, body = get(f"{base}/readyz")
    assert code == 503
    assert json.loads(body) == {"ready": False}
    # liveness must stay green while draining, or the kubelet would kill the pod early
    assert get(f"{base}/healthz")[0] == 200


def test_unknown_route_is_404_and_bounded_cardinality(running):
    _, base = running(Config())
    for path in ("/nope", "/also/nope", "/x?y=1"):
        assert get(f"{base}{path}")[0] == 404
    metrics = get(f"{base}/metrics")[1].decode()
    # arbitrary paths collapse into one label value instead of exploding series count
    assert metric_value(metrics, "http_requests_total", 'route="unmatched",code="404"') == 3


def test_request_metrics_recorded(running):
    _, base = running(Config())
    for _ in range(5):
        get(f"{base}/api/orders")
    metrics = get(f"{base}/metrics")[1].decode()
    assert metric_value(metrics, "http_requests_total", 'route="/api/orders",code="200"') == 5
    assert metric_value(metrics, "http_request_duration_seconds_count", 'route="/api/orders"') == 5
    assert 'orders_api_build_info{version="dev"} 1.0' in metrics


def test_fault_injection_full_error_rate(running):
    _, base = running(Config(error_rate=1.0))
    codes = [get(f"{base}/api/orders")[0] for _ in range(10)]
    assert codes == [500] * 10
    metrics = get(f"{base}/metrics")[1].decode()
    assert metric_value(metrics, "http_requests_total", 'route="/api/orders",code="500"') == 10


def test_fault_injection_partial_error_rate(running):
    _, base = running(Config(error_rate=0.3), seed=42)
    codes = [get(f"{base}/api/orders")[0] for _ in range(200)]
    errors = codes.count(500) / len(codes)
    assert 0.15 < errors < 0.45


def test_injected_latency_lands_in_histogram(running):
    _, base = running(Config(latency_ms=350))
    get(f"{base}/api/orders")
    metrics = get(f"{base}/metrics")[1].decode()
    # 350ms of injected latency must fall outside the 300ms SLO bucket
    le_03 = metric_value(
        metrics, "http_request_duration_seconds_bucket", 'le="0.3",route="/api/orders"'
    )
    assert le_03 == 0


@pytest.mark.parametrize("value", ["-0.1", "1.5"])
def test_config_rejects_bad_error_rate(monkeypatch, value):
    monkeypatch.setenv("FAULT_ERROR_RATE", value)
    with pytest.raises(ValueError):
        Config.from_env()


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("FAULT_ERROR_RATE", "0.05")
    monkeypatch.setenv("FAULT_LATENCY_MS", "200")
    monkeypatch.setenv("PORT", "9090")
    cfg = Config.from_env()
    assert (cfg.error_rate, cfg.latency_ms, cfg.port) == (0.05, 200, 9090)


def test_request_id_is_minted_and_echoed(running):
    _, base = running(Config())
    _, _, headers = get_full(f"{base}/api/orders")
    minted = headers["X-Request-ID"]
    assert len(minted) == 16
    _, _, headers = get_full(f"{base}/api/orders", {"X-Request-ID": "abc-123"})
    assert headers["X-Request-ID"] == "abc-123"


def test_errors_are_logged_with_request_id(running, caplog):
    _, base = running(Config(error_rate=1.0))
    with caplog.at_level("WARNING", logger="orders_api"):
        get(f"{base}/api/orders", {"X-Request-ID": "trace-me"})
    messages = [r.getMessage() for r in caplog.records]
    assert any("code=500" in m and "request_id=trace-me" in m for m in messages)

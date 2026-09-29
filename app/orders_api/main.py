"""orders-api: a small HTTP service instrumented for SLO-based alerting.

Endpoints
  GET /api/orders  simulated business endpoint (the thing the SLO covers)
  GET /healthz     liveness: the process is up and serving
  GET /readyz      readiness: returns 503 while draining on SIGTERM
  GET /metrics     Prometheus exposition format

Fault injection (for game days), read from the environment at startup:
  FAULT_ERROR_RATE   fraction of /api/orders requests that return 500 (0.0 to 1.0)
  FAULT_LATENCY_MS   extra latency added to every /api/orders request
"""

from __future__ import annotations

import json
import logging
import os
import random
import signal
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

VERSION = os.environ.get("APP_VERSION", "dev")
LATENCY_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.5, 5.0)

log = logging.getLogger("orders_api")


@dataclass(frozen=True)
class Config:
    port: int = 8080
    error_rate: float = 0.0
    latency_ms: int = 0
    drain_seconds: float = 5.0

    @classmethod
    def from_env(cls) -> Config:
        error_rate = float(os.environ.get("FAULT_ERROR_RATE", "0"))
        if not 0.0 <= error_rate <= 1.0:
            raise ValueError("FAULT_ERROR_RATE must be between 0 and 1")
        return cls(
            port=int(os.environ.get("PORT", "8080")),
            error_rate=error_rate,
            latency_ms=max(0, int(os.environ.get("FAULT_LATENCY_MS", "0"))),
            drain_seconds=float(os.environ.get("DRAIN_SECONDS", "5")),
        )


class Metrics:
    def __init__(self, registry: CollectorRegistry) -> None:
        self.requests = Counter(
            "http_requests",
            "HTTP requests by route and status code.",
            ["route", "code"],
            registry=registry,
        )
        self.latency = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency by route.",
            ["route"],
            buckets=LATENCY_BUCKETS,
            registry=registry,
        )
        self.in_flight = Gauge(
            "http_requests_in_flight", "Requests currently being served.", registry=registry
        )
        self.build_info = Gauge(
            "orders_api_build_info", "Build metadata.", ["version"], registry=registry
        )
        self.build_info.labels(version=VERSION).set(1)


class App:
    """Holds state shared by all request handler threads."""

    def __init__(self, config: Config, rng: random.Random | None = None) -> None:
        self.config = config
        self.registry = CollectorRegistry()
        self.metrics = Metrics(self.registry)
        self.ready = threading.Event()
        self.ready.set()
        self._rng = rng or random.Random()

    def orders(self) -> tuple[int, dict]:
        if self.config.latency_ms:
            time.sleep(self.config.latency_ms / 1000)
        time.sleep(self._rng.uniform(0.005, 0.03))  # simulated downstream call
        if self._rng.random() < self.config.error_rate:
            return 500, {"error": "injected fault"}
        return 200, {"orders": [{"id": 1, "status": "shipped"}], "version": VERSION}


def make_handler(app: App) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = f"orders-api/{VERSION}"

        def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
            path = self.path.split("?", 1)[0]
            if path == "/metrics":
                self._send(200, generate_latest(app.registry), CONTENT_TYPE_LATEST)
                return
            if path == "/healthz":
                self._json(200, {"status": "ok"})
                return
            if path == "/readyz":
                ok = app.ready.is_set()
                self._json(200 if ok else 503, {"ready": ok})
                return
            if path == "/api/orders":
                self._instrumented("/api/orders", app.orders)
                return
            self._instrumented("unmatched", lambda: (404, {"error": "not found"}))

        def _instrumented(self, route: str, fn) -> None:
            app.metrics.in_flight.inc()
            start = time.perf_counter()
            try:
                code, body = fn()
            except Exception:  # pragma: no cover - defensive
                log.exception("unhandled error on %s", route)
                code, body = 500, {"error": "internal"}
            finally:
                app.metrics.in_flight.dec()
            app.metrics.latency.labels(route=route).observe(time.perf_counter() - start)
            app.metrics.requests.labels(route=route, code=str(code)).inc()
            self._json(code, body)

        def _json(self, code: int, body: dict) -> None:
            self._send(code, json.dumps(body).encode(), "application/json")

        def _send(self, code: int, payload: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt: str, *args) -> None:
            log.debug("%s %s", self.address_string(), fmt % args)

    return Handler


def serve(config: Config) -> None:
    app = App(config)
    server = ThreadingHTTPServer(("0.0.0.0", config.port), make_handler(app))

    def drain(signum, _frame) -> None:
        # Fail readiness first so the Service stops routing new traffic here,
        # give endpoints time to update, then stop accepting connections.
        log.info("signal %s received, draining for %.1fs", signum, config.drain_seconds)
        app.ready.clear()

        def stop() -> None:
            time.sleep(config.drain_seconds)
            server.shutdown()

        threading.Thread(target=stop, daemon=True).start()

    signal.signal(signal.SIGTERM, drain)
    signal.signal(signal.SIGINT, drain)
    log.info("orders-api %s listening on :%d (config=%s)", VERSION, config.port, config)
    server.serve_forever()
    log.info("shutdown complete")


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
    )
    serve(Config.from_env())


if __name__ == "__main__":
    main()

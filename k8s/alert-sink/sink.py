"""alert-sink: a webhook receiver that records what Alertmanager delivers.

Stands in for PagerDuty / a ticket queue in the local cluster and in CI, so the
end to end test can prove a page was actually *delivered*, not just evaluated.

  POST /alerts?severity=page   Alertmanager webhook (stores the payload)
  GET  /alerts                 everything received so far, as JSON
  GET  /healthz
"""

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

log = logging.getLogger("alert_sink")
received: list[dict] = []
lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path != "/alerts":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        receiver = parse_qs(url.query).get("severity", ["unknown"])[0]
        entry = {"received_at": time.time(), "receiver": receiver, "payload": payload}
        with lock:
            received.append(entry)
        for alert in payload.get("alerts", []):
            log.info(
                "receiver=%s status=%s alert=%s",
                receiver,
                alert.get("status"),
                alert.get("labels", {}).get("alertname"),
            )
        self._json(200, {"ok": True})

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/healthz":
            self._json(200, {"status": "ok"})
        elif path == "/alerts":
            with lock:
                self._json(200, received)
        else:
            self._json(404, {"error": "not found"})

    def _json(self, code: int, body) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        log.debug(fmt, *args)


if __name__ == "__main__":
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(message)s")
    log.info("alert-sink listening on :8080")
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()

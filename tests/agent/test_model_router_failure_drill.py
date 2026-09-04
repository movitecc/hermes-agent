import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import Request, urlopen

from agent.model_router.health import HealthConfig, RouterHealthStore


class _FailureThenSuccess(BaseHTTPRequestHandler):
    responses = [503, 200]

    def do_POST(self):
        status = self.responses.pop(0)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": status == 200}).encode())

    def log_message(self, *_args):
        pass


def test_isolated_provider_failure_drill_records_open_and_recovers(tmp_path):
    server = HTTPServer(("127.0.0.1", 0), _FailureThenSuccess)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    store = RouterHealthStore(tmp_path / "router.db", HealthConfig(failure_threshold=1))
    url = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
    try:
        try:
            urlopen(Request(url, data=b"{}", method="POST"), timeout=2)
        except Exception:
            store.record_outcome("local-drill", "primary", status_code=503, retryable=True, reason="server_error")
        assert store.snapshot("local-drill", "primary").state == "open"
        response = urlopen(Request(url, data=b"{}", method="POST"), timeout=2)
        assert response.status == 200
        store.record_outcome("local-drill", "primary", success=True)
        assert store.snapshot("local-drill", "primary").state == "closed"
    finally:
        server.shutdown()
        thread.join(timeout=2)

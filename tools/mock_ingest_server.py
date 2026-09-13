#!/usr/bin/env python3
"""
Minimal mock implementation of POST /v1/ingest/batch (docs/TIMEOS_ENGINEERING_SPEC.md §12.3),
used to manually verify the Phase 2 Android sync client end-to-end without a real backend
(Phase 3 hasn't been built yet).

stdlib-only, no dependencies. Implements the two properties the client actually depends on:
  - idempotent replay by batch_id (Idempotency-Key header / batch_id in the body)
  - configurable forced status codes, to exercise the retry vs quarantine paths

Usage:
    python3 tools/mock_ingest_server.py [--port 8089]

Then, with a device connected via adb:
    adb reverse tcp:8089 tcp:8089

...and set the app's Server URL (on the diagnostic screen) to http://127.0.0.1:8089 — the
adb reverse tunnel works over USB regardless of the phone's WiFi/cellular state, which is what
makes it possible to test "server unreachable" by simply killing this process rather than
fiddling with the phone's radios (already validated not to matter for collection in Phase 1B).

Control endpoints (for testing retry/quarantine):
    curl -X POST 'http://127.0.0.1:8089/_control/force?code=500&count=1'
    curl -X POST 'http://127.0.0.1:8089/_control/force?code=422&count=1'
    curl -X POST 'http://127.0.0.1:8089/_control/clear'
    curl 'http://127.0.0.1:8089/_control/batches'   # list every batch_id received, for eyeballing
"""

from __future__ import annotations

import argparse
import gzip
import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

_lock = threading.Lock()
_batches: dict[str, dict] = {}  # batch_id -> stored response body
_received_order: list[str] = []  # batch_ids in arrival order, for /_control/batches
_forced_status: int | None = None
_forced_remaining = 0


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "TimeOSMockIngest/0.1"

    def log_message(self, format, *args):  # noqa: A002 - silence default noisy logging
        pass

    def _send_json(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/v1/health":
            self._send_json(200, {"status": "ok"})
            return
        if parsed.path == "/_control/batches":
            with _lock:
                self._send_json(200, {"batches": _received_order, "count": len(_received_order)})
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        global _forced_status, _forced_remaining
        parsed = urlparse(self.path)

        if parsed.path == "/_control/force":
            qs = parse_qs(parsed.query)
            code = int(qs.get("code", ["500"])[0])
            count = int(qs.get("count", ["1"])[0])
            with _lock:
                _forced_status = code
                _forced_remaining = count
            _log(f"CONTROL: forcing status {code} for next {count} request(s)")
            self._send_json(200, {"forced_status": code, "count": count})
            return

        if parsed.path == "/_control/clear":
            with _lock:
                _forced_status = None
                _forced_remaining = 0
                _batches.clear()
                _received_order.clear()
            _log("CONTROL: cleared forced status and batch history")
            self._send_json(200, {"cleared": True})
            return

        if parsed.path != "/v1/ingest/batch":
            self._send_json(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if self.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)

        try:
            request = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            _log(f"REJECT: malformed body ({e})")
            self._send_json(422, {"error": f"malformed json: {e}"})
            return

        batch_id = request.get("batch_id")
        events = request.get("events", [])
        auth = self.headers.get("Authorization", "")

        with _lock:
            forced = None
            if _forced_status is not None and _forced_remaining > 0:
                forced = _forced_status
                _forced_remaining -= 1
                if _forced_remaining == 0:
                    _forced_status = None

            if forced is not None:
                _log(
                    f"BATCH {batch_id}: {len(events)} events, auth={auth[:20]!r} "
                    f"-> FORCED {forced}",
                )
                if forced >= 500:
                    self._send_json(forced, {"error": "forced server error"})
                elif forced == 429:
                    self.send_response(429)
                    self.send_header("Retry-After", "5")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                else:
                    self._send_json(forced, {"error": "forced client error", "detail": "test-forced"})
                return

            # Idempotent replay: a batch_id we've already accepted returns the SAME stored
            # response, per §12.3 point 1 — this is the exact property the client's retry logic
            # depends on being safe.
            if batch_id in _batches:
                _log(f"BATCH {batch_id}: REPLAY (already processed) -> 200")
                self._send_json(200, _batches[batch_id])
                return

            if not batch_id or not request.get("device_id") or not events:
                _log(f"REJECT: missing required fields in batch {batch_id}")
                self._send_json(422, {"error": "missing required fields"})
                return

            seq_to = request.get("seq_to", 0)
            response = {
                "accepted": len(events),
                "duplicates": 0,
                "batch_id": batch_id,
                "server_seq": seq_to,
                "next_expected_seq": seq_to + 1,
            }
            _batches[batch_id] = response
            _received_order.append(batch_id)
            _log(
                f"BATCH {batch_id}: {len(events)} events, seq {request.get('seq_from')}-{seq_to}, "
                f"auth={auth[:20]!r} -> 200 accepted",
            )
            self._send_json(200, response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8089)
    args = parser.parse_args()

    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    _log(f"Mock ingest server listening on 0.0.0.0:{args.port}")
    _log("Run: adb reverse tcp:%d tcp:%d" % (args.port, args.port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _log("Shutting down")


if __name__ == "__main__":
    main()

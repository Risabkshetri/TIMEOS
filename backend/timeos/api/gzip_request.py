"""Decompresses gzip-encoded REQUEST bodies.

Starlette's GZipMiddleware only compresses responses — it does nothing for a client that sends a
gzip-compressed request body, which is exactly what the Android sync client always does
(android/core/sync/OkHttpIngestApiClient.kt sets Content-Encoding: gzip on every batch upload,
per docs/TIMEOS_ENGINEERING_SPEC.md §26/§12.3). Without this, FastAPI's automatic Pydantic body
parsing tries to JSON-decode raw gzip bytes and fails with a generic 400, not a helpful error.
"""

import gzip

from starlette.types import ASGIApp, Receive, Scope, Send


class GZipRequestMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_encoding = headers.get(b"content-encoding", b"").decode("latin-1")
        if "gzip" not in content_encoding:
            await self.app(scope, receive, send)
            return

        body_chunks = []
        more_body = True
        while more_body:
            message = await receive()
            body_chunks.append(message.get("body", b""))
            more_body = message.get("more_body", False)
        compressed_body = b"".join(body_chunks)

        try:
            decompressed_body = gzip.decompress(compressed_body)
        except OSError:
            # Not actually valid gzip despite the header — let the real handler's JSON/schema
            # validation produce the error, rather than this middleware masking it differently.
            decompressed_body = compressed_body

        sent = False

        async def receive_decompressed() -> dict:
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": decompressed_body, "more_body": False}

        await self.app(scope, receive_decompressed, send)

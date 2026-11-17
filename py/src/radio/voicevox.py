"""VOICEVOX Engine client (external server).

Design decision (2026-11-17): synthesis is the ONLY part delegated to an
external server. Scripts, scheduling, AzuraCast and the audio storage all
live on the user's own host; this module just calls the engine over HTTP.

- Host comes from env VOICEVOX_HOST (e.g. http://192.168.x.x:50021),
  default http://localhost:50021 (same name as the original env.php).
- A single http.client connection is reused: a long program needs
  hundreds of audio_query/synthesis round trips, so per-line reconnects
  to a remote host would add up.
- Timeouts are mandatory (see STRUCTURE.md #3).
"""
from __future__ import annotations

import http.client
import json
import os
import urllib.parse

DEFAULT_HOST = "http://localhost:50021"
CONNECT_TIMEOUT = 10
SYNTH_TIMEOUT = 120  # synthesis of a long line can take a while


def host_from_env() -> str:
    return os.environ.get("VOICEVOX_HOST", DEFAULT_HOST).rstrip("/")


class VoiceVoxClient:
    def __init__(self, host: str | None = None):
        self.base = urllib.parse.urlparse(host or host_from_env())
        self._conn: http.client.HTTPConnection | None = None

    def _connection(self) -> http.client.HTTPConnection:
        if self._conn is None:
            self._conn = http.client.HTTPConnection(
                self.base.hostname, self.base.port or 80, timeout=SYNTH_TIMEOUT
            )
        return self._conn

    def _request(self, method: str, path: str, body: bytes | None = None,
                 content_type: str | None = None) -> bytes:
        headers = {"Content-Type": content_type} if content_type else {}
        for attempt in range(2):
            try:
                conn = self._connection()
                conn.request(method, path, body=body, headers=headers)
                resp = conn.getresponse()
                data = resp.read()
                if resp.status != 200:
                    raise RuntimeError(f"VOICEVOX {path} -> HTTP {resp.status}: {data[:200]!r}")
                return data
            except (http.client.HTTPException, ConnectionError, OSError):
                self.close()
                if attempt == 1:
                    raise
        raise RuntimeError("unreachable")

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None

    def __enter__(self) -> "VoiceVoxClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # --- Engine API ---
    def version(self) -> str:
        return self._request("GET", "/version").decode("utf-8").strip().strip('"')

    def speakers(self) -> list[dict]:
        return json.loads(self._request("GET", "/speakers"))

    def synthesize_line(self, text: str, speaker: int) -> bytes:
        """One line of dialogue -> WAV bytes (audio_query + synthesis)."""
        q = urllib.parse.urlencode({"text": text, "speaker": speaker})
        query = self._request("POST", f"/audio_query?{q}", body=b"")
        q2 = urllib.parse.urlencode({"speaker": speaker})
        return self._request(
            "POST", f"/synthesis?{q2}", body=query,
            content_type="application/json",
        )

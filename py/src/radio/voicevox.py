"""VOICEVOX Engine client (external server, with fallback).

Design decision (2026-11-17): synthesis is the ONLY part delegated to an
external server. Scripts, scheduling, AzuraCast and the audio storage all
live on the user's own host; this module just calls the engine over HTTP.

- Host comes from env VOICEVOX_HOST (e.g. http://192.168.x.x:50021),
  default http://localhost:50021 (same name as the original env.php).
- A single http.client connection is reused: a long program needs
  hundreds of audio_query/synthesis round trips, so per-line reconnects
  to a remote host would add up.
- Timeouts are mandatory (see STRUCTURE.md #3).

Fallback (added 2026-11-19, after the enoki server outage):
- env VOICEVOX_HOST_FALLBACK names a second engine (the self-hosted CPU
  engine on op3060m, http://192.168.108.200:50021). The external GPU
  engine stays primary; the local CPU engine is the backup.
- Before the first request of a process, the primary is probed with a
  short timeout (PROBE_TIMEOUT). If it does not answer, the whole
  process sticks to the fallback. Jobs are spawned per run by the
  scheduler, so the next job automatically re-checks the primary and
  returns to it once it is back - no state file, no manual switch.
- If the primary dies mid-job, the failed request is retried once on
  the fallback and the rest of the job stays there. Lines already
  synthesized are kept (same speakers; engine version may differ
  slightly, 0.25.x vs 0.26.x, which is inaudible in practice).
- HTTP error responses (non-200) do NOT trigger failover: the engine
  is alive, and switching would only mask a real error.
- HTTP 5xx responses are retried on the same host (waits in
  STATUS_RETRY_WAITS): a single transient 500 used to kill a whole
  159-line synthesis (2026-11-20, gadget 12:00 slot). 4xx is not
  retried; it would fail again deterministically.
- Engaging the fallback prints a "VOICEVOX FALLBACK" line so it shows
  up in scheduler logs and in the Discord success/failure summaries.
"""
from __future__ import annotations

import http.client
import json
import os
import time
import urllib.parse

DEFAULT_HOST = "http://localhost:50021"
CONNECT_TIMEOUT = 10
SYNTH_TIMEOUT = 120  # synthesis of a long line can take a while
PROBE_TIMEOUT = 5    # primary reachability check before the first request
STATUS_RETRY_WAITS = [2, 5, 10]  # waits before HTTP 5xx retries (seconds)


def host_from_env() -> str:
    return os.environ.get("VOICEVOX_HOST", DEFAULT_HOST).rstrip("/")


def fallback_from_env() -> str | None:
    value = os.environ.get("VOICEVOX_HOST_FALLBACK", "").strip().rstrip("/")
    return value or None


class VoiceVoxClient:
    def __init__(self, host: str | None = None,
                 fallback: str | None = None):
        primary = (host or host_from_env()).rstrip("/")
        fb = fallback if fallback is not None else fallback_from_env()
        self._hosts = [primary]
        if fb and fb.rstrip("/") != primary:
            self._hosts.append(fb.rstrip("/"))
        self._host_idx = 0
        self.base = urllib.parse.urlparse(self._hosts[0])
        self._conn: http.client.HTTPConnection | None = None
        self._probed = False

    @property
    def using_fallback(self) -> bool:
        return self._host_idx > 0

    def _switch_to_fallback(self, reason: str) -> bool:
        """Move to the fallback host. Returns False if none is left."""
        if self._host_idx + 1 >= len(self._hosts):
            return False
        old = self._hosts[self._host_idx]
        self._host_idx += 1
        self.close()
        self.base = urllib.parse.urlparse(self._hosts[self._host_idx])
        print(f"VOICEVOX FALLBACK: {old} unreachable ({reason}); "
              f"using {self._hosts[self._host_idx]}", flush=True)
        return True

    def _probe_primary(self) -> None:
        """One short-timeout /version check, run before the first request."""
        self._probed = True
        if len(self._hosts) < 2:
            return
        conn = http.client.HTTPConnection(
            self.base.hostname, self.base.port or 80, timeout=PROBE_TIMEOUT)
        try:
            conn.request("GET", "/version")
            resp = conn.getresponse()
            resp.read()
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
        except Exception as exc:
            self._switch_to_fallback(f"probe: {exc}")
        finally:
            conn.close()

    def _connection(self) -> http.client.HTTPConnection:
        if self._conn is None:
            self._conn = http.client.HTTPConnection(
                self.base.hostname, self.base.port or 80, timeout=SYNTH_TIMEOUT
            )
        return self._conn

    def _request(self, method: str, path: str, body: bytes | None = None,
                 content_type: str | None = None) -> bytes:
        if not self._probed:
            self._probe_primary()
        headers = {"Content-Type": content_type} if content_type else {}
        while True:
            try:
                return self._request_once(method, path, body, headers)
            except (http.client.HTTPException, ConnectionError, OSError) as exc:
                if not self._switch_to_fallback(str(exc)):
                    raise

    def _request_once(self, method: str, path: str, body: bytes | None,
                      headers: dict) -> bytes:
        status_attempt = 0
        while True:
            for attempt in range(2):
                try:
                    conn = self._connection()
                    conn.request(method, path, body=body, headers=headers)
                    resp = conn.getresponse()
                    data = resp.read()
                    break
                except (http.client.HTTPException, ConnectionError,
                        OSError):
                    self.close()
                    if attempt == 1:
                        raise
            if resp.status == 200:
                return data
            if (500 <= resp.status < 600
                    and status_attempt < len(STATUS_RETRY_WAITS)):
                wait = STATUS_RETRY_WAITS[status_attempt]
                status_attempt += 1
                print(f"VOICEVOX {path} -> HTTP {resp.status}: "
                      f"retry {status_attempt}/{len(STATUS_RETRY_WAITS)} "
                      f"in {wait}s", flush=True)
                self.close()
                time.sleep(wait)
                continue
            raise RuntimeError(
                f"VOICEVOX {path} -> HTTP {resp.status}: {data[:200]!r}")

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

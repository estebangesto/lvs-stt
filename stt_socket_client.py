#!/usr/bin/env python3
"""Small test client for LVS STT socket activation.

Usage:
  python3 stt_socket_client.py /path/to/audio.ogg
  python3 stt_socket_client.py /path/to/audio.ogg --json
  python3 stt_socket_client.py /path/to/audio.ogg --socket "$XDG_RUNTIME_DIR/lvs-stt.sock"

It sends a single JSON request to the Unix socket and prints the response.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path
from typing import Optional


def default_socket_candidates() -> list[str]:
    candidates = []
    runtime_dir = os.getenv("XDG_RUNTIME_DIR")
    if runtime_dir:
        candidates.append(os.path.join(runtime_dir, "lvs-stt.sock"))
    candidates.append("/tmp/lvs-stt.sock")
    return candidates


def resolve_socket_path(explicit: Optional[str]) -> str:
    if explicit:
        return explicit
    for candidate in default_socket_candidates():
        if Path(candidate).exists():
            return candidate
    return default_socket_candidates()[0]


def send_request(sock_path: str, audio_path: str, timeout: float, language: str, prompt: Optional[str], beam_size: int, vad_filter: Optional[bool]) -> dict:
    payload = {
        "path": str(Path(audio_path).expanduser().resolve()),
        "language": language,
        "beam_size": beam_size,
    }
    if prompt is not None:
        payload["prompt"] = prompt
    if vad_filter is not None:
        payload["vad_filter"] = vad_filter

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(sock_path)
        s.sendall((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))

        buf = bytearray()
        while not buf.endswith(b"\n"):
            chunk = s.recv(4096)
            if not chunk:
                break
            buf.extend(chunk)

    raw = buf.decode("utf-8", errors="replace").strip()
    if not raw:
        raise RuntimeError("empty response from STT socket")
    return json.loads(raw)


def main() -> int:
    p = argparse.ArgumentParser(description="Test client for LVS STT socket")
    p.add_argument("audio", help="Audio file path")
    p.add_argument("--socket", help="Unix socket path")
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("--language", default="es")
    p.add_argument("--prompt", default=None)
    p.add_argument("--beam-size", type=int, default=1)
    p.add_argument("--vad-filter", action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--json", action="store_true", help="Print raw JSON")
    args = p.parse_args()

    sock_path = resolve_socket_path(args.socket)
    response = send_request(
        sock_path=sock_path,
        audio_path=args.audio,
        timeout=args.timeout,
        language=args.language,
        prompt=args.prompt,
        beam_size=args.beam_size,
        vad_filter=args.vad_filter,
    )

    if args.json:
        print(json.dumps(response, ensure_ascii=False, indent=2))
        return 0

    if "error" in response:
        print(f"ERROR: {response['error']}", file=sys.stderr)
        return 1

    print(response.get("text", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

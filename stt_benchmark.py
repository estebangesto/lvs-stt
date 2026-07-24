#!/usr/bin/env python3
"""Benchmark STT latency for the current Whisper script or the fast worker.

Usage:
  python3 stt_benchmark.py --file audio.ogg
  python3 stt_benchmark.py --file audio.ogg --repeats 3 --backend fast-once
  python3 stt_benchmark.py --file audio.ogg --backend current
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent
CURRENT = ROOT / "transcribe_whisper.py"
FAST = ROOT / "transcribe_whisper_fast.py"
DEFAULT_SOCKET = Path("/tmp/lucia-stt.sock")


def run_current(audio: str) -> tuple[float, str]:
    start = time.perf_counter()
    cp = subprocess.run([sys.executable, str(CURRENT), audio], capture_output=True, text=True)
    elapsed = time.perf_counter() - start
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.strip() or cp.stdout.strip())
    return elapsed, cp.stdout.strip()


def run_fast_once(audio: str, backend: str, model: str, device: str, compute_type: str) -> tuple[float, str]:
    cmd = [sys.executable, str(FAST), "--once", "--json", "--backend", backend, "--model", model, "--device", device, "--compute-type", compute_type, audio]
    start = time.perf_counter()
    cp = subprocess.run(cmd, capture_output=True, text=True)
    elapsed = time.perf_counter() - start
    if cp.returncode != 0:
        raise RuntimeError(cp.stderr.strip() or cp.stdout.strip())
    data = json.loads(cp.stdout)
    return elapsed, data.get("text", "")


def run_fast_socket(audio: str, sock: str) -> tuple[float, str]:
    start = time.perf_counter()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(sock)
        s.sendall((json.dumps({"path": audio}) + "\n").encode("utf-8"))
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(4096)
            if not chunk:
                break
            buf += chunk
    elapsed = time.perf_counter() - start
    data = json.loads(buf.decode("utf-8"))
    if "error" in data:
        raise RuntimeError(data["error"])
    return elapsed, data.get("text", "")


def main() -> int:
    p = argparse.ArgumentParser(description="Benchmark STT modes")
    p.add_argument("--file", required=True, help="Audio file path")
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument("--backend", choices=["current", "fast-once", "fast-socket"], default="fast-once")
    p.add_argument("--model", default=os.getenv("STT_MODEL", "small"))
    p.add_argument("--device", default=os.getenv("STT_DEVICE", "auto"))
    p.add_argument("--compute-type", default=os.getenv("STT_COMPUTE_TYPE", ""))
    p.add_argument("--socket", default=str(DEFAULT_SOCKET))
    args = p.parse_args()

    times = []
    for i in range(args.repeats):
        if args.backend == "current":
            t, text = run_current(args.file)
        elif args.backend == "fast-socket":
            t, text = run_fast_socket(args.file, args.socket)
        else:
            t, text = run_fast_once(args.file, backend="faster-whisper", model=args.model, device=args.device, compute_type=args.compute_type)
        times.append(t)
        print(f"run {i+1}: {t:.3f}s | {text[:80]}")

    print("---")
    print(f"avg: {mean(times):.3f}s")
    print(f"min: {min(times):.3f}s")
    print(f"max: {max(times):.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

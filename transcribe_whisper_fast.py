#!/usr/bin/env python3
"""Fast, reusable STT worker for OpenClaw audio.

Goals:
- keep the model warm in a long-lived process
- prefer faster-whisper when available
- fall back to openai-whisper if needed
- keep config external so OpenClaw can be switched later without touching it now

Modes:
- one-shot CLI:   python3 transcribe_whisper_fast.py --once path/to/audio.ogg
- JSON output:    python3 transcribe_whisper_fast.py --once --json path/to/audio.ogg
- daemon socket:  python3 transcribe_whisper_fast.py --serve --socket /tmp/lvs-stt.sock

Protocol for the daemon:
- client connects to the Unix socket
- sends one JSON line: {"path": "/abs/audio.ogg", "language": "es"}
- server responds with one JSON line containing the transcript + stats

Environment variables:
- STT_BACKEND=faster-whisper|whisper (default: faster-whisper)
- STT_MODEL=small|medium|large-v3|... (default: small)
- STT_DEVICE=auto|cpu|cuda (default: auto)
- STT_COMPUTE_TYPE=int8|float16|... (default: int8 on cpu, float16 on cuda)
- STT_LANGUAGE=es (default: es)
- STT_PROMPT=... initial prompt text
- STT_BEAM_SIZE=1 (default: 1)
- STT_VAD=1 (default: 1)
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import socketserver
import sys
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ---------- Config ----------
DEFAULT_LANGUAGE = os.getenv("STT_LANGUAGE", "es")
DEFAULT_MODEL = os.getenv("STT_MODEL", "small")
DEFAULT_BACKEND = os.getenv("STT_BACKEND", "faster-whisper")
DEFAULT_DEVICE = os.getenv("STT_DEVICE", "auto")
DEFAULT_COMPUTE_TYPE = os.getenv("STT_COMPUTE_TYPE", "")
DEFAULT_BEAM_SIZE = int(os.getenv("STT_BEAM_SIZE", "1"))
DEFAULT_VAD = os.getenv("STT_VAD", "1") not in {"0", "false", "False", "no", "NO"}
DEFAULT_PROMPT_ENV = os.getenv("STT_PROMPT", "")
DEFAULT_SOCKET = os.getenv("STT_SOCKET_PATH", "/tmp/lvs-stt.sock")
DEFAULT_SOCKET_TIMEOUT = float(os.getenv("STT_SOCKET_TIMEOUT", "30"))


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "f", "no", "n", "off"}:
            return False
    return default


@dataclass
class TranscriptResult:
    text: str
    backend: str
    model: str
    device: str
    compute_type: str
    seconds: float
    language: str
    file_path: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "backend": self.backend,
            "model": self.model,
            "device": self.device,
            "compute_type": self.compute_type,
            "seconds": round(self.seconds, 3),
            "language": self.language,
            "file_path": self.file_path,
        }


class STTWorker:
    def __init__(self, backend: str = DEFAULT_BACKEND, model: str = DEFAULT_MODEL, device: str = DEFAULT_DEVICE, compute_type: str = DEFAULT_COMPUTE_TYPE):
        self.backend = backend
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self._model = None
        self._backend_name = None
        self._load_model()

    def _load_model(self) -> None:
        if self.backend == "faster-whisper":
            try:
                from faster_whisper import WhisperModel  # type: ignore
            except Exception as e:
                raise RuntimeError(
                    "faster-whisper no está disponible. Instala `faster-whisper` o usa STT_BACKEND=whisper."
                ) from e

            device = self.device if self.device != "auto" else ("cuda" if _cuda_available() else "cpu")
            compute_type = self.compute_type or ("float16" if device == "cuda" else "int8")
            self._model = WhisperModel(self.model_name, device=device, compute_type=compute_type)
            self.device = device
            self.compute_type = compute_type
            self._backend_name = "faster-whisper"
            return

        if self.backend == "whisper":
            try:
                import whisper  # type: ignore
            except Exception as e:
                raise RuntimeError(
                    "openai-whisper no está disponible. Instala `openai-whisper` o usa STT_BACKEND=faster-whisper."
                ) from e

            try:
                import torch  # type: ignore
            except Exception as e:
                raise RuntimeError("torch no está disponible, necesario para openai-whisper") from e

            device = self.device if self.device != "auto" else ("cuda" if torch.cuda.is_available() else "cpu")
            self._model = whisper.load_model(self.model_name, device=device)
            self.device = device
            self.compute_type = "n/a"
            self._backend_name = "whisper"
            return

        raise ValueError(f"Backend STT desconocido: {self.backend}")

    def transcribe(self, file_path: str, language: str = DEFAULT_LANGUAGE, prompt: str = DEFAULT_PROMPT_ENV, beam_size: int = DEFAULT_BEAM_SIZE, vad_filter: bool = DEFAULT_VAD) -> TranscriptResult:
        audio_path = Path(file_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        if not audio_path.is_file():
            raise IsADirectoryError(f"Audio path is not a file: {audio_path}")

        started = time.perf_counter()
        if self._backend_name == "faster-whisper":
            segments, info = self._model.transcribe(  # type: ignore[union-attr]
                str(audio_path),
                language=language,
                initial_prompt=prompt,
                beam_size=beam_size,
                vad_filter=vad_filter,
            )
            text = "".join(seg.text for seg in segments).strip()
            elapsed = time.perf_counter() - started
            return TranscriptResult(
                text=text,
                backend=self._backend_name,
                model=self.model_name,
                device=self.device,
                compute_type=self.compute_type,
                seconds=elapsed,
                language=getattr(info, "language", language),
                file_path=file_path,
            )

        result = self._model.transcribe(  # type: ignore[union-attr]
            str(audio_path),
            initial_prompt=prompt,
            language=language,
        )
        text = (result.get("text") or "").strip()
        elapsed = time.perf_counter() - started
        return TranscriptResult(
            text=text,
            backend=self._backend_name or self.backend,
            model=self.model_name,
            device=self.device,
            compute_type=self.compute_type,
            seconds=elapsed,
            language=language,
            file_path=file_path,
        )


def _cuda_available() -> bool:
    try:
        import torch  # type: ignore
        return bool(torch.cuda.is_available())
    except Exception:
        return False


class STTJSONHandler(socketserver.StreamRequestHandler):
    worker: STTWorker

    def handle(self) -> None:
        self.request.settimeout(DEFAULT_SOCKET_TIMEOUT)
        raw = self.rfile.readline().decode("utf-8", errors="replace").strip()
        if not raw:
            return
        try:
            payload = json.loads(raw)
            file_path = payload.get("path")
            if not file_path:
                raise ValueError("Missing required field: path")
            language = payload.get("language", DEFAULT_LANGUAGE)
            prompt = payload.get("prompt", DEFAULT_PROMPT_ENV)
            beam_size = int(payload.get("beam_size", DEFAULT_BEAM_SIZE))
            vad_filter = parse_bool(payload.get("vad_filter"), DEFAULT_VAD)
            result = self.worker.transcribe(file_path, language=language, prompt=prompt, beam_size=beam_size, vad_filter=vad_filter)
            self.wfile.write((json.dumps(result.as_dict(), ensure_ascii=False) + "\n").encode("utf-8"))
        except socket.timeout:
            self.wfile.write((json.dumps({"error": f"socket timeout after {DEFAULT_SOCKET_TIMEOUT}s"}) + "\n").encode("utf-8"))
        except (FileNotFoundError, IsADirectoryError, ValueError) as e:
            self.wfile.write((json.dumps({"error": str(e)}) + "\n").encode("utf-8"))
        except Exception as e:
            self.wfile.write((json.dumps({"error": str(e)}) + "\n").encode("utf-8"))


class STTUnixServer(socketserver.UnixStreamServer):
    allow_reuse_address = True


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fast reusable STT worker")
    mode = p.add_mutually_exclusive_group(required=False)
    mode.add_argument("--once", action="store_true", help="Transcribe one file and exit")
    mode.add_argument("--serve", action="store_true", help="Run as a Unix socket daemon")
    p.add_argument("--socket", default=DEFAULT_SOCKET, help="Unix socket path for --serve")
    p.add_argument("--backend", default=DEFAULT_BACKEND, choices=["faster-whisper", "whisper"], help="STT backend")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Model size/name")
    p.add_argument("--device", default=DEFAULT_DEVICE, help="Device: auto|cpu|cuda")
    p.add_argument("--compute-type", default=DEFAULT_COMPUTE_TYPE, help="Compute type for faster-whisper")
    p.add_argument("--language", default=DEFAULT_LANGUAGE, help="Language code")
    p.add_argument("--prompt", default=DEFAULT_PROMPT_ENV, help="Initial prompt")
    p.add_argument("--beam-size", type=int, default=DEFAULT_BEAM_SIZE, help="Beam size")
    p.add_argument("--vad-filter", action=argparse.BooleanOptionalAction, default=DEFAULT_VAD, help="Enable/disable VAD filtering")
    p.add_argument("file", nargs="?", help="Audio file path for one-shot mode")
    p.add_argument("--json", action="store_true", help="JSON output in one-shot mode")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    if not args.serve and not args.once:
        args.once = True

    worker = STTWorker(backend=args.backend, model=args.model, device=args.device, compute_type=args.compute_type)

    if args.serve:
        sock = Path(args.socket)
        with suppress(Exception):
            if sock.exists():
                sock.unlink()
        STTJSONHandler.worker = worker
        with STTUnixServer(str(sock), STTJSONHandler) as server:
            print(f"STT service ready at {sock} ({worker._backend_name} / {worker.model_name})", file=sys.stderr)
            try:
                server.serve_forever()
            finally:
                with suppress(Exception):
                    sock.unlink()
        return 0

    if not args.file:
        print("ERROR: provide an audio file path", file=sys.stderr)
        return 2

    result = worker.transcribe(args.file, language=args.language, prompt=args.prompt, beam_size=args.beam_size, vad_filter=args.vad_filter)
    if args.json:
        print(json.dumps(result.as_dict(), ensure_ascii=False))
    else:
        print(result.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

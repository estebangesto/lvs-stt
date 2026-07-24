# Luc.ia STT

Canonical workspace for the new local STT stack.

## Layout
- `transcribe_whisper_fast.py`, reusable worker, faster-whisper first
- `stt_benchmark.py`, latency comparison helper
- `stt_socket_client.py`, manual test client
- `lucia-stt.service`, systemd user service
- `lucia-stt.socket`, systemd socket activation
- `Makefile`, convenience targets
- `.gitignore`, repository hygiene

## Goals
- keep the model warm when needed
- avoid boot-time waste when no audio is used
- support CUDA first, CPU fallback
- keep the code ready for a future git repository

## Quick start
```bash
make lint
make install
make enable
make start
```

## Manual test
```bash
python3 /opt/lucia-stt/stt_socket_client.py /path/to/audio.ogg
python3 /opt/lucia-stt/stt_socket_client.py /path/to/audio.ogg --json
```

## Benchmark
```bash
python3 /opt/lucia-stt/stt_benchmark.py --file /path/to/audio.ogg --backend fast-socket
```

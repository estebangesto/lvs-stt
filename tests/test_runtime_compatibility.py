from __future__ import annotations

import os
import socket
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from faster_whisper.audio import decode_audio

from transcribe_whisper_fast import STTJSONHandler, create_unix_server


class PyAVCompatibilityTests(unittest.TestCase):
    def test_faster_whisper_decodes_audio_with_metadata_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / "silence.wav"
            with wave.open(str(audio_path), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16_000)
                audio.writeframes(b"\x00\x00" * 1600)

            samples = decode_audio(str(audio_path), sampling_rate=16_000)

        self.assertEqual(samples.shape, (1600,))


class SystemdSocketTests(unittest.TestCase):
    def test_activated_server_uses_systemd_socket_without_unlinking_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            socket_path = Path(directory) / "lvs-stt.sock"
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(socket_path))
            listener.listen()
            adopted_socket = socket.fromfd(listener.fileno(), socket.AF_UNIX, socket.SOCK_STREAM)

            try:
                with (
                    patch.dict(os.environ, {"LISTEN_PID": str(os.getpid()), "LISTEN_FDS": "1"}),
                    patch("transcribe_whisper_fast.socket.fromfd", return_value=adopted_socket) as fromfd,
                ):
                    server, activated = create_unix_server(socket_path, STTJSONHandler)
                try:
                    self.assertTrue(activated)
                    self.assertEqual(server.socket.getsockname(), str(socket_path))
                    self.assertTrue(socket_path.is_socket())
                    fromfd.assert_called_once_with(3, socket.AF_UNIX, socket.SOCK_STREAM)
                finally:
                    server.server_close()
            finally:
                listener.close()

    def test_direct_server_binds_requested_socket(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            socket_path = Path(directory) / "lvs-stt.sock"
            with patch.dict(os.environ, {"LISTEN_PID": "", "LISTEN_FDS": ""}):
                server, activated = create_unix_server(socket_path, STTJSONHandler)
            try:
                self.assertFalse(activated)
                self.assertTrue(socket_path.is_socket())
            finally:
                server.server_close()

    def test_direct_server_refuses_to_remove_non_socket_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            socket_path = Path(directory) / "lvs-stt.sock"
            socket_path.write_text("keep this file", encoding="utf-8")
            with (
                patch.dict(os.environ, {"LISTEN_PID": "", "LISTEN_FDS": ""}),
                self.assertRaisesRegex(RuntimeError, "refusing to remove non-socket path"),
            ):
                create_unix_server(socket_path, STTJSONHandler)
            self.assertEqual(socket_path.read_text(encoding="utf-8"), "keep this file")


if __name__ == "__main__":
    unittest.main()

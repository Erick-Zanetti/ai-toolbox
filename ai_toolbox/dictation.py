"""Dictation: record the microphone, transcribe locally with Whisper
(faster-whisper), hand the text back. No GTK here.

faster-whisper lives in its own venv (~/.local/share/ai-toolbox/stt-venv),
created on first use; on NVIDIA machines the CUDA libraries go in too and the
large-v3-turbo model runs on the GPU, otherwise a smaller model on the CPU."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

from .config import Dictation

DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "ai-toolbox"
VENV = DATA_DIR / "stt-venv"
WORKER = Path(__file__).resolve().parent / "stt_worker.py"
VENV_PYTHON_VERSION = "3.12"  # ctranslate2 wheels lag behind new Pythons
CUDA_WHEELS = ("nvidia-cublas-cu12", "nvidia-cudnn-cu12==9.*")


class DictationError(Exception):
    pass


# ── Environment ────────────────────────────────────────────────────────────

def has_nvidia() -> bool:
    smi = shutil.which("nvidia-smi")
    return bool(smi) and subprocess.run([smi, "-L"], capture_output=True).returncode == 0


def venv_python() -> Path:
    return VENV / "bin" / "python"


def installed() -> bool:
    if not venv_python().exists():
        return False
    check = subprocess.run([str(venv_python()), "-c", "import faster_whisper"], capture_output=True)
    return check.returncode == 0


def install(gpu: bool) -> None:
    """Create the venv and install faster-whisper (+ CUDA libs). Slow: ~1 GB."""
    uv = shutil.which("uv")
    if not uv:
        raise DictationError("dictation setup needs uv (https://docs.astral.sh/uv)")
    VENV.parent.mkdir(parents=True, exist_ok=True)
    steps = [[uv, "venv", "-q", "--python", VENV_PYTHON_VERSION, str(VENV)]]
    packages = ["faster-whisper", *(CUDA_WHEELS if gpu else ())]
    steps.append([uv, "pip", "install", "-q", "--python", str(venv_python()), *packages])
    for argv in steps:
        result = subprocess.run(argv, capture_output=True, text=True)
        if result.returncode != 0:
            raise DictationError((result.stderr or result.stdout).strip().splitlines()[-1])


def _cuda_lib_path() -> str:
    found = sorted(str(p) for p in VENV.glob("lib/python*/site-packages/nvidia/*/lib"))
    return os.pathsep.join(found)


# ── Recording ──────────────────────────────────────────────────────────────

def record_argv(path: Path) -> list[str]:
    """16 kHz mono 16-bit WAV, what Whisper wants, from the default microphone."""
    if shutil.which("pw-record"):
        return ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", str(path)]
    if shutil.which("parecord"):
        return ["parecord", "--rate=16000", "--channels=1", "--format=s16le",
                "--file-format=wav", str(path)]
    raise DictationError("no recorder found: install pipewire (pw-record) or pulseaudio-utils")


class Recorder:
    def __init__(self) -> None:
        handle, name = tempfile.mkstemp(prefix="ai-toolbox-", suffix=".wav")
        os.close(handle)
        self.path = Path(name)
        self.started = time.monotonic()
        self._proc = subprocess.Popen(record_argv(self.path), stdout=subprocess.DEVNULL,
                                      stderr=subprocess.PIPE)

    @property
    def seconds(self) -> float:
        return time.monotonic() - self.started

    def stop(self) -> Path:
        """Stop and return the finished WAV (SIGINT lets the recorder close it)."""
        if self._proc.poll() is None:
            self._proc.send_signal(signal.SIGINT)
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if not self.path.exists() or self.path.stat().st_size <= 44:
            err = self._proc.stderr.read().decode(errors="replace").strip() if self._proc.stderr else ""
            raise DictationError(err or "nothing was recorded")
        return self.path

    def cancel(self) -> None:
        if self._proc.poll() is None:
            self._proc.kill()
        self.path.unlink(missing_ok=True)


# ── Transcription ──────────────────────────────────────────────────────────

class Engine:
    """A warm faster-whisper worker. Thread-safe; unloads after idle time."""

    def __init__(self, settings: Dictation, on_status: Callable[[str], None] = lambda _m: None):
        self.settings = settings
        self.on_status = on_status
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._last_use = 0.0
        self.device = ""

    def _spawn(self, model: str, device: str) -> None:
        env = {**os.environ, "PYTHONNOUSERSITE": "1"}
        if device == "cuda":
            env["LD_LIBRARY_PATH"] = os.pathsep.join(
                p for p in (_cuda_lib_path(), env.get("LD_LIBRARY_PATH", "")) if p)
        compute = "float16" if device == "cuda" else "int8"
        self._proc = subprocess.Popen(
            [str(venv_python()), "-I", str(WORKER), model, device, compute],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, env=env)
        first = json.loads(self._proc.stdout.readline() or '{"error": "worker exited"}')
        if "error" in first:
            self._kill()
            raise DictationError(first["error"])
        self.device = device

    def _ensure(self) -> None:
        if self._proc and self._proc.poll() is None:
            return
        if not installed():
            gpu = self.settings.device != "cpu" and has_nvidia()
            self.on_status("setup")
            install(gpu)
        want_gpu = self.settings.device in ("auto", "cuda") and has_nvidia()
        self.on_status("loading")
        if want_gpu:
            try:
                self._spawn(self.settings.model, "cuda")
                return
            except DictationError:
                if self.settings.device == "cuda":
                    raise
        self._spawn(self.settings.cpu_model, "cpu")

    def transcribe(self, wav: Path) -> str:
        with self._lock:
            self._ensure()
            request = {"wav": str(wav), "language": self.settings.language or None}
            self._proc.stdin.write(json.dumps(request) + "\n")
            self._proc.stdin.flush()
            answer = json.loads(self._proc.stdout.readline() or '{"error": "worker exited"}')
            self._last_use = time.monotonic()
        if "error" in answer:
            raise DictationError(answer["error"])
        return answer["text"]

    def unload_if_idle(self) -> None:
        idle = time.monotonic() - self._last_use
        if self._proc and idle > self.settings.idle_unload_minutes * 60 and self._lock.acquire(False):
            try:
                self._kill()
            finally:
                self._lock.release()

    def _kill(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.kill()
        self._proc = None

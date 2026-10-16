"""Speech-to-text worker. Runs inside the dictation venv (faster-whisper), not
the app's Python, and keeps the model loaded between requests.

  python stt_worker.py <model> <device> <compute_type>

Protocol, one JSON object per line:
  stdout first line: {"ready": true, "device": "..."} or {"error": "..."}
  stdin  request:    {"wav": "/path.wav", "language": "pt" | null}
  stdout response:   {"text": "...", "language": "pt"} or {"error": "..."}
"""

import json
import sys
import wave


def reply(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def read_wav(path: str):
    import numpy as np

    with wave.open(path) as w:
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, np.int16).astype(np.float32) / 32768.0


def main() -> None:
    model_name, device, compute = sys.argv[1:4]
    try:
        from faster_whisper import WhisperModel

        model = WhisperModel(model_name, device=device, compute_type=compute)
    except Exception as err:  # noqa: BLE001 - report any load failure to the app
        reply({"error": f"{type(err).__name__}: {err}"})
        return
    reply({"ready": True, "device": device})

    for line in sys.stdin:
        try:
            request = json.loads(line)
            segments, info = model.transcribe(read_wav(request["wav"]), beam_size=5,
                                              vad_filter=True,
                                              language=request.get("language") or None)
            text = " ".join(s.text.strip() for s in segments).strip()
            reply({"text": text, "language": info.language})
        except Exception as err:  # noqa: BLE001
            reply({"error": f"{type(err).__name__}: {err}"})


if __name__ == "__main__":
    main()

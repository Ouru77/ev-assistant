"""
E.V. — Local Speech-to-Text via faster-whisper.
Turkish, runs on CPU, fully offline and free. Models are cached on the A: drive.
"""
import io

_model = None
_cfg = {"model": "small", "dir": None}


def configure(model_name: str, download_dir: str):
    _cfg["model"] = model_name or "small"
    _cfg["dir"] = download_dir


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        print(f"[E.V.] Whisper modeli yükleniyor: {_cfg['model']} (ilk seferde iner)...", flush=True)
        _model = WhisperModel(
            _cfg["model"],
            device="cpu",
            compute_type="int8",
            download_root=_cfg["dir"],
        )
        print("[E.V.] Whisper hazır.", flush=True)
    return _model


def transcribe(audio_bytes: bytes) -> str:
    """Decode audio bytes (webm/opus from the browser) and return Turkish text."""
    if not audio_bytes:
        return ""
    model = _get_model()
    segments, _info = model.transcribe(
        io.BytesIO(audio_bytes),
        language="tr",
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        condition_on_previous_text=False,
    )
    return " ".join(seg.text.strip() for seg in segments).strip()

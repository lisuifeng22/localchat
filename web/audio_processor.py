"""Audio processing: STT (faster-whisper) + TTS (OmniVoice API)."""

import hashlib
import tempfile
from pathlib import Path

import torch
from faster_whisper import WhisperModel
from gradio_client import Client

GENERATED_DIR = Path(__file__).resolve().parent.parent / "generated"

# OmniVoice voice name mapping — list of available voices
VOICE_LIST = ["jok老师", "叶奈法"]
DEFAULT_VOICE = VOICE_LIST[0]


class AudioProcessor:
    def __init__(self):
        self.stt_model = None
        self.omni_client = Client("http://localhost:7862/")

    def _load_stt(self):
        if self.stt_model is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute = "float16" if device == "cuda" else "int8"
            print(f"[Audio] Loading STT model (tiny, {device})...")
            self.stt_model = WhisperModel("tiny", device=device, compute_type=compute)
            print("[Audio] STT model loaded.")
        return self.stt_model

    def transcribe(self, audio_bytes: bytes) -> dict:
        """STT: audio bytes -> recognized text."""
        model = self._load_stt()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp = f.name
        try:
            segments, info = model.transcribe(tmp, language="zh")
            text = "".join(seg.text for seg in segments)
            return {
                "text": text.strip(),
                "duration_ms": int(info.duration * 1000),
            }
        finally:
            Path(tmp).unlink(missing_ok=True)

    def synthesize(self, text: str, speed: float = 1.0, voice: str | None = None) -> bytes:
        """TTS via OmniVoice: text -> wav bytes. `voice` selects voice name; defaults to first in VOICE_LIST."""
        voice_name = voice or DEFAULT_VOICE
        h = hashlib.md5((text + str(speed) + voice_name).encode()).hexdigest()[:12]
        cache_path = GENERATED_DIR / f"tts_{h}.wav"
        if cache_path.exists():
            return cache_path.read_bytes()

        voice_name = voice or DEFAULT_VOICE
        print(f"[TTS] Calling OmniVoice (voice={voice_name})...")

        wav_path, _ = self.omni_client.predict(
            voice_name,          # voices_dropdown
            text,                # text
            "",                  # prompt_text
            None,                # prompt_audio (no reference audio)
            speed,               # speed
            "",                  # instruct
            "Auto",              # lang
            False,               # auto_up
            api_name="/do_job",
        )

        wav_bytes = Path(wav_path).read_bytes()

        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(wav_bytes)
        print(f"[TTS] OK ({len(wav_bytes)} bytes, voice={voice_name})")
        return wav_bytes

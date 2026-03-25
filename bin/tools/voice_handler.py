#!/usr/bin/env python3
"""
DQIII8 Voice Handler — STT via Groq Whisper + TTS via gTTS.

STT: Groq Whisper Large V3 Turbo ($0.04/hour, 216x real-time)
TTS: gTTS (Google TTS, free, simple quality)
     Fallback: espeak (system, always available)

Chatterbox Multilingual is the ideal TTS but requires GPU (min 4.5GB VRAM).
VPS has 0 GPU, so gTTS is the primary TTS engine here.

Usage:
    from voice_handler import transcribe_audio, synthesize_speech
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import logging
log = logging.getLogger(__name__)
JARVIS = Path(os.environ.get("DQIII8_ROOT", "/root/dqiii8"))

# ── STT: Groq Whisper ─────────────────────────────────────────────────────────


def transcribe_audio(audio_path: str, language: str = None) -> str:
    """Transcribe audio file to text using Groq Whisper API.

    Cost: $0.04/hour (~free for short messages)
    Speed: 216x real-time on Groq LPU
    Formats: flac, mp3, mp4, mpeg, mpga, m4a, ogg, wav, webm
    """
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        return "[Error: GROQ_API_KEY not configured — cannot transcribe audio]"

    try:
        from groq import Groq

        client = Groq(api_key=groq_key)

        with open(audio_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3-turbo",
                language=language,  # None = auto-detect, "es" for Spanish, "en" for English
                response_format="text",
                temperature=0.0,
            )

        return (
            transcription.strip()
            if isinstance(transcription, str)
            else transcription.text.strip()
        )

    except Exception as e:
        return f"[Transcription error: {e}]"


def translate_audio_to_english(audio_path: str) -> str:
    """Translate audio in any language to English text."""
    groq_key = os.environ.get("GROQ_API_KEY", "")
    if not groq_key:
        return "[Error: GROQ_API_KEY not configured]"

    try:
        from groq import Groq

        client = Groq(api_key=groq_key)

        with open(audio_path, "rb") as audio_file:
            translation = client.audio.translations.create(
                file=audio_file,
                model="whisper-large-v3-turbo",
                response_format="text",
                temperature=0.0,
            )

        return (
            translation.strip()
            if isinstance(translation, str)
            else translation.text.strip()
        )

    except Exception as e:
        return f"[Translation error: {e}]"


# ── TTS: gTTS (primary) or espeak (fallback) ──────────────────────────────────

_TTS_ENGINE = None  # Lazy-loaded


def _detect_tts_engine() -> str:
    global _TTS_ENGINE
    if _TTS_ENGINE is not None:
        return _TTS_ENGINE

    # Try gTTS (Google TTS — simple, free, works everywhere)
    try:
        from gtts import gTTS  # noqa: F401

        _TTS_ENGINE = "gtts"
        return _TTS_ENGINE
    except ImportError:
        pass

    # Fallback: espeak (system, very low quality but always available)
    try:
        result = subprocess.run(
            ["espeak", "--version"], capture_output=True, timeout=3
        )
        if result.returncode == 0:
            _TTS_ENGINE = "espeak"
            return _TTS_ENGINE
    except Exception as _exc:
        log.warning('%s: %s', __name__, _exc)

    _TTS_ENGINE = "none"
    return _TTS_ENGINE


def _detect_language(text: str) -> str:
    """Simple language detection based on character analysis."""
    spanish_chars = set("áéíóúñ¿¡")
    if any(c in text.lower() for c in spanish_chars):
        return "es"
    return "en"


def synthesize_speech(text: str, output_path: str = None, language: str = None) -> str:
    """Convert text to speech audio file.

    Returns: path to .mp3 file, or empty string on failure.
    """
    tmp_dir = JARVIS / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    if not output_path:
        output_path = tempfile.mktemp(suffix=".mp3", dir=str(tmp_dir))

    if not language:
        language = _detect_language(text)

    engine = _detect_tts_engine()

    if engine == "gtts":
        return _tts_gtts(text, output_path, language)
    elif engine == "espeak":
        return _tts_espeak(text, output_path, language)
    else:
        return ""


def _tts_gtts(text: str, output_path: str, language: str) -> str:
    """Simple TTS via Google Translate TTS."""
    try:
        from gtts import gTTS

        if not output_path.endswith(".mp3"):
            output_path = output_path.rsplit(".", 1)[0] + ".mp3"
        tts = gTTS(text=text, lang=language, slow=False)
        tts.save(output_path)
        return output_path if Path(output_path).exists() else ""
    except Exception as e:
        print(f"  gTTS failed: {e}", file=sys.stderr)
        return ""


def _tts_espeak(text: str, output_path: str, language: str) -> str:
    """Minimal TTS via system espeak."""
    try:
        if not output_path.endswith(".wav"):
            output_path = output_path.rsplit(".", 1)[0] + ".wav"
        voice = language if language else "en"
        subprocess.run(
            ["espeak", "-v", voice, "-w", output_path, text],
            capture_output=True,
            timeout=30,
        )
        return output_path if Path(output_path).exists() else ""
    except Exception as e:
        print(f"  espeak failed: {e}", file=sys.stderr)
        return ""


if __name__ == "__main__":
    # Load .env
    env_file = JARVIS / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    if len(sys.argv) > 1 and sys.argv[1] == "--transcribe":
        if len(sys.argv) > 2:
            result = transcribe_audio(sys.argv[2])
            print(f"Transcription: {result}")
        else:
            print("Usage: python3 voice_handler.py --transcribe audio.ogg")

    elif len(sys.argv) > 1 and sys.argv[1] == "--speak":
        text = " ".join(sys.argv[2:]) or "Hello, I am DQ, your AI assistant."
        path = synthesize_speech(text)
        if path:
            print(f"Audio saved to: {path}")
            size = Path(path).stat().st_size
            print(f"File size: {size} bytes")
        else:
            print("TTS failed — no audio produced")

    elif len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("=== STT Test ===")
        print("Engine: Groq Whisper (cloud)")
        groq_key = os.environ.get("GROQ_API_KEY", "")
        print(f"GROQ_API_KEY: {'configured' if groq_key else 'MISSING'}")
        print()
        print("=== TTS Test ===")
        engine = _detect_tts_engine()
        print(f"Engine: {engine}")
        if engine != "none":
            path = synthesize_speech(
                "Hola, soy DQ, tu asistente de inteligencia artificial."
            )
            if path:
                print(f"Test audio: {path}")
                print(f"File size: {Path(path).stat().st_size} bytes")
            else:
                print("TTS test failed")
        else:
            print("No TTS engine available")

    else:
        print("Usage:")
        print("  python3 voice_handler.py --test")
        print("  python3 voice_handler.py --transcribe audio.ogg")
        print("  python3 voice_handler.py --speak Hello world")

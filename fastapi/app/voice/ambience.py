"""
Adds subtle call-center ambience to the AI's outbound speech: a continuous
low-level background "voice babble" bed plus a short echo/room tap, so a call
doesn't sound like a dead-silent AI voice in a vacuum. Twilio has no built-in
feature for this (its only related setting passes through a live conference
participant's own mic noise, which doesn't apply to a synthesized voice) —
this is mixed in ourselves, in raw PCM.

IMPORTANT: this must be generated/loaded and mixed at the OUTPUT sample rate
(8kHz, what Twilio actually carries), not at Gemini's native 24kHz. The
24k->8k downsample step in audio_processor.py is a naive "pick every 3rd
sample" decimation with no anti-aliasing filter — mixing broadband audio in
*before* that step folds its high-frequency content down into audible
aliasing distortion (sounds like a bad phone line). Converting/generating
the loop directly at 8kHz sidesteps the problem entirely.

Primary source: a real recorded CC0 (public domain) ambience clip —
"Busy Room Ambience / Small crowd / People talking in background" by
Breviceps, https://freesound.org/people/Breviceps/sounds/457043/ — bundled at
app/voice/assets/call_center_ambience.wav. CC0: free for commercial use, no
attribution required. Converted from its native 44.1kHz stereo down to 8kHz
mono once at startup, with a short crossfade stitched across the loop seam so
it repeats without an audible click.

If that asset is ever missing (e.g. not deployed), falls back to a
synthesized "babble" bed: several independent band-limited noise "voices"
(each filtered to roughly the human vocal band, ~300Hz-3000Hz, with its own
slow random amplitude swell) summed together — a standard cheap technique
for simulating indistinct crowd murmur without a real recording. It's a
fallback, not the primary path, because it can't approach how a real
recording sounds — kept only so the feature degrades gracefully rather than
breaking if the asset file doesn't ship.
"""
import audioop
import functools
import logging
import random
import wave
from array import array
from pathlib import Path

from app.core.config import load_config

logger = logging.getLogger(__name__)

_SAMPLE_WIDTH = 2  # 16-bit PCM
_LOOP_SECONDS = 12
_NOISE_AMPLITUDE = 6000  # peak amplitude before the level scaling below is applied
_VOICE_COUNT = 4  # independent overlapping "murmur" layers

_ASSET_PATH = Path(__file__).parent / "assets" / "call_center_ambience.wav"
_CROSSFADE_MS = 400  # blended across the loop seam so it repeats without a click
_TARGET_RMS = 1800  # loudness the real asset is normalized to before level scaling
_MAX_NORMALIZE_GAIN = 8.0  # cap so a near-silent source clip can't get amplified into noise


def _generate_babble_noise(rate: int, seconds: float, amplitude: int) -> bytes:
    n_samples = int(rate * seconds)
    mix = [0.0] * n_samples

    for _voice in range(_VOICE_COUNT):
        # Band-pass = difference of two low-passes (fast cutoff keeps <~3kHz,
        # slow cutoff keeps only the <~300Hz rumble; subtracting removes it).
        fast_leak = random.uniform(0.55, 0.70)
        slow_leak = random.uniform(0.965, 0.985)
        # Very slow envelope so this "voice"'s presence swells in and out,
        # like someone talking then pausing — the key ingredient that reads
        # as "murmur" rather than a flat noise floor.
        env_leak = random.uniform(0.9985, 0.9995)

        y_fast = 0.0
        y_slow = 0.0
        env = random.uniform(0.3, 0.7)
        voice_gain = random.uniform(0.6, 1.0) / _VOICE_COUNT

        for i in range(n_samples):
            white = random.uniform(-1.0, 1.0)
            y_fast = y_fast * fast_leak + white * (1.0 - fast_leak)
            y_slow = y_slow * slow_leak + white * (1.0 - slow_leak)
            band = y_fast - y_slow

            env = env * env_leak + random.uniform(0.0, 1.0) * (1.0 - env_leak)
            envelope = 0.25 + 0.9 * env

            mix[i] += band * envelope * voice_gain

    peak = max(1e-6, max(abs(v) for v in mix))
    samples = array("h", bytes(n_samples * _SAMPLE_WIDTH))
    for i in range(n_samples):
        normalized = mix[i] / peak
        samples[i] = int(max(-1.0, min(1.0, normalized)) * amplitude)
    return samples.tobytes()


def _crossfade_loop_seam(pcm: bytes, rate: int, crossfade_ms: int) -> bytes:
    """Blends the clip's tail into its head so looping it doesn't produce an
    audible click/jump at the seam. Returns a shorter buffer (crossfade
    portion is folded into the start, not appended) that loops seamlessly."""
    samples = array("h", pcm)
    n = len(samples)
    fade_n = min(int(rate * crossfade_ms / 1000), n // 4)
    if fade_n <= 0:
        return pcm

    head = samples[:fade_n]
    tail = samples[n - fade_n:]
    blended = array("h", bytes(fade_n * _SAMPLE_WIDTH))
    for i in range(fade_n):
        t = i / fade_n
        blended[i] = int(head[i] * t + tail[i] * (1.0 - t))

    result = blended + samples[fade_n: n - fade_n]
    return result.tobytes()


def _load_real_ambience(rate: int) -> "bytes | None":
    if not _ASSET_PATH.exists():
        return None
    try:
        with wave.open(str(_ASSET_PATH), "rb") as w:
            n_channels = w.getnchannels()
            sample_width = w.getsampwidth()
            src_rate = w.getframerate()
            raw = w.readframes(w.getnframes())

        if sample_width != _SAMPLE_WIDTH:
            raw = audioop.lin2lin(raw, sample_width, _SAMPLE_WIDTH)
        if n_channels == 2:
            raw = audioop.tomono(raw, _SAMPLE_WIDTH, 0.5, 0.5)
        elif n_channels > 2:
            raise ValueError(f"unsupported channel count: {n_channels}")

        if src_rate != rate:
            raw, _ = audioop.ratecv(raw, _SAMPLE_WIDTH, 1, src_rate, rate, None)

        # Normalize loudness so the BACKGROUND_AMBIENCE_LEVEL fraction behaves
        # consistently regardless of how quiet/loud the source recording is —
        # this particular clip is a soft murmur, well below the synthetic
        # fallback's amplitude, and would be barely audible unscaled.
        current_rms = audioop.rms(raw, _SAMPLE_WIDTH)
        if current_rms > 0:
            gain = min(_TARGET_RMS / current_rms, _MAX_NORMALIZE_GAIN)
            raw = audioop.mul(raw, _SAMPLE_WIDTH, gain)

        raw = _crossfade_loop_seam(raw, rate, _CROSSFADE_MS)
        logger.info(f"Loaded real ambience asset ({_ASSET_PATH.name}): "
                    f"{len(raw) / (rate * _SAMPLE_WIDTH):.1f}s after crossfade, {src_rate}Hz->{rate}Hz.")
        return raw
    except Exception as e:
        logger.warning(f"Failed to load ambience asset {_ASSET_PATH} ({e}) — falling back to synthetic babble.")
        return None


@functools.lru_cache(maxsize=4)
def _shared_noise_loop(rate: int) -> bytes:
    """Generated/loaded once per sample rate and cached for the life of the
    process — all concurrent call sessions read this same immutable buffer
    (each with its own random start offset), so a new call never pays the
    load/generation cost again. Prefers the real recorded asset; falls back
    to synthesized babble only if that asset is missing or fails to load."""
    real = _load_real_ambience(rate)
    if real is not None:
        return real
    return _generate_babble_noise(rate, _LOOP_SECONDS, _NOISE_AMPLITUDE)


class AmbienceMixer:
    """One instance per call session — holds the echo delay-line state and
    this call's position in the shared noise loop (randomized per instance
    so concurrent calls don't sound identical)."""

    def __init__(self, rate: int, level: float = 0.15, echo_level: float = 0.12, echo_ms: int = 70):
        self.rate = rate
        self.level = max(0.0, min(level, 1.0))
        self.echo_level = max(0.0, min(echo_level, 1.0))

        self._loop = _shared_noise_loop(rate)
        self._loop_pos = random.randrange(0, len(self._loop) - _SAMPLE_WIDTH, _SAMPLE_WIDTH)

        self._echo_delay_bytes = int(rate * echo_ms / 1000) * _SAMPLE_WIDTH
        self._echo_history = bytes(self._echo_delay_bytes)  # starts as silence

    def _next_noise_chunk(self, n_bytes: int) -> bytes:
        loop = self._loop
        loop_len = len(loop)
        pos = self._loop_pos
        end = pos + n_bytes
        if end <= loop_len:
            chunk = loop[pos:end]
        else:
            chunk = loop[pos:] + loop[: end - loop_len]
        self._loop_pos = end % loop_len
        return chunk

    def mix(self, speech_pcm: bytes) -> bytes:
        """speech_pcm: raw 16-bit PCM of the AI's own voice, before mu-law
        encoding. Returns the same audio with ambience + echo mixed in."""
        if not speech_pcm:
            return speech_pcm
        n = len(speech_pcm)

        mixed = speech_pcm
        if self.level > 0:
            noise_chunk = self._next_noise_chunk(n)
            mixed = audioop.add(mixed, audioop.mul(noise_chunk, _SAMPLE_WIDTH, self.level), _SAMPLE_WIDTH)

        if self.echo_level > 0 and self._echo_delay_bytes > 0:
            extended = self._echo_history + speech_pcm
            delayed = extended[:n]
            self._echo_history = extended[-self._echo_delay_bytes:]
            mixed = audioop.add(mixed, audioop.mul(delayed, _SAMPLE_WIDTH, self.echo_level), _SAMPLE_WIDTH)

        return mixed


def build_ambience_mixer(rate: int) -> "AmbienceMixer | None":
    """Reads config each call-session start so a level/enable change in .env
    takes effect on the next call without a code change."""
    cfg = load_config()
    enabled = cfg.get("BACKGROUND_AMBIENCE_ENABLED", "true").strip().lower() == "true"
    if not enabled:
        return None
    try:
        level = float(cfg.get("BACKGROUND_AMBIENCE_LEVEL", "0.15"))
        echo_level = float(cfg.get("BACKGROUND_ECHO_LEVEL", "0.12"))
    except ValueError:
        logger.warning("Invalid BACKGROUND_AMBIENCE_LEVEL/BACKGROUND_ECHO_LEVEL in config — using defaults.")
        level, echo_level = 0.15, 0.12
    return AmbienceMixer(rate, level=level, echo_level=echo_level)


def warm_up_ambience_cache():
    """Call once at app startup so the noise-loop generation happens before
    the first real call, not during it. Generated at 8kHz — the actual
    Twilio output rate, not Gemini's native 24kHz — see module docstring."""
    try:
        _shared_noise_loop(8000)
        logger.info("Ambience noise loop warmed up.")
    except Exception as e:
        logger.warning(f"Ambience warm-up failed (will build on first call instead): {e}")

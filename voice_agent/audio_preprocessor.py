"""
Audio Preprocessing Layer – WebRTC VAD Gate with Debouncing
Gates incoming caller audio to prevent false interruptions from background noise
or background human voices (e.g. in a crowded bus stand).

Key protection: speech onset debouncing – audio only passes through after
N consecutive speech frames. A brief background voice (< 60ms) won't sustain
enough frames to trigger, but the real caller speaking will.

Usage:
    preprocessor = AudioPreprocessor(sample_rate=16000, aggressiveness=2)
    gated_pcm = preprocessor.process(pcm_16k_bytes)
"""

import logging
import time

logger = logging.getLogger(__name__)


class AudioPreprocessor:
    """
    Real-time VAD gate with onset debouncing and hangover.

    State machine per frame:
      SILENCE  → count consecutive speech frames
      ONSET    → N consecutive speech frames seen → switch to SPEECH (open gate)
      SPEECH   → pass all frames through; reset hangover counter on silence
      HANGOVER → keep gate open for M frames after speech ends (avoids clipping word endings)

    WebRTC VAD at 16kHz uses 20ms frames = 640 bytes each.
    At 8kHz Exotel input → 16kHz upsampled = 640 bytes per chunk = exactly 1 frame.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        enabled: bool = True,
        aggressiveness: int = 2,
        onset_frames: int = 3,    # consecutive speech frames before gate opens (3 × 20ms = 60ms)
        hangover_frames: int = 8, # frames gate stays open after speech ends (8 × 20ms = 160ms)
        ns_level: int = 3,
        agc_enabled: bool = True,
    ):
        self.sample_rate = sample_rate
        self.ns_level = ns_level
        self.agc_enabled = agc_enabled
        self.enabled = enabled
        self._vad = None
        self._frame_size = None
        self._leftover = b''

        self._onset_frames = onset_frames
        self._hangover_frames = hangover_frames
        self._consecutive_speech = 0
        self._gate_open = False
        self._hangover_remaining = 0
        self._total_frames = 0
        self._passed_frames = 0
        self._last_log_time = time.time()

        # SpeexDSP filter state
        self._speex_b = None
        self._speex_a = None
        self._speex_zi = None

        self._init_vad(aggressiveness)

    def _init_vad(self, aggressiveness: int):
        """Load WebRTC VAD."""
        try:
            import webrtcvad
            self._vad = webrtcvad.Vad(aggressiveness)
            self._frame_size = int(self.sample_rate * 20 / 1000) * 2
            logger.info(
                f"🎙️ AudioPreprocessor: WebRTC VAD initialised "
                f"(sample_rate={self.sample_rate}, aggressiveness={aggressiveness}, "
                f"frame_size={self._frame_size} bytes = {self._frame_size // 2} samples = 20ms)"
            )
        except ImportError:
            logger.warning("⚠️ webrtcvad not installed – VAD disabled")
            self._vad = None
        except Exception as e:
            logger.error(f"⚠️ VAD init error: {e}")
            self._vad = None

    def process(self, pcm_bytes: bytes) -> bytes:
        """
        Apply WebRTC VAD gate. Passes speech frames through, zeros silence frames.

        Expected input: raw 16kHz 16-bit PCM bytes (for example from Gemini audio stream)
        Output: same format, with silence frames zero'd out

        Debouncing logic:
         - Onset: collect N=3 consecutive speech frames before opening gate
         - Hangover: keep gate open for M=8 frames after speech ends (avoids clipping word endings)
        This avoids gate jitter and word clipping.
        """
        if not self.enabled or self._vad is None:
            return pcm_bytes

        try:
            output = b''
            data = self._leftover + pcm_bytes

            while len(data) >= self._frame_size:
                frame = data[: self._frame_size]
                data = data[self._frame_size :]

                self._total_frames += 1

                is_speech = self._vad.is_speech(frame, self.sample_rate)

                if is_speech:
                    self._consecutive_speech += 1
                    self._hangover_remaining = self._hangover_frames

                    # Open gate once enough consecutive frames seen
                    if self._consecutive_speech >= self._onset_frames:
                        self._gate_open = True
                else:
                    self._consecutive_speech = 0
                    if self._hangover_remaining > 0:
                        self._hangover_remaining -= 1
                    else:
                        self._gate_open = False

                if self._gate_open:
                    self._passed_frames += 1
                    output += frame
                else:
                    output += b'\x00' * self._frame_size

            self._leftover = data

            # Log stats every 10 seconds
            now = time.time()
            if now - self._last_log_time >= 10 and self._total_frames > 0:
                pct = (self._passed_frames / self._total_frames) * 100
                logger.info(
                    f"🎙️ VAD stats: {self._passed_frames}/{self._total_frames} "
                    f"frames passed ({pct:.0f}%) | gate={'OPEN' if self._gate_open else 'CLOSED'}"
                )
                self._last_log_time = now

            return output if output else pcm_bytes

        except Exception as e:
            logger.error(f"⚠️ VAD processing error: {e}")
            return pcm_bytes  # passthrough on error

    def reset(self):
        """Reset VAD state (call between sessions)."""
        self._leftover = b''
        self._consecutive_speech = 0
        self._gate_open = False
        self._hangover_remaining = 0
        self._total_frames = 0
        self._passed_frames = 0

    def init_webrtc_ns(self):
        """Initialize the legacy-free WebRTC processing pipeline (10ms frames).
        This replaces speex with high-fidelity noise suppression and AGC.
        """
        try:
            from .webrtc_audio_processor import WebRTCExotelProcessor
            self._webrtc_processor = WebRTCExotelProcessor(
                exotel_rate=8000, 
                gemini_rate=self.sample_rate, 
                ns_level=self.ns_level,
                agc_enabled=self.agc_enabled
            )
            logger.info("✅ WebRTC-based processing pipeline initialized (10ms frames, 16kHz)")
        except Exception as e:
            logger.error(f"⚠️ Failed to initialize WebRTC processor: {e}")
            self._webrtc_processor = None


    def process_webrtc_ns(self, pcm_bytes: bytes) -> bytes:
        """Process Exotel 8kHz PCM audio via the WebRTC processing pipeline. Returns 16kHz PCM audio."""
        if not hasattr(self, '_webrtc_processor') or self._webrtc_processor is None:
            # Fallback resampling if processor is totally missing (safety)
            import audioop
            # Use a dummy state or just direct resampling if we're here
            pcm_16k, _ = audioop.ratecv(pcm_bytes, 2, 1, 8000, 16000, None)
            return pcm_16k

        try:
            return self._webrtc_processor.process_chunk(pcm_bytes)
        except Exception as e:
            logger.warning(f"WebRTC noise suppression error: {e}")
            return pcm_bytes

"""
Ported unchanged from voice_agent/webrtc_audio_processor.py (this is the
processor class actually used by the live call session — audio_preprocessor.py
in the old app was dead code, never imported by sessions.py).
"""
import audioop
import logging

logger = logging.getLogger(__name__)


class WebRTCExotelProcessor:
    def __init__(self, session_id, exotel_rate=8000, gemini_in_rate=16000, gemini_out_rate=24000, ns_level=3, agc_enabled=True, encoding="ulaw"):
        self.session_id = session_id
        self.exotel_rate = exotel_rate
        self.gemini_in_rate = gemini_in_rate
        self.gemini_out_rate = gemini_out_rate
        self.sample_width = 2  # 16-bit PCM
        self.encoding = encoding

        self._last_energy = 0

        self._rate_cv_state_in = None
        self._rate_cv_state_out = None

        self.frame_duration_ms = 20
        self.frame_samples = int(self.gemini_in_rate * (self.frame_duration_ms / 1000.0))
        self.frame_bytes = self.frame_samples * self.sample_width
        self._in_buffer = bytearray()

        logger.info(f"[{self.session_id}] High-Fidelity Mode: Using direct decimation for 24k->8k (Grain Reduction).")

    def process_inbound(self, audio_chunk: bytes) -> bytes:
        pcm_8k = audioop.ulaw2lin(audio_chunk, self.sample_width)
        return self.process_chunk(pcm_8k)

    def process_outbound(self, pcm_gemini: bytes) -> bytes:
        pcm_8k = b"".join([pcm_gemini[i:i + 2] for i in range(0, len(pcm_gemini), 6)])
        return audioop.lin2ulaw(pcm_8k, self.sample_width)

    def process_chunk(self, pcm_8k: bytes) -> bytes:
        pcm_in, self._rate_cv_state_in = audioop.ratecv(
            pcm_8k, self.sample_width, 1, self.exotel_rate, self.gemini_in_rate, self._rate_cv_state_in
        )
        pcm_in = audioop.mul(pcm_in, self.sample_width, 5.0)
        self._last_energy = audioop.rms(pcm_in, self.sample_width)
        return pcm_in

    def clear_buffer(self):
        self._in_buffer.clear()
        self._rate_cv_state_in = None
        self._rate_cv_state_out = None

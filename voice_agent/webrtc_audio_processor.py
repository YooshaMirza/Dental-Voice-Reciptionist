import base64
import audioop
import logging
import time

logger = logging.getLogger(__name__)

class WebRTCExotelProcessor:
    def __init__(self, session_id, exotel_rate=8000, gemini_in_rate=16000, gemini_out_rate=24000, ns_level=3, agc_enabled=True, encoding="ulaw"):
        self.session_id = session_id
        self.exotel_rate = exotel_rate
        self.gemini_in_rate = gemini_in_rate
        self.gemini_out_rate = gemini_out_rate
        self.sample_width = 2  # 16-bit PCM
        self.encoding = encoding # Forced to 'ulaw' usually
        
        # Audio energy monitor (debug)
        self._last_energy = 0
        
        # Audioop states
        self._rate_cv_state_in = None
        self._rate_cv_state_out = None
        
        # Buffer for WebRTC processing (20ms is standard)
        self.frame_duration_ms = 20
        self.frame_samples = int(self.gemini_in_rate * (self.frame_duration_ms / 1000.0))
        self.frame_bytes = self.frame_samples * self.sample_width
        self._in_buffer = bytearray()
        
        logger.info(f"[{self.session_id}] 💎 High-Fidelity Mode: Using direct decimation for 24k->8k (Grain Reduction).")

    def process_inbound(self, audio_chunk: bytes) -> bytes:
        # Standard u-law to Linear conversion
        pcm_8k = audioop.ulaw2lin(audio_chunk, self.sample_width)
        return self.process_chunk(pcm_8k)

    def process_outbound(self, pcm_gemini: bytes) -> bytes:
        # High-Quality Decimation (24kHz -> 8kHz)
        # Instead of ratecv, we take every 3rd sample to avoid aliasing grains
        # 1 sample = 2 bytes. Every 3rd sample means every 6th byte.
        pcm_8k = b"".join([pcm_gemini[i:i+2] for i in range(0, len(pcm_gemini), 6)])
        
        # Convert to u-law (Twilio default)
        return audioop.lin2ulaw(pcm_8k, self.sample_width)

    def process_chunk(self, pcm_8k: bytes) -> bytes:
        # 1. Resample 8kHz -> 16kHz
        pcm_in, self._rate_cv_state_in = audioop.ratecv(
            pcm_8k, self.sample_width, 1, self.exotel_rate, self.gemini_in_rate, self._rate_cv_state_in
        )
        
        # 2. Extreme Hearing Boost (5.0x) for Aggressive VAD
        pcm_in = audioop.mul(pcm_in, self.sample_width, 5.0)
        
        # 3. Energy monitoring (debug only)
        self._last_energy = audioop.rms(pcm_in, self.sample_width)
        
        return pcm_in
    
    def clear_buffer(self):
        self._in_buffer.clear()
        self._rate_cv_state_in = None
        self._rate_cv_state_out = None

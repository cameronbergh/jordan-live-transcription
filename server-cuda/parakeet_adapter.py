import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Awaitable, Optional
import time

import numpy as np

from config import config

logger = logging.getLogger("parakeet_adapter")


@dataclass
class TranscriptResult:
    segment_id: str
    text: str
    start_ms: int
    end_ms: int
    is_final: bool = False


TranscriptCallback = Callable[[TranscriptResult], Awaitable[None]]


class ParakeetAdapter(ABC):
    @abstractmethod
    async def initialize(self, model_name: str) -> None:
        raise NotImplementedError

    @abstractmethod
    async def warm_up(self) -> None:
        raise NotImplementedError

    @abstractmethod
    async def transcribe_stream(
        self,
        audio_chunks: AsyncIterator[bytes],
        session_id: str,
        transcript_callback: TranscriptCallback,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def shutdown(self) -> None:
        raise NotImplementedError


class MockParakeetAdapter(ParakeetAdapter):
    SAMPLE_PHRASES = [
        "Hello, how are you doing today?",
        "I'm just testing the transcription system.",
        "This is a live demo of the speech to text pipeline.",
        "The quick brown fox jumps over the lazy dog.",
        "NVIDIA Parakeet is running on the GPU server.",
        "We're streaming audio in real time.",
        "This transcript should appear word by word.",
        "Everything seems to be working correctly.",
    ]

    def __init__(self):
        self._initialized = False
        self._sample_rate = 16000
        self._segment_counter = 0

    async def initialize(self, model_name: str = "parakeet-qn-params") -> None:
        await asyncio.sleep(0.1)
        self._initialized = True

    async def warm_up(self) -> None:
        if not self._initialized:
            raise RuntimeError("Adapter not initialized")
        await asyncio.sleep(0.05)

    async def transcribe_stream(
        self,
        audio_chunks: AsyncIterator[bytes],
        session_id: str,
        transcript_callback: TranscriptCallback,
    ) -> None:
        if not self._initialized:
            raise RuntimeError("Adapter not initialized")

        buffer = b""
        chunk_count = 0
        self._segment_counter += 1
        segment_id = f"seg-{self._segment_counter:04d}"
        phrase_idx = 0
        current_phrase = self.SAMPLE_PHRASES[phrase_idx % len(self.SAMPLE_PHRASES)]
        words = current_phrase.split()
        word_index = 0
        start_ms = int(time.time() * 1000)

        async for chunk in audio_chunks:
            buffer += chunk
            chunk_count += 1

            if len(buffer) >= 1600:
                await asyncio.sleep(0.08)
                if word_index < len(words):
                    partial_text = " ".join(words[: word_index + 1])
                    end_ms = int(time.time() * 1000)
                    result = TranscriptResult(
                        segment_id=segment_id,
                        text=partial_text,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        is_final=False,
                    )
                    await transcript_callback(result)
                    word_index += 1

                if word_index >= len(words) and chunk_count % 8 == 0:
                    phrase_idx += 1
                    current_phrase = self.SAMPLE_PHRASES[
                        phrase_idx % len(self.SAMPLE_PHRASES)
                    ]
                    words = current_phrase.split()
                    word_index = 0
                    self._segment_counter += 1
                    segment_id = f"seg-{self._segment_counter:04d}"
                    final_result = TranscriptResult(
                        segment_id=segment_id,
                        text=current_phrase,
                        start_ms=start_ms,
                        end_ms=int(time.time() * 1000),
                        is_final=True,
                    )
                    await transcript_callback(final_result)
                    start_ms = int(time.time() * 1000)
                    self._segment_counter += 1
                    segment_id = f"seg-{self._segment_counter:04d}"

                buffer = buffer[len(buffer) // 2 :]

    async def shutdown(self) -> None:
        self._initialized = False


class RealParakeetAdapter(ParakeetAdapter):
    def __init__(self):
        self._initialized = False
        self._model = None
        self._vad_model = None
        self._sample_rate = 16000
        self._device: Optional[str] = None
        self._torch = None

    def _import_torch(self):
        if self._torch is None:
            import torch

            self._torch = torch
        return self._torch

    async def initialize(self, model_name: str = "parakeet-qn-params") -> None:
        torch = self._import_torch()

        if not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA not available. RealParakeetAdapter requires NVIDIA GPU with CUDA."
            )

        self._device = f"cuda:{config.gpu_device_id}"
        torch.cuda.set_device(config.gpu_device_id)

        try:
            from nemo.collections.asr.models import EncDecCTCModel
        except ImportError as e:
            raise RuntimeError(
                f"NeMo not installed. Install with: pip install nemo-toolkit[asr]\n"
                f"Import error: {e}"
            )

        self._model = EncDecCTCModel.from_pretrained(model_name=model_name)
        self._model = self._model.to(self._device)
        self._model.eval()
        self._model_name = model_name

        try:
            from nemo.collections.asr.models import EncDecClassificationModel

            self._vad_model = EncDecClassificationModel.from_pretrained(
                model_name=config.vad_model
            )
            self._vad_model = self._vad_model.to(self._device)
            self._vad_model.eval()
        except Exception as e:
            logger.warning(
                f"VAD model not available ({config.vad_model}): {e}. "
                "Running without VAD (transcription will proceed without voice activity detection)."
            )
            self._vad_model = None

        self._initialized = True

    async def warm_up(self) -> None:
        if not self._initialized:
            raise RuntimeError("Adapter not initialized")
        torch = self._import_torch()

        dummy_audio = torch.randn(
            1, self._sample_rate, dtype=torch.float32, device=self._device
        )
        dummy_length = torch.tensor(
            [self._sample_rate], dtype=torch.long, device=self._device
        )
        with torch.no_grad():
            self._model(input_signal=dummy_audio, input_signal_length=dummy_length)

        if self._vad_model is not None:
            dummy_vad = torch.randn(
                1, self._sample_rate, dtype=torch.float32, device=self._device
            )
            dummy_vad_length = torch.tensor(
                [self._sample_rate], dtype=torch.long, device=self._device
            )
            with torch.no_grad():
                self._vad_model(
                    input_signal=dummy_vad, input_signal_length=dummy_vad_length
                )

    def _decode_logprobs(self, log_probs, encoded_len) -> str:
        """Decode CTC log probabilities using greedy decoding + BPE detokenization.

        Uses direct argmax + CTC collapse to avoid the broken GreedyCTCInfer.vocab_size
        access in NeMo's ctc_decoder_predictions_tensor, then decodes via decode_ids_to_str
        which uses the SentencePiece tokenizer on model.decoding.tokenizer.
        """
        torch = self._import_torch()
        try:
            # log_probs: (B, T, V) — take argmax over vocabulary dimension
            predicted_ids = torch.argmax(log_probs, dim=-1)  # (B, T)

            # Get actual sequence length from encoded_len
            if encoded_len is not None and torch.is_tensor(encoded_len):
                seq_len = encoded_len[0].item()
            else:
                seq_len = predicted_ids.shape[1]

            # CTC decoding: collapse repeated tokens, remove blanks (token_id=0)
            ids = predicted_ids[0, :seq_len].cpu().numpy()

            # Collapse runs of same token
            collapsed = []
            prev = -1
            for token_id in ids:
                if token_id != prev:
                    collapsed.append(int(token_id))
                    prev = int(token_id)

            # Remove CTC blank token (blank_id for this model is 1024, vocab_size is 1024)
            # Also guard against any tokens >= vocab_size that might cause tokenizer errors
            blank_id = getattr(self._model.decoding, 'blank_id', 0)
            vocab_size = getattr(self._model.tokenizer, 'vocab_size', 0)
            text_tokens = [t for t in collapsed if t != blank_id and t < vocab_size]
            if not text_tokens:
                return ""

            # Use decode_ids_to_str which handles SentencePiece detokenization
            decoded_str = self._model.decoding.decode_ids_to_str(text_tokens)
            if decoded_str:
                return decoded_str.strip()
            return ""
        except Exception as e:
            logger.error(f"CTC greedy decode failed: {e}", exc_info=True)
        return ""

    async def transcribe_stream(
        self,
        audio_chunks: AsyncIterator[bytes],
        session_id: str,
        transcript_callback: TranscriptCallback,
    ) -> None:
        if not self._initialized:
            raise RuntimeError("Adapter not initialized")
        torch = self._import_torch()

        buffer = b""
        min_samples = int(0.5 * self._sample_rate)
        segment_counter = 0
        pending_text = ""
        segment_start_ms = 0

        async for chunk in audio_chunks:
            buffer += chunk

            if len(buffer) < 2:
                continue

            samples = np.frombuffer(buffer, dtype=np.int16)
            if len(samples) < min_samples:
                continue

            transcript_text = self._run_inference(torch, samples)

            if transcript_text:
                segment_counter += 1
                now_ms = int(time.time() * 1000)
                if segment_start_ms == 0:
                    segment_start_ms = int(
                        now_ms - (len(samples) / self._sample_rate * 1000)
                    )

                result = TranscriptResult(
                    segment_id=f"seg-{session_id}-{segment_counter:04d}",
                    text=transcript_text,
                    start_ms=segment_start_ms,
                    end_ms=now_ms,
                    is_final=False,
                )
                await transcript_callback(result)
                pending_text = transcript_text
                segment_start_ms = now_ms

            kept_samples = max(0, len(samples) - min_samples)
            buffer = buffer[-kept_samples * 2 :] if kept_samples > 0 else b""

        # Flush remaining buffer as a final transcript
        if len(buffer) >= 2:
            samples = np.frombuffer(buffer, dtype=np.int16)
            if len(samples) >= min_samples:
                transcript_text = self._run_inference(torch, samples)
                if transcript_text:
                    segment_counter += 1
                    now_ms = int(time.time() * 1000)
                    if segment_start_ms == 0:
                        segment_start_ms = now_ms
                    result = TranscriptResult(
                        segment_id=f"seg-{session_id}-{segment_counter:04d}",
                        text=transcript_text,
                        start_ms=segment_start_ms,
                        end_ms=now_ms,
                        is_final=True,
                    )
                    await transcript_callback(result)
                    return

        if pending_text:
            segment_counter += 1
            now_ms = int(time.time() * 1000)
            result = TranscriptResult(
                segment_id=f"seg-{session_id}-{segment_counter:04d}",
                text=pending_text,
                start_ms=segment_start_ms,
                end_ms=now_ms,
                is_final=True,
            )
            await transcript_callback(result)

    def _run_inference(self, torch, samples: np.ndarray) -> str:
        audio_tensor = (
            torch.from_numpy(samples.astype(np.float32) / 32768.0)
            .unsqueeze(0)
            .to(self._device)
        )
        audio_length = torch.tensor(
            [samples.shape[0]], dtype=torch.long, device=self._device
        )

        with torch.no_grad():
            model_output = self._model(
                input_signal=audio_tensor, input_signal_length=audio_length
            )

        if isinstance(model_output, tuple) and len(model_output) >= 2:
            log_probs = model_output[0]
            encoded_len = model_output[1]
        elif isinstance(model_output, tuple):
            log_probs = model_output[0]
            encoded_len = audio_length
        else:
            log_probs = model_output
            encoded_len = audio_length

        return self._decode_logprobs(log_probs, encoded_len)

    async def shutdown(self) -> None:
        self._initialized = False
        self._model = None
        self._vad_model = None
        torch = self._import_torch()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def create_parakeet_adapter() -> ParakeetAdapter:
    if config.enable_mock_parakeet:
        return MockParakeetAdapter()
    return RealParakeetAdapter()

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
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


class TranscriptionAdapter(ABC):
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


ParakeetAdapter = TranscriptionAdapter


class MockParakeetAdapter(TranscriptionAdapter):
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


class RealParakeetAdapter(TranscriptionAdapter):
    def __init__(self):
        self._initialized = False
        self._model = None
        self._sample_rate = 16000
        self._device: Optional[str] = None
        self._torch = None

    def _import_torch(self):
        if self._torch is None:
            import torch

            self._torch = torch
        return self._torch

    def _disable_cuda_graph_decoder(self):
        """Turn off CUDA graph acceleration in the transducer decoder.

        NeMo's TDT label-looping decoder compiles CUDA graphs via
        cuda-python's cu_call().  If the installed cuda-python version
        returns fewer values than NeMo expects, the decoder silently
        yields empty hypotheses.  Disabling CUDA graphs forces the
        eager-mode fallback which works on any driver.
        """
        try:
            decoder = getattr(self._model, "decoding", None)
            inner = getattr(decoder, "decoding", None)
            if inner is not None and hasattr(inner, "use_cuda_graph_decoder"):
                inner.use_cuda_graph_decoder = False
                logger.info("Disabled CUDA graph decoder (eager-mode fallback)")
                return

            from omegaconf import OmegaConf, open_dict

            cfg = self._model.cfg.decoding
            with open_dict(cfg):
                if hasattr(cfg, "greedy"):
                    cfg.greedy.use_cuda_graph_decoder = False
                elif hasattr(cfg, "greedy_batch"):
                    cfg.greedy_batch.use_cuda_graph_decoder = False
            self._model.change_decoding_strategy(cfg)
            logger.info("Disabled CUDA graph decoder via decoding config")
        except Exception as e:
            logger.warning(f"Could not disable CUDA graph decoder: {e}")

    async def initialize(self, model_name: str = "nvidia/parakeet-tdt-0.6b-v2") -> None:
        torch = self._import_torch()

        if not torch.cuda.is_available():
            raise RuntimeError(
                "CUDA not available. RealParakeetAdapter requires NVIDIA GPU with CUDA."
            )

        self._device = f"cuda:{config.gpu_device_id}"
        torch.cuda.set_device(config.gpu_device_id)

        try:
            from nemo.collections.asr.models import ASRModel
        except ImportError as e:
            raise RuntimeError(
                f"NeMo not installed. Install with: pip install nemo-toolkit[asr]\n"
                f"Import error: {e}"
            )

        logger.info(f"Loading ASR model: {model_name}")
        self._model = ASRModel.from_pretrained(model_name=model_name)
        self._model = self._model.to(self._device)
        self._model.eval()
        self._model_name = model_name

        # Disable CUDA graph decoder — works around cu_call() return-value
        # mismatch between cuda-python versions and NeMo's expectation.
        self._disable_cuda_graph_decoder()

        self._initialized = True
        logger.info(f"Model loaded: {type(self._model).__name__}")

    async def warm_up(self) -> None:
        if not self._initialized:
            raise RuntimeError("Adapter not initialized")
        loop = asyncio.get_event_loop()
        dummy = np.zeros(self._sample_rate, dtype=np.float32)
        await loop.run_in_executor(None, self._run_transcribe, dummy)
        logger.info("Warm-up inference complete")

    def _run_transcribe(self, audio_float32: np.ndarray) -> str:
        """Run model.transcribe() on a 1-D float32 numpy array normalized to [-1, 1]."""
        try:
            result = self._model.transcribe([audio_float32], batch_size=1)

            if isinstance(result, tuple):
                result = result[0]

            if isinstance(result, list) and len(result) > 0:
                item = result[0]
                if hasattr(item, "text"):
                    return str(item.text).strip()
                return str(item).strip()

            return str(result).strip() if result else ""
        except Exception as e:
            logger.error(f"Transcribe failed: {e}", exc_info=True)
        return ""

    async def _infer_buffer(self, loop, audio_bytes: bytearray) -> str:
        samples = np.frombuffer(bytes(audio_bytes), dtype=np.int16)
        audio_float = samples.astype(np.float32) / 32768.0
        return await loop.run_in_executor(None, self._run_transcribe, audio_float)

    async def transcribe_stream(
        self,
        audio_chunks: AsyncIterator[bytes],
        session_id: str,
        transcript_callback: TranscriptCallback,
    ) -> None:
        if not self._initialized:
            raise RuntimeError("Adapter not initialized")

        loop = asyncio.get_event_loop()

        all_audio = bytearray()
        last_inference_len = 0
        segment_counter = 0
        current_segment_id = f"seg-{session_id}-{segment_counter:04d}"
        segment_start_ms = int(time.time() * 1000)

        min_bytes = int(config.min_context_secs * self._sample_rate * 2)
        interval_bytes = int(config.inference_interval_secs * self._sample_rate * 2)
        max_bytes = int(config.max_context_secs * self._sample_rate * 2)
        overlap_bytes = int(config.overlap_secs * self._sample_rate * 2)

        async for chunk in audio_chunks:
            all_audio.extend(chunk)

            if len(all_audio) < min_bytes:
                continue

            new_bytes = len(all_audio) - last_inference_len
            if new_bytes < interval_bytes:
                continue

            # Slide window: finalize current segment, keep overlap for continuity
            if len(all_audio) > max_bytes:
                text = await self._infer_buffer(loop, all_audio)
                if text:
                    now_ms = int(time.time() * 1000)
                    await transcript_callback(
                        TranscriptResult(
                            segment_id=current_segment_id,
                            text=text,
                            start_ms=segment_start_ms,
                            end_ms=now_ms,
                            is_final=True,
                        )
                    )

                all_audio = bytearray(all_audio[-overlap_bytes:])
                last_inference_len = 0
                segment_counter += 1
                current_segment_id = f"seg-{session_id}-{segment_counter:04d}"
                segment_start_ms = int(time.time() * 1000)
                continue

            text = await self._infer_buffer(loop, all_audio)
            last_inference_len = len(all_audio)

            if text:
                now_ms = int(time.time() * 1000)
                await transcript_callback(
                    TranscriptResult(
                        segment_id=current_segment_id,
                        text=text,
                        start_ms=segment_start_ms,
                        end_ms=now_ms,
                        is_final=False,
                    )
                )

        # Final flush
        if len(all_audio) >= min_bytes:
            text = await self._infer_buffer(loop, all_audio)
            if text:
                now_ms = int(time.time() * 1000)
                await transcript_callback(
                    TranscriptResult(
                        segment_id=current_segment_id,
                        text=text,
                        start_ms=segment_start_ms,
                        end_ms=now_ms,
                        is_final=True,
                    )
                )

    async def shutdown(self) -> None:
        self._initialized = False
        self._model = None
        torch = self._import_torch()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


def create_parakeet_adapter() -> TranscriptionAdapter:
    if config.enable_mock_parakeet:
        return MockParakeetAdapter()
    return RealParakeetAdapter()

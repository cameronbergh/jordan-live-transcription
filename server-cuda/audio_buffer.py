import numpy as np
from collections import deque
from typing import Optional


class AudioBuffer:
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self._buffer: deque[np.ndarray] = deque()
        self._total_samples: int = 0
        self._start_time_ms: int = 0

    def append(self, pcm_bytes: bytes) -> None:
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        self._buffer.append(samples)
        self._total_samples += len(samples)

    def set_start_time(self, start_ms: int) -> None:
        self._start_time_ms = start_ms

    @property
    def total_samples(self) -> int:
        return self._total_samples

    @property
    def duration_ms(self) -> int:
        return int(self._total_samples / self.sample_rate * 1000)

    def get_samples(self, num_samples: Optional[int] = None) -> np.ndarray:
        if num_samples is None:
            chunks = list(self._buffer)
            if not chunks:
                return np.array([], dtype=np.float32)
            return np.concatenate(chunks)
        else:
            accumulated = 0
            result = []
            for chunk in self._buffer:
                if accumulated + len(chunk) >= num_samples:
                    needed = num_samples - accumulated
                    result.append(chunk[:needed])
                    break
                else:
                    result.append(chunk)
                    accumulated += len(chunk)
            return np.concatenate(result) if result else np.array([], dtype=np.float32)

    def get_latest(self, num_samples: int) -> np.ndarray:
        total = self.total_samples
        if total <= num_samples:
            return self.get_samples()
        return self.get_samples(total)[-num_samples:]

    def get_duration_ms_for_samples(self, num_samples: int) -> int:
        return int(num_samples / self.sample_rate * 1000)

    def clear(self) -> None:
        self._buffer.clear()
        self._total_samples = 0

    def reset(self) -> None:
        self.clear()
        self._start_time_ms = 0

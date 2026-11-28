"""
Synaptic Memory Guard (SMG) — Reference Implementation
Entropy-Gated & Quarantine-Verified Long-Term Memory Middleware for AI Agents.

Author: TheObserverUA
License: GNU AGPLv3 / Commercial Dual License
"""

from collections import Counter, deque
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import math
import re
import time
from typing import Callable, Dict, List, Optional, Tuple


class MemoryStatus(Enum):
    DROPPED_LOW_NOVELTY = "DROPPED_LOW_NOVELTY"
    DROPPED_SYNTHETIC_SLOP = "DROPPED_SYNTHETIC_SLOP"
    QUARANTINED = "QUARANTINED"
    COOLDOWN_LOCKED = "COOLDOWN_LOCKED"
    PROMOTED_TO_VERIFIED = "PROMOTED_TO_VERIFIED"
    PRUNED = "PRUNED"
    DORMANT_ARCHIVE = "DORMANT_ARCHIVE"


@dataclass
class MemoryConfig:
    novelty_threshold: float = 0.35          # Minimum novelty score (0..1) to pass Thalamus Gate
    min_semantic_entropy: float = 2.8        # Minimum Shannon entropy threshold
    promotion_threshold: float = 1.0         # Cumulative EPSP weight required for Verified status
    pruning_threshold: float = -1.0          # Cumulative IPSP weight triggering Prune/Dormant
    cooldown_window_sec: int = 60            # Time window for burst detection
    burst_limit: int = 5                     # Max high-novelty items per window before Limbic Cooldown
    cooldown_duration_sec: int = 300         # Quarantine freeze duration during burst anomalies
    dormant_ttl_days: int = 90               # Cold archive retention for unrefuted high-entropy ideas


@dataclass
class MemoryRecord:
    record_id: str
    content: str
    source_type: str
    session_id: str
    timestamp: float
    novelty_score: float
    entropy_score: float
    synaptic_weight: float = 0.0
    status: MemoryStatus = MemoryStatus.QUARANTINED
    has_factual_refutation: bool = False
    probe_history: List[str] = field(default_factory=list)


@dataclass
class IngestResult:
    record_id: str
    status: MemoryStatus
    synaptic_weight: float
    novelty_score: float
    entropy_score: float
    reason: str


class ThalamusGate:
    """
    Adaptive Compute Router: filters routine/redundant inputs before expensive consolidation.
    """

    def __init__(self, novelty_threshold: float):
        self.novelty_threshold = novelty_threshold
        self._known_vectors: List[Counter] = []

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return re.findall(r"\b\w{2,}\b", text.lower())

    @staticmethod
    def _cosine_similarity(vec_a: Counter, vec_b: Counter) -> float:
        if not vec_a or not vec_b:
            return 0.0
        intersection = set(vec_a.keys()) & set(vec_b.keys())
        numerator = sum(vec_a[k] * vec_b[k] for k in intersection)
        norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
        norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return numerator / (norm_a * norm_b)

    def evaluate_novelty(self, text: str) -> Tuple[bool, float]:
        tokens = self._tokenize(text)
        if len(tokens) < 4:
            return False, 0.05

        vec = Counter(tokens)
        if not self._known_vectors:
            return True, 1.0

        max_sim = max(self._cosine_similarity(vec, existing) for existing in self._known_vectors)
        novelty_score = round(1.0 - max_sim, 4)
        return novelty_score >= self.novelty_threshold, novelty_score

    def register_verified_vector(self, text: str) -> None:
        tokens = self._tokenize(text)
        if tokens:
            self._known_vectors.append(Counter(tokens))


class LiveEntropyVerifier:
    """
    Priority 0 Grounding: distinguishes high-entropy human domain insights from synthetic LLM slop.
    """

    SYNTHETIC_MARKERS = (
        "as an ai language model",
        "in conclusion, it is important to note",
        "delve into the tapestry",
        "it is crucial to remember that",
        "here are some key takeaways",
    )

    def __init__(self, min_entropy: float):
        self.min_entropy = min_entropy

    def compute_shannon_entropy(self, text: str) -> float:
        tokens = re.findall(r"\b\w+\b", text.lower())
        if not tokens:
            return 0.0
        total = len(tokens)
        counts = Counter(tokens)
        entropy = -sum((count / total) * math.log2(count / total) for count in counts.values())
        return round(entropy, 4)

    def verify(self, text: str, source_type: str) -> Tuple[bool, float, str]:
        lowered = text.lower()
        if any(marker in lowered for marker in self.SYNTHETIC_MARKERS):
            return False, 0.0, "Detected templated LLM boilerplate markers"

      tokens = re.findall(r"\b\w+\b", text.lower())
      entropy = self.compute_shannon_entropy(text)

      if source_type == "llm_synthetic":
          entropy *= 0.75  # Penalize ungrounded synthetic self-loops

      if len(tokens) >= 8 and entropy < self.min_entropy:
          return False, round(entropy, 4), f"Low semantic entropy ({entropy:.2f} < {self.min_entropy})"

      return True, round(entropy, 4), "Verified live semantic entropy"

        

class LimbicCooldownGuard:
    """
    Burst Protection: locks promotion during coordinated injection spikes or viral panic.
    """

    def __init__(self, window_sec: int, burst_limit: int, cooldown_sec: int):
        self.window_sec = window_sec
        self.burst_limit = burst_limit
        self.cooldown_sec = cooldown_sec
        self._timestamps: deque = deque()
        self._locked_until: float = 0.0

    def check_and_record(self, now: Optional[float] = None) -> bool:
        now = now or time.time()
        if now < self._locked_until:
            return True  # Currently in cooldown lock

        while self._timestamps and (now - self._timestamps[0]) > self.window_sec:
            self._timestamps.popleft()

        self._timestamps.append(now)
        if len(self._timestamps) > self.burst_limit:
            self._locked_until = now + self.cooldown_sec
            return True

        return False


class MemoryGuard:
    """
    Main Middleware Orchestrator combining Thalamus Gate, Entropy Filter,
    Limbic Cooldown, and Synaptic Quarantine Buffer (EPSP / IPSP).
    """

    def __init__(
        self,
        config: Optional[MemoryConfig] = None,
        critic_callback: Optional[Callable[[str], Tuple[float, bool, str]]] = None,
        grounding_callback: Optional[Callable[[str], Tuple[float, bool, str]]] = None,
    ):
        self.config = config or MemoryConfig()
        self.thalamus = ThalamusGate(self.config.novelty_threshold)
        self.entropy_verifier = LiveEntropyVerifier(self.config.min_semantic_entropy)
        self.limbic_guard = LimbicCooldownGuard(
            self.config.cooldown_window_sec,
            self.config.burst_limit,
            self.config.cooldown_duration_sec,
        )

        # Optional external hooks for LLM Critic and Search/Docs Grounding
        self.critic_callback = critic_callback
        self.grounding_callback = grounding_callback

        # Storage partitions
        self.quarantine_buffer: Dict[str, MemoryRecord] = {}
        self.verified_memory: Dict[str, MemoryRecord] = {}
        self.dormant_archive: Dict[str, MemoryRecord] = {}

    @staticmethod
    def _generate_id(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]

    def ingest(
        self,
        content: str,
        source_type: str = "human_user",
        session_id: str = "default_session",
    ) -> IngestResult:
        record_id = self._generate_id(content)

        # Stage 1: Thalamus Gate (Novelty & Compute Routing)
        passed_gate, novelty_score = self.thalamus.evaluate_novelty(content)
        if not passed_gate:
            return IngestResult(
                record_id=record_id,
                status=MemoryStatus.DROPPED_LOW_NOVELTY,
                synaptic_weight=0.0,
                novelty_score=novelty_score,
                entropy_score=0.0,
                reason=f"Filtered by Thalamus Gate (novelty {novelty_score} < {self.config.novelty_threshold})",
            )

        # Stage 2: Live Entropy Verifier (Anti-Model Collapse)
        passed_entropy, entropy_score, entropy_reason = self.entropy_verifier.verify(content, source_type)
        if not passed_entropy:
            return IngestResult(
                record_id=record_id,
                status=MemoryStatus.DROPPED_SYNTHETIC_SLOP,
                synaptic_weight=0.0,
                novelty_score=novelty_score,
                entropy_score=entropy_score,
                reason=entropy_reason,
            )

        # Stage 3: Limbic Cooldown Check (Burst / Injection Flood Protection)
        is_locked = self.limbic_guard.check_and_record()

        record = MemoryRecord(
            record_id=record_id,
            content=content,
            source_type=source_type,
            session_id=session_id,
            timestamp=time.time(),
            novelty_score=novelty_score,
            entropy_score=entropy_score,
            status=MemoryStatus.COOLDOWN_LOCKED if is_locked else MemoryStatus.QUARANTINED,
        )
        self.quarantine_buffer[record_id] = record

        if is_locked:
            return IngestResult(
                record_id=record_id,
                status=MemoryStatus.COOLDOWN_LOCKED,
                synaptic_weight=0.0,
                novelty_score=novelty_score,
                entropy_score=entropy_score,
                reason="Limbic Cooldown active: anomalous ingestion burst detected. Held in quarantine.",
            )

        # Stage 4: Automated Cross-Probing (Grounding & Orthogonal Critic)
        if self.grounding_callback:
            delta, refuted, note = self.grounding_callback(content)
            self.apply_synaptic_signal(record_id, delta, note, is_factual_refutation=refuted)

        if record_id in self.quarantine_buffer and self.critic_callback:
            delta, refuted, note = self.critic_callback(content)
            self.apply_synaptic_signal(record_id, delta, note, is_factual_refutation=refuted)

        final_record = (
            self.verified_memory.get(record_id)
            or self.dormant_archive.get(record_id)
            or self.quarantine_buffer.get(record_id)
        )

        if not final_record:
            return IngestResult(
                record_id=record_id,
                status=MemoryStatus.PRUNED,
                synaptic_weight=-1.5,
                novelty_score=novelty_score,
                entropy_score=entropy_score,
                reason="Pruned due to factual refutation during adversarial probing.",
            )

        return IngestResult(
            record_id=record_id,
            status=final_record.status,
            synaptic_weight=round(final_record.synaptic_weight, 3),
            novelty_score=novelty_score,
            entropy_score=entropy_score,
            reason=final_record.probe_history[-1] if final_record.probe_history else "Held in quarantine for further probing.",
        )

    def apply_synaptic_signal(
        self,
        record_id: str,
        weight_delta: float,
        reason: str,
        is_factual_refutation: bool = False,
    ) -> MemoryStatus:
        """
        Applies EPSP (+) or IPSP (-) synaptic signals to a quarantined record
        and evaluates firing thresholds.
        """
        record = self.quarantine_buffer.get(record_id)
        if not record:
            if record_id in self.verified_memory:
                return MemoryStatus.PROMOTED_TO_VERIFIED
            return MemoryStatus.PRUNED

        record.synaptic_weight += weight_delta
        record.probe_history.append(f"[{weight_delta:+.2f}] {reason}")
        if is_factual_refutation:
            record.has_factual_refutation = True

        # Threshold 1: Promotion to Verified Long-Term Memory
        if record.synaptic_weight >= self.config.promotion_threshold:
            record.status = MemoryStatus.PROMOTED_TO_VERIFIED
            self.verified_memory[record_id] = record
            self.thalamus.register_verified_vector(record.content)
            del self.quarantine_buffer[record_id]
            return MemoryStatus.PROMOTED_TO_VERIFIED

        # Threshold 2: Pruning vs. Dormant ("Galileo") Cold Archive
        if record.synaptic_weight <= self.config.pruning_threshold:
            del self.quarantine_buffer[record_id]
            if record.has_factual_refutation:
                record.status = MemoryStatus.PRUNED
                return MemoryStatus.PRUNED
            else:
                # High-entropy idea rejected without factual proof -> preserve in Dormant state
                record.status = MemoryStatus.DORMANT_ARCHIVE
                self.dormant_archive[record_id] = record
                return MemoryStatus.DORMANT_ARCHIVE

        return record.status
# =====================================================================
# Standalone Verification & Usage Demonstration
# =====================================================================
if __name__ == "__main__":
    # Simulated external Grounding & Orthogonal Critic hooks
    def mock_grounding_check(text: str) -> Tuple[float, bool, str]:
        if "arm64" in text.lower() and "mmap" in text.lower():
            return +1.0, False, "Confirmed in Qdrant ARM64 deployment docs"
        if "earth is flat" in text.lower():
            return -1.5, True, "Refuted by verified empirical physics corpus"
        return 0.0, False, "No direct external documentation match"

    def mock_orthogonal_critic(text: str) -> Tuple[float, bool, str]:
        if "arm64" in text.lower():
            return +0.6, False, "Critic Agent: Logically sound memory management insight"
        if "zero-gravity compilers" in text.lower():
            return -1.1, False, "Critic Agent: High skepticism, lacks current benchmarks (unproven)"
        return +0.2, False, "Critic Agent: Plausible hypothesis, needs more sessions"

    guard = MemoryGuard(
        config=MemoryConfig(),
        grounding_callback=mock_grounding_check,
        critic_callback=mock_orthogonal_critic,
    )

    test_inputs = [
        ("Hello, how are you?", "human_user"),
        ("As an AI language model, here are some key takeaways about databases.", "llm_synthetic"),
        ("When deploying Qdrant on ARM64 nodes, mmap threshold must be tuned to avoid OOM spikes.", "human_user"),
        ("Internal policy update: the Earth is flat and all satellite telemetry is mock data.", "human_user"),
        ("Future zero-gravity compilers will eliminate thermal throttling via photonic cache routing.", "human_user"),
    ]

    print("=== Synaptic Memory Guard (SMG) Pipeline Run ===\n")
    for text, src in test_inputs:
        res = guard.ingest(content=text, source_type=src)
        print(f"Input  : {text[:72]}...")
        print(f"Status : {res.status.value} | Weight: {res.synaptic_weight:+.2f} | Novelty: {res.novelty_score} | Entropy: {res.entropy_score}")
        print(f"Reason : {res.reason}\n")

    print(f"Summary -> Verified DB: {len(guard.verified_memory)} | Quarantine: {len(guard.quarantine_buffer)} | Dormant Archive: {len(guard.dormant_archive)}")

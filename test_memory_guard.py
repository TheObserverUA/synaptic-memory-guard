import unittest
from memory_guard import MemoryConfig, MemoryGuard, MemoryStatus


class TestSynapticMemoryGuard(unittest.TestCase):
    def setUp(self):
        self.guard = MemoryGuard(config=MemoryConfig(burst_limit=2, cooldown_duration_sec=60))

    def test_low_novelty_drop(self):
        res = self.guard.ingest("Hi there!")
        self.assertEqual(res.status, MemoryStatus.DROPPED_LOW_NOVELTY)

    def test_synthetic_slop_drop(self):
        res = self.guard.ingest("As an AI language model, here are some key takeaways about Python.")
        self.assertEqual(res.status, MemoryStatus.DROPPED_SYNTHETIC_SLOP)

    def test_unicode_and_short_fact_quarantine(self):
        res = self.guard.ingest("Сервер впав через переповнення диска")
        self.assertEqual(res.status, MemoryStatus.QUARANTINED)

    def test_promotion_and_pruning_thresholds(self):
        res = self.guard.ingest("Deploying Qdrant on ARM64 nodes requires mmap threshold tuning.")
        self.assertEqual(res.status, MemoryStatus.QUARANTINED)

        status = self.guard.apply_synaptic_signal(res.record_id, +1.2, "Verified via docs")
        self.assertEqual(status, MemoryStatus.PROMOTED_TO_VERIFIED)
        self.assertIn(res.record_id, self.guard.verified_memory)

    def test_limbic_cooldown_burst_protection(self):
        self.guard.ingest("First unique engineering insight about database indexing.")
        self.guard.ingest("Second unique engineering insight about network latency.")
        res_burst = self.guard.ingest("Third unique engineering insight triggering burst lock.")
        self.assertEqual(res_burst.status, MemoryStatus.COOLDOWN_LOCKED)


if __name__ == "__main__":
    unittest.main()

"""Regression guards for DeterministicFusion snapshot restore across tiers.

A snapshot saved at one tier (or a legacy ResonanceField save) must load into an
instance configured at a different tier without leaving module states whose width
disagrees with ``state_dim`` — otherwise the next ``resonate()`` indexes past the
configured width (IndexError when a smaller snapshot loads into a larger tier).
"""

from __future__ import annotations

from sylanne_core.compute.deterministic_fusion import create_deterministic_fusion


class TestCrossTierRestore:
    def test_smaller_snapshot_into_larger_tier_no_index_error(self):
        # lite(8-dim) snapshot loaded into a pro(16-dim) instance previously
        # IndexError'd on the next resonate(): range(state_dim=16) over 8-long states.
        lite = create_deterministic_fusion(n_modules=7, tier="lite")
        lite.inject(0, [0.5] * 8)
        snap = lite.to_dict()

        pro = create_deterministic_fusion(n_modules=7, tier="pro")
        pro.from_dict(snap)

        assert pro.state_dim == 16
        assert all(len(s) == 16 for s in pro.module_states)
        pro.resonate()  # must not raise
        assert all(len(s) == 16 for s in pro.module_states)

    def test_larger_snapshot_into_smaller_tier_aligned(self):
        # pro(16) snapshot into lite(8): states must truncate to 8 rather than stay
        # 16-long and silently desync from state_dim.
        pro = create_deterministic_fusion(n_modules=7, tier="pro")
        pro.inject(0, [0.5] * 16)
        snap = pro.to_dict()

        lite = create_deterministic_fusion(n_modules=7, tier="lite")
        lite.from_dict(snap)

        assert lite.state_dim == 8
        assert all(len(s) == 8 for s in lite.module_states)
        lite.resonate()  # must not raise

    def test_fewer_modules_in_snapshot_no_index_error(self):
        # A ragged/foreign snapshot whose "states" list has fewer rows than n_modules
        # survived the width-resize but then IndexError'd in resonate() (range(n_modules)
        # over too-few states). from_dict must pad the module COUNT to n_modules too.
        fusion = create_deterministic_fusion(n_modules=7, tier="lite")
        fusion.from_dict({"tier": "lite", "states": [[0.1] * 8, [0.2] * 8, [0.3] * 8]})

        assert len(fusion.module_states) == 7
        assert all(len(s) == 8 for s in fusion.module_states)
        fusion.resonate()  # must not raise

    def test_more_modules_in_snapshot_truncated(self):
        fusion = create_deterministic_fusion(n_modules=7, tier="lite")
        fusion.from_dict({"tier": "lite", "states": [[0.0] * 8 for _ in range(11)]})

        assert len(fusion.module_states) == 7
        fusion.resonate()  # must not raise

    def test_same_tier_roundtrip_preserves_values(self):
        # Same-tier restore must be a faithful round-trip (resize is a no-op).
        lite = create_deterministic_fusion(n_modules=7, tier="lite")
        lite.inject(2, [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
        snap = lite.to_dict()

        restored = create_deterministic_fusion(n_modules=7, tier="lite")
        restored.from_dict(snap)

        assert restored.module_states == lite.module_states

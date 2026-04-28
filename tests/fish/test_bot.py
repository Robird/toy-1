"""tests/fish/test_bot.py — BotInput 决定性 + 启发式行为 + 30s 跑不抛。"""

from __future__ import annotations

import math

from toy_engine.geom import Vec2
from toy_engine.input import BotInputBase, InputFrame
from toy_engine.loop import GameLoop
from toy_engine.rng import SeededRng

from fish.ai.bot_player import BotInput
from fish.config.constants import DT, TIER_FRY, TIER_GIANT
from fish.systems.level_generator import LevelGenerator
from fish.world import World


def _basic_snap(*, ptier=0, fishes=(), boss=None, ppos=(640.0, 360.0)):
    entities = [
        {"eid": 0, "kind": "player", "pos": list(ppos), "vel": [0, 0],
         "radius": 10, "alive": True, "heading": 0.0, "tier": ptier},
    ]
    for i, f in enumerate(fishes, start=1):
        entities.append({
            "eid": i, "kind": "fish", "pos": list(f["pos"]), "vel": [0, 0],
            "radius": 14, "alive": True, "heading": 0.0,
            "tier": int(f["tier"]), "state": "WANDER",
        })
    return {
        "player_pos": tuple(ppos),
        "player_tier": ptier,
        "entities": entities,
        "boss": boss,
    }


class TestBotInputBasics:
    def test_subclass_of_botinputbase(self):
        bot = BotInput(SeededRng(0))
        assert isinstance(bot, BotInputBase)

    def test_returns_input_frame(self):
        bot = BotInput(SeededRng(0))
        out = bot.poll(_basic_snap())
        assert isinstance(out, InputFrame)

    def test_drift_when_empty(self):
        bot = BotInput(SeededRng(0))
        out = bot.poll(_basic_snap())
        assert out.desired_dir is None


class TestHeuristic:
    def test_flees_high_tier_threat_in_front(self):
        bot = BotInput(SeededRng(0))
        # threat tier=3 right of player at +100,0 ; player tier=0 → tier diff = 3 ≥ 2
        snap = _basic_snap(
            ptier=0,
            fishes=[{"pos": (740.0, 360.0), "tier": 3}],
        )
        out = bot.poll(snap)
        assert out.desired_dir is not None
        # 应朝 -x 方向逃
        assert out.desired_dir.x < -0.9

    def test_chases_prey(self):
        bot = BotInput(SeededRng(0))
        # prey tier=1 at +100,0 ; player tier=0 → can_eat (tier ≤ 0+1)
        snap = _basic_snap(
            ptier=0,
            fishes=[{"pos": (740.0, 360.0), "tier": 1}],
        )
        out = bot.poll(snap)
        assert out.desired_dir is not None
        assert out.desired_dir.x > 0.9

    def test_threat_one_tier_above_does_not_trigger_flee(self):
        bot = BotInput(SeededRng(0))
        # tier=1 vs player tier=0：差 1 不算威胁（启发式要求 ≥ tier+2）
        # 且 tier=1 满足 ≤ ptier+1 = 1 → 是 prey！应该被追
        snap = _basic_snap(ptier=0, fishes=[{"pos": (740.0, 360.0), "tier": 1}])
        out = bot.poll(snap)
        assert out.desired_dir is not None
        assert out.desired_dir.x > 0  # toward prey

    def test_flee_boss_when_low_tier(self):
        bot = BotInput(SeededRng(0))
        snap = _basic_snap(
            ptier=0,
            boss={"pos": [740.0, 360.0], "heading": 0.0, "state": "PATROL",
                  "intro_remaining": 0.0, "hp": 3, "max_hp": 3, "enraged": False,
                  "bite_count": 0, "eid": 99},
        )
        out = bot.poll(snap)
        assert out.desired_dir is not None
        assert out.desired_dir.x < 0  # away from boss

    def test_targets_stunned_boss_when_tier4(self):
        bot = BotInput(SeededRng(0))
        snap = _basic_snap(
            ptier=TIER_GIANT,
            boss={"pos": [740.0, 360.0], "heading": 0.0, "state": "STUNNED",
                  "intro_remaining": 0.0, "hp": 3, "max_hp": 3, "enraged": False,
                  "bite_count": 0, "eid": 99},
        )
        out = bot.poll(snap)
        assert out.desired_dir is not None
        # STUNNED → 直冲 boss
        assert out.desired_dir.x > 0.9


class TestDeterminism:
    def test_same_seed_same_outputs(self):
        # 跑两个独立 World，输入序列必须一致
        rng_a = SeededRng(42)
        cfg_a = LevelGenerator.generate(seed=42, difficulty=0.5, rng=rng_a)
        wa = World(cfg_a, SeededRng(cfg_a.seed))
        bot_a = BotInput(SeededRng(7).spawn("bot"))

        rng_b = SeededRng(42)
        cfg_b = LevelGenerator.generate(seed=42, difficulty=0.5, rng=rng_b)
        wb = World(cfg_b, SeededRng(cfg_b.seed))
        bot_b = BotInput(SeededRng(7).spawn("bot"))

        loop_a = GameLoop(wa, bot_a, dt=DT, max_sim_seconds=2.0)
        loop_b = GameLoop(wb, bot_b, dt=DT, max_sim_seconds=2.0)
        loop_a.run_headless()
        loop_b.run_headless()
        assert wa.snapshot_hash() == wb.snapshot_hash()


class TestLongRun:
    def test_runs_30s_without_throwing(self):
        rng = SeededRng(0)
        cfg = LevelGenerator.generate(seed=0, difficulty=0.5, rng=rng)
        world = World(cfg, SeededRng(cfg.seed))
        bot = BotInput(SeededRng(0).spawn("bot"))
        loop = GameLoop(world, bot, dt=DT, max_sim_seconds=30.0)
        loop.run_headless()  # 不抛即通过
        # 若已死亡 or 仍 running 都可
        assert world.frame_count > 0

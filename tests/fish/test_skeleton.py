"""tests/fish/test_skeleton.py — M3-01 骨架自检。

只验证：包可导入、常量存在、LevelConfig.default() 形状正确、main() 可运行。
具体业务行为（World / 实体 / 系统）的测试由后续步骤补全。
"""

from __future__ import annotations

import importlib

import pytest


def test_import_fish_package() -> None:
    """fish 包顶层可被 import。"""
    mod = importlib.import_module("fish")
    assert hasattr(mod, "__version__")


def test_constants_exposed() -> None:
    """constants 模块至少导出已知常量，且数值与 fish-doc 文档一致。"""
    from fish.config.constants import (
        DT,
        Phase,
        TIER_THRESHOLDS,
        WORLD_H,
        WORLD_W,
    )

    assert (WORLD_W, WORLD_H) == (1280, 720)         # fish-doc 00 §4.2
    assert DT == pytest.approx(1.0 / 60.0)           # fish-doc 00 §4.2
    assert TIER_THRESHOLDS == (0, 8, 25, 60, 150)    # fish-doc 01 §2
    # Phase 必须含四个阶段
    assert {p.name for p in Phase} == {"WARMUP", "PRESSURE", "BOSS", "REVENGE"}


def test_level_config_default_shape() -> None:
    """LevelConfig.default() 字段类型与文档声明一致。"""
    from fish.config.constants import Phase
    from fish.config.level_config import BossConfig, LevelConfig, PhaseConfig

    cfg = LevelConfig.default()

    assert isinstance(cfg, LevelConfig)
    assert isinstance(cfg.seed, int)
    assert isinstance(cfg.world_size, tuple) and len(cfg.world_size) == 2
    assert all(isinstance(v, int) for v in cfg.world_size)
    assert isinstance(cfg.difficulty, float)
    assert isinstance(cfg.boss, BossConfig)
    assert isinstance(cfg.boss.appear_time_s, float)
    assert isinstance(cfg.boss.sense_radius, float)
    assert isinstance(cfg.boss.chase_speed, float)
    assert isinstance(cfg.boss.turn_rate, float)
    assert isinstance(cfg.boss.charge_cooldown, float)
    assert isinstance(cfg.boss.hp, int)
    assert isinstance(cfg.phases, dict)
    # 必含四个阶段（fish-doc 04 §2：phases 必含 WARMUP/PRESSURE/BOSS/REVENGE）
    assert set(cfg.phases.keys()) == set(Phase)
    for ph_cfg in cfg.phases.values():
        assert isinstance(ph_cfg, PhaseConfig)
        assert isinstance(ph_cfg.duration_s, float)
        assert isinstance(ph_cfg.population_target, dict)
        assert all(isinstance(k, int) for k in ph_cfg.population_target)
        assert all(isinstance(v, int) for v in ph_cfg.population_target.values())
        assert isinstance(ph_cfg.spawn_rate, dict)
        assert all(isinstance(k, int) for k in ph_cfg.spawn_rate)
        assert all(isinstance(v, float) for v in ph_cfg.spawn_rate.values())
        assert isinstance(ph_cfg.fish_speed_mul, float)
        assert isinstance(ph_cfg.threat_aggression, float)

    # 默认值必须满足 fish-doc 04 §4/§5 中写明的区间与硬约束。
    assert 12.0 <= cfg.phases[Phase.WARMUP].duration_s <= 18.0
    assert 15.0 <= cfg.phases[Phase.PRESSURE].duration_s <= 25.0
    assert cfg.phases[Phase.WARMUP].population_target.get(3, 0) == 0
    assert cfg.phases[Phase.WARMUP].population_target.get(4, 0) == 0
    assert all(phase.population_target.get(4, 0) <= 3 for phase in cfg.phases.values())
    assert 25.0 <= cfg.boss.appear_time_s <= 60.0


def test_level_config_is_frozen() -> None:
    """LevelConfig 顶层字段不可被重新赋值（frozen=True）。"""
    from dataclasses import FrozenInstanceError

    from fish.config.level_config import LevelConfig

    cfg = LevelConfig.default()
    with pytest.raises(FrozenInstanceError):
        cfg.seed = 42  # type: ignore[misc]


def test_main_runs(capsys: pytest.CaptureFixture[str]) -> None:
    """main() 可被调用并完成 headless 多帧 demo。

    M3-02 起 main() 合法地透传依赖到 toy_engine.input（其顶层 import pygame，
    但仅创建模块对象、不创建 display）。M3-04 起 main() 跑 300 帧（fish 群刷新
    演示）；M3-05 起跑 600 帧（碰撞 / 成长 / DEAD 演示）。本测试只验证可
    执行 + 打印骨架字样与 snapshot 主要字段；不锁帧数避免 main 节奏调整时回归。
    """
    from fish.main import main

    main()
    captured = capsys.readouterr()
    assert "fish MVP" in captured.out
    assert "skeleton ready" in captured.out
    assert "frames=" in captured.out
    assert "player_pos=" in captured.out
    assert "stats=" in captured.out

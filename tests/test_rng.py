"""toy_engine.rng 单元测试，对齐 01-rng.md 的 DoD 验收清单。"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import textwrap

import pytest

from toy_engine.rng import SeededRng


# --------------------------------------------------------------------------- #
# DoD: 同 seed 创建两个 SeededRng，对相同操作序列产生完全一致的输出
# --------------------------------------------------------------------------- #
def test_same_seed_same_sequence() -> None:
    a = SeededRng(42)
    b = SeededRng(42)
    seq_a = [a.random() for _ in range(50)]
    seq_b = [b.random() for _ in range(50)]
    assert seq_a == seq_b


def test_same_seed_mixed_ops_same_sequence() -> None:
    a = SeededRng(12345)
    b = SeededRng(12345)
    out_a = [
        a.random(),
        a.uniform(-1.0, 1.0),
        a.randint(0, 100),
        a.choice([10, 20, 30, 40]),
        a.gauss(0.0, 1.0),
    ]
    out_b = [
        b.random(),
        b.uniform(-1.0, 1.0),
        b.randint(0, 100),
        b.choice([10, 20, 30, 40]),
        b.gauss(0.0, 1.0),
    ]
    assert out_a == out_b


def test_different_seeds_diverge() -> None:
    a = SeededRng(1)
    b = SeededRng(2)
    assert [a.random() for _ in range(10)] != [b.random() for _ in range(10)]


# --------------------------------------------------------------------------- #
# DoD: spawn("a") 与 spawn("b") 输出独立（无消耗干扰）
# --------------------------------------------------------------------------- #
def test_spawn_children_independent() -> None:
    root1 = SeededRng(7)
    fish1 = root1.spawn("fish_spawner")
    baseline = [fish1.random() for _ in range(20)]

    root2 = SeededRng(7)
    fish2 = root2.spawn("fish_spawner")
    boss2 = root2.spawn("boss_ai")
    # 大量消耗 boss 子流，不应影响 fish 子流
    for _ in range(1000):
        boss2.random()
    observed = [fish2.random() for _ in range(20)]

    assert observed == baseline


def test_spawn_does_not_advance_parent() -> None:
    """spawn 是纯派生操作，不推进父流 MT 状态。"""
    parent_a = SeededRng(99)
    parent_b = SeededRng(99)

    parent_b.spawn("anything")
    parent_b.spawn("more")
    parent_b.spawn("stuff")

    assert [parent_a.random() for _ in range(20)] == [
        parent_b.random() for _ in range(20)
    ]


def test_parent_consumption_does_not_affect_child() -> None:
    root1 = SeededRng(123)
    child1 = root1.spawn("fish_spawner")
    baseline = [child1.random() for _ in range(20)]

    root2 = SeededRng(123)
    for _ in range(500):
        root2.random()
    child2 = root2.spawn("fish_spawner")
    observed = [child2.random() for _ in range(20)]

    assert observed == baseline


# --------------------------------------------------------------------------- #
# DoD: 重命名某个子流不影响其它子流
# --------------------------------------------------------------------------- #
def test_renaming_substream_does_not_affect_siblings() -> None:
    root_v1 = SeededRng(2024)
    phases_v1 = root_v1.spawn("phases")
    boss_v1 = root_v1.spawn("boss")
    for _ in range(100):
        boss_v1.random()
    expected = [phases_v1.random() for _ in range(10)]

    root_v2 = SeededRng(2024)
    # 把 "boss" 重命名为 "boss_v2"，phases 不受影响
    phases_v2 = root_v2.spawn("phases")
    boss_v2 = root_v2.spawn("boss_v2")
    for _ in range(100):
        boss_v2.random()
    actual = [phases_v2.random() for _ in range(10)]

    assert actual == expected


# --------------------------------------------------------------------------- #
# DoD: spawn("a") 多次得到等价子流
# --------------------------------------------------------------------------- #
def test_spawn_same_name_equivalent_streams() -> None:
    root = SeededRng(2026)
    s1 = root.spawn("fish_spawner")
    s2 = root.spawn("fish_spawner")
    assert s1 is not s2  # 不同实例
    assert [s1.random() for _ in range(30)] == [s2.random() for _ in range(30)]


def test_nested_spawn_path_stable() -> None:
    """嵌套 spawn 路径稳定：相同路径产生相同序列。"""
    root_a = SeededRng(555)
    leaf_a = root_a.spawn("a").spawn("b").spawn("c")
    root_b = SeededRng(555)
    leaf_b = root_b.spawn("a").spawn("b").spawn("c")
    assert [leaf_a.random() for _ in range(15)] == [
        leaf_b.random() for _ in range(15)
    ]


def test_nested_spawn_distinct_paths_diverge() -> None:
    root = SeededRng(555)
    p1 = root.spawn("a").spawn("b")
    p2 = root.spawn("b").spawn("a")
    assert [p1.random() for _ in range(10)] != [p2.random() for _ in range(10)]


# --------------------------------------------------------------------------- #
# DoD: PYTHONHASHSEED=random 下跨进程结果仍然一致
# --------------------------------------------------------------------------- #
def _cross_process_script() -> str:
    return textwrap.dedent(
        """
        import sys, json
        from toy_engine.rng import SeededRng
        root = SeededRng(20260427)
        out = {
            "root": [root.random() for _ in range(5)],
            "fish": [root.spawn("fish_spawner").random() for _ in range(5)],
            "boss_ai": [root.spawn("boss_ai").random() for _ in range(5)],
            "nested": [
                root.spawn("phases").spawn("inner").random() for _ in range(5)
            ],
        }
        sys.stdout.write(json.dumps(out))
        """
    )


def _run_subprocess(hashseed: str) -> str:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = hashseed
    # 让子进程能 import toy_engine
    env["PYTHONPATH"] = repo_root + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c", _cross_process_script()],
        capture_output=True,
        text=True,
        env=env,
        check=True,
        cwd=repo_root,
    )
    return result.stdout


def test_cross_process_hashseed_random_reproducible() -> None:
    out_a = _run_subprocess("random")
    out_b = _run_subprocess("random")
    out_c = _run_subprocess("0")
    assert out_a == out_b == out_c


# --------------------------------------------------------------------------- #
# DoD: get_state / set_state 往返一致，且后续 spawn 派生也一致
# --------------------------------------------------------------------------- #
def test_get_set_state_roundtrip_random_sequence() -> None:
    rng = SeededRng(98765)
    # 先消耗一些
    for _ in range(17):
        rng.random()
    state = rng.get_state()
    expected = [rng.random() for _ in range(20)]

    restored = SeededRng(0)
    restored.set_state(state)
    actual = [restored.random() for _ in range(20)]
    assert actual == expected


def test_get_set_state_roundtrip_preserves_spawn_derivation() -> None:
    rng = SeededRng(98765)
    for _ in range(17):
        rng.random()
    state = rng.get_state()
    expected_child_seq = [
        rng.spawn("fish_spawner").random() for _ in range(10)
    ]

    restored = SeededRng(0)
    restored.set_state(state)
    actual_child_seq = [
        restored.spawn("fish_spawner").random() for _ in range(10)
    ]
    assert actual_child_seq == expected_child_seq


# --------------------------------------------------------------------------- #
# DoD: 边界行为
# --------------------------------------------------------------------------- #
def test_choice_empty_raises_index_error() -> None:
    rng = SeededRng(0)
    with pytest.raises(IndexError):
        rng.choice([])


def test_choice_generator_raises_type_error() -> None:
    rng = SeededRng(0)

    def gen():
        yield 1
        yield 2

    with pytest.raises(TypeError):
        rng.choice(gen())


def test_choice_iterator_raises_type_error() -> None:
    rng = SeededRng(0)
    with pytest.raises(TypeError):
        rng.choice(iter([1, 2, 3]))


def test_gauss_sigma_zero_returns_mu_without_consuming_state() -> None:
    rng = SeededRng(42)
    state_before = rng.get_state()
    result = rng.gauss(3.14, 0.0)
    state_after = rng.get_state()
    assert result == 3.14
    assert state_before == state_after


def test_gauss_negative_sigma_raises() -> None:
    rng = SeededRng(0)
    with pytest.raises(ValueError):
        rng.gauss(0.0, -0.1)


def test_seed_larger_than_64_bit() -> None:
    big_seed = (1 << 200) + 1234567
    a = SeededRng(big_seed)
    b = SeededRng(big_seed)
    assert [a.random() for _ in range(20)] == [b.random() for _ in range(20)]
    # 不同的大种子应给出不同序列
    c = SeededRng((1 << 200) + 1234568)
    assert [a.random() for _ in range(5)] != [c.random() for _ in range(5)]


def test_seed_zero_and_negative_are_supported() -> None:
    zero_a = SeededRng(0)
    zero_b = SeededRng(0)
    assert [zero_a.random() for _ in range(10)] == [
        zero_b.random() for _ in range(10)
    ]

    negative_a = SeededRng(-123456789)
    negative_b = SeededRng(-123456789)
    assert [negative_a.random() for _ in range(10)] == [
        negative_b.random() for _ in range(10)
    ]


def test_seed_must_be_int() -> None:
    with pytest.raises(TypeError):
        SeededRng("42")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        SeededRng(3.14)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        SeededRng(True)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        SeededRng(False)  # type: ignore[arg-type]


def test_spawn_name_validation() -> None:
    rng = SeededRng(0)
    with pytest.raises(TypeError):
        rng.spawn(123)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        rng.spawn(True)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        rng.spawn("")


def test_spawn_unicode_name() -> None:
    """name 走 utf-8 编码，应支持非 ASCII。"""
    a = SeededRng(1)
    b = SeededRng(1)
    seq_a = [a.spawn("鱼群").random() for _ in range(5)]
    seq_b = [b.spawn("鱼群").random() for _ in range(5)]
    assert seq_a == seq_b
    seq_diff = [SeededRng(1).spawn("boss").random() for _ in range(5)]
    assert seq_a != seq_diff


# --------------------------------------------------------------------------- #
# 跨进程 spawn 派生稳定性：BLAKE2b 不依赖 PYTHONHASHSEED
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("seed", "name", "expected_child_seed", "expected_first_values"),
    [
        (
            42,
            "fish_spawner",
            11681822636822581446,
            [0.18237160182883916, 0.8752539832935368, 0.6958644610548514],
        ),
        (
            20260427,
            "boss_ai",
            7166187524925382291,
            [0.29032481558669565, 0.3131933129094735, 0.49125392721730166],
        ),
        (
            -123456789,
            "鱼群",
            17199484220979709978,
            [0.5937796027808268, 0.150931576503479, 0.7120464722974402],
        ),
        (
            (1 << 200) + 1234567,
            "phases",
            10456624246721747227,
            [0.8698639010251841, 0.23249700629987846, 0.8133444142656976],
        ),
    ],
)
def test_spawn_seed_value_stable_known_vectors(
    seed: int,
    name: str,
    expected_child_seed: int,
    expected_first_values: list[float],
) -> None:
    """钉死派生算法：改实现要主动改本测试 + 升 _SPAWN_DOMAIN 版本号。"""
    child = SeededRng(seed).spawn(name)
    assert child.get_state()[0] == expected_child_seed
    assert [child.random() for _ in range(3)] == expected_first_values


# --------------------------------------------------------------------------- #
# DoD: CI/pytest 能发现业务代码对 random.* / numpy.random 的误用
# --------------------------------------------------------------------------- #
_FORBIDDEN_GLOBAL_RANDOM_RE = re.compile(
    r"\brandom\.(?:random|uniform|randint|choice|gauss|shuffle)\("
    r"|\bnumpy\.random\b"
    r"|\bnp\.random\b"
)


def test_toy_engine_modules_do_not_call_global_random_apis() -> None:
    """在 toy_engine 包内禁止新增全局随机调用；rng.py 自身除外。"""
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    offenders: list[str] = []

    for path in sorted((repo_root / "toy_engine").rglob("*.py")):
        if path.name == "rng.py":
            continue
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _FORBIDDEN_GLOBAL_RANDOM_RE.search(line):
                rel_path = path.relative_to(repo_root)
                offenders.append(f"{rel_path}:{line_no}: {line.strip()}")

    assert offenders == []

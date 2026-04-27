"""SeededRng — 确定性随机源（toy-engine MVP / 01-rng.md）。

只依赖 Python 标准库：
- ``random.Random``（Mersenne Twister）作为底层流；
- ``hashlib.blake2b`` 作为子流派生函数（不受 ``PYTHONHASHSEED`` 影响）。

业务代码禁止使用 ``random.*`` / ``numpy.random`` 全局函数，统一通过
``SeededRng`` 实例及其 ``spawn(name)`` 派生子流。
"""

from __future__ import annotations

import hashlib
import random
from typing import Sequence, TypeVar

__all__ = ["SeededRng"]

T = TypeVar("T")

# 派生协议版本号；任何修改都构成确定性破坏，必须升版本号。
_SPAWN_DOMAIN = b"toy_engine.SeededRng.v1\0"


class SeededRng:
    """命名子流可派生的确定性随机源。

    Parameters
    ----------
    seed:
        任意 Python ``int``。不会先截断到 64 bit；子流派生时才会取
        BLAKE2b 64-bit digest 作为子 RNG 的种子。
    """

    __slots__ = ("_seed", "_random")

    def __init__(self, seed: int) -> None:
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise TypeError(f"seed must be int, got {type(seed).__name__}")
        self._seed: int = seed
        self._random: random.Random = random.Random(seed)

    # ------------------------------------------------------------------ #
    # 核心采样 API（fish-doc 07 §1 契约）
    # ------------------------------------------------------------------ #
    def random(self) -> float:
        """返回 ``[0.0, 1.0)`` 区间均匀分布浮点。"""
        return self._random.random()

    def uniform(self, a: float, b: float) -> float:
        """返回 ``[a, b]``（或 ``[b, a]``）区间均匀分布浮点。"""
        return self._random.uniform(a, b)

    def randint(self, a: int, b: int) -> int:
        """返回闭区间 ``[a, b]`` 上的随机整数。"""
        return self._random.randint(a, b)

    def choice(self, seq: Sequence[T]) -> T:
        """从具体 ``Sequence`` 中等概率挑选一个元素。

        - 不接受生成器/迭代器（不会隐式 ``list(seq)``），否则抛
          ``TypeError``；
        - 空序列抛 ``IndexError``。
        """
        if not hasattr(seq, "__len__") or not hasattr(seq, "__getitem__"):
            raise TypeError(
                "choice() requires a concrete Sequence with __len__ and "
                f"__getitem__, got {type(seq).__name__}"
            )
        n = len(seq)
        if n == 0:
            raise IndexError("Cannot choose from an empty sequence")
        # 使用底层 randrange(n) 取得合法下标，避免拼装 randint(0, n - 1)。
        return seq[self._random.randrange(n)]

    def gauss(self, mu: float, sigma: float) -> float:
        """高斯分布；``sigma == 0`` 时直接返回 ``mu`` 且不消耗 RNG 状态。"""
        if sigma < 0:
            raise ValueError(f"sigma must be >= 0, got {sigma}")
        if sigma == 0:
            return mu
        return self._random.gauss(mu, sigma)

    # ------------------------------------------------------------------ #
    # 命名子流派生
    # ------------------------------------------------------------------ #
    def spawn(self, name: str) -> "SeededRng":
        """基于 ``(canonical_seed, name)`` 派生独立子流。

        派生是纯函数操作，不推进当前实例的 MT 状态。同名重复 ``spawn``
        返回逻辑上等价的子流（不同实例，但种子和后续序列相同）。
        """
        if not isinstance(name, str):
            raise TypeError(f"name must be str, got {type(name).__name__}")
        if name == "":
            raise ValueError("name must be a non-empty string")

        payload = (
            _SPAWN_DOMAIN
            + str(self._seed).encode("ascii")
            + b"\0"
            + name.encode("utf-8")
        )
        child_seed = int.from_bytes(
            hashlib.blake2b(payload, digest_size=8).digest(),
            "little",
        )
        return SeededRng(child_seed)

    # ------------------------------------------------------------------ #
    # 调试 / 测试辅助（不写入 Recorder JSON）
    # ------------------------------------------------------------------ #
    def get_state(self) -> tuple:
        """返回 ``(canonical_seed, random_state)``，用于 set_state 往返。"""
        return (self._seed, self._random.getstate())

    def set_state(self, state: tuple) -> None:
        """恢复 ``get_state()`` 返回的状态；spawn 派生也会同步恢复。"""
        if not isinstance(state, tuple) or len(state) != 2:
            raise TypeError("state must be a 2-tuple from get_state()")
        seed, random_state = state
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise TypeError("state[0] (canonical seed) must be int")
        self._seed = seed
        self._random.setstate(random_state)

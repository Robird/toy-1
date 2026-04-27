# 01 — SeededRng（确定性随机）

> 父文档：[00-overview.md](00-overview.md) ｜ 关联：[fish-doc 07 §1](../../fish-doc/mvp/07-test-harness.md)、[04-recorder.md](04-recorder.md)
>
> **本模块是引擎地基，所有其它模块都可以依赖它。**

## 1. 设计要点

- **完全自包含**：基于 Python 标准库 `random.Random`（Mersenne Twister），不引入新依赖
- **禁止**业务代码使用 `random.*` / `numpy.random` 全局函数；统一通过 `SeededRng` 实例，并在 CI/测试中按 §6 检查
- **可派生子流**：`spawn(name)` 基于 `(seed, name)` 哈希派生子 RNG，用于隔离子系统消耗顺序，避免"鱼群刷新顺序变了导致 Boss 行为也变了"这种脆弱耦合
- **可调试状态**：`get_state() / set_state()` 仅作为测试/调试辅助；录像仍以 seed + 输入重放为准
- **大整数 seed 不截断**：根 seed 接受任意 Python `int`，不先截断到 64 bit；子流派生结果才是 BLAKE2b 64-bit digest

## 2. API

```python
from typing import Sequence, TypeVar
T = TypeVar("T")

class SeededRng:
    def __init__(self, seed: int) -> None: ...

    # fish-doc 07 §1 核心契约
    def random(self) -> float: ...                    # [0.0, 1.0)
    def uniform(self, a: float, b: float) -> float: ...
    def randint(self, a: int, b: int) -> int: ...    # 闭区间 [a, b]
    def choice(self, seq: Sequence[T]) -> T: ...
    def gauss(self, mu: float, sigma: float) -> float: ...

    # 派生子流（fish-doc 04 §7 / 07 §1 核心）
    def spawn(self, name: str) -> "SeededRng": ...

    # 调试/测试辅助；非 Recorder 持久化格式
    def get_state(self) -> tuple: ...
    def set_state(self, state: tuple) -> None: ...
```

### 2.1 边界行为

- `choice(seq)` 只接受已实现 `__len__` / `__getitem__` 的具体 `Sequence`；空序列抛 `IndexError`；生成器/迭代器不隐式转 `list`，应抛 `TypeError`。
- `gauss(mu, sigma)`：`sigma < 0` 抛 `ValueError`；`sigma == 0` 直接返回 `mu`，且**不消耗** RNG 状态；`sigma > 0` 才委托底层 `random.Random.gauss()`。
- `get_state()` 返回 `(canonical_seed, random_state)`；`set_state()` 同时恢复二者，保证恢复后继续 `spawn()` 的派生结果也一致。该 tuple 只承诺在同 Python 主版本内用于测试/调试往返，不写入 Recorder JSON。

## 3. `spawn` 的语义

```python
rng       = SeededRng(42)
rng_fish  = rng.spawn("fish_spawner")
rng_boss  = rng.spawn("boss_ai")
rng_fish2 = rng.spawn("fish_spawner")   # 与 rng_fish 同序列
```

- 同名 `spawn` 多次返回**逻辑上等价**的子流（实现细节：每次创建新实例，但种子相同 → 输出序列相同）
- 子流之间相互独立：`rng_boss` 取多少次都不会影响 `rng_fish` 的下一次输出
- 父流 `rng` 与子流之间也独立：调用 `rng.random()` 不影响 `rng_fish.random()`
- `spawn(name)` 是纯派生操作，不推进父流的 `random.Random` 状态；fork 后父/子、子/子状态互不影响
- 重命名某个子流只影响该子流自身：例如把 `spawn("boss")` 改为 `spawn("boss_v2")`，不得改变 `spawn("phases")` 的输出
- `name` 必须是非空 `str`；非 `str` 抛 `TypeError`，空字符串抛 `ValueError`；命名规范见 §4

派生算法（MVP 固定实现；改动视为确定性破坏）：

初始化时保存 `canonical_seed`：root 为原始 int，child 为派生 int。`spawn` 始终基于当前实例的 `canonical_seed`，而不是当前 MT 状态。

```python
import hashlib

payload = (
    b"toy_engine.SeededRng.v1\0"
    + str(self._seed).encode("ascii")
    + b"\0"
    + name.encode("utf-8")
)
child_seed = int.from_bytes(
    hashlib.blake2b(payload, digest_size=8).digest(),
    "little",
)
return SeededRng(child_seed)
```

> 选 BLAKE2b 而非 Python 内置 `hash()`，是因为后者受 `PYTHONHASHSEED` 环境变量影响，会破坏跨进程确定性。

## 4. 命名约定

子流命名空间用 snake_case，**和模块/系统对齐**：

```
"fish_spawner"      # spawner.py 的鱼类生成
"fish_ai"           # 鱼群 AI 抖动
"boss_ai"           # Boss 状态机
"phases"            # LevelGenerator 的 PhaseConfig 采样（fish-doc 04 §7）
"boss"              # LevelGenerator 的 BossConfig 采样；不同于运行时 "boss_ai"
"visuals"           # 渲染层抖动（如鱼颜色色相 ±15°）—— 必须和逻辑层隔离
```

> **强烈约定**：渲染层/视觉层任何随机都必须走自己独立的子流，不能消耗逻辑层 RNG，否则关掉/打开渲染会破坏确定性。

## 5. 与 World 的耦合点

`World.__init__(level_config, seed)` 内部：

```python
self.rng = SeededRng(seed)
self.spawner_rng = self.rng.spawn("fish_spawner")
self.boss_rng    = self.rng.spawn("boss_ai")
# 渲染层在 Renderer 侧另起 SeededRng(seed).spawn("visuals")
```

## 6. 禁用全局随机的实施方式

- 代码审查/CI：除 `toy_engine/rng.py` 自身和测试夹具外，禁止匹配 `\brandom\.(random|uniform|randint|choice|gauss|shuffle)\(`、`\bnumpy\.random\b`、`\bnp\.random\b` 的直接调用。
- pytest：在业务测试入口 monkeypatch `random` 模块全局函数和可选的 `numpy.random` 入口为“调用即失败”；不要 patch `random.Random` 实例方法，避免误伤 `SeededRng` 实现。
- 运行约定：业务模块不直接 `import random` 做抽样；需要随机时显式接收 `SeededRng` 或其 `spawn(name)` 子流。

## DoD 验收清单

- [ ] 同 `seed` 创建两个 `SeededRng`，对相同操作序列产生完全一致的输出
- [ ] `spawn("a")` 与 `spawn("b")` 输出独立（无消耗干扰）
- [ ] 将某个子流从 `spawn("b")` 重命名为 `spawn("b2")` 不影响 `spawn("a")` 输出
- [ ] `spawn("a")` 多次得到等价子流
- [ ] 在 `PYTHONHASHSEED=random` 下跨进程结果仍然一致
- [ ] `get_state / set_state` 往返后，后续随机序列与后续 `spawn` 派生都一致
- [ ] `choice([])`、生成器输入、`gauss(..., 0)`、`seed > 2**64` 等边界行为有单测
- [ ] CI/pytest 能发现业务代码对 `random.*` / `numpy.random` 的误用
- [ ] 单元测试覆盖以上所有条目

## 未决问题

- 是否暴露 `numpy` 风格 API（`uniform(low, high, size)` 返回数组）？MVP **不做**，业务无 numpy 需求。

# 04 — Recorder（录像）

> 父文档：[00-overview.md](00-overview.md) ｜ 关联：[fish-doc 07 §3](../../fish-doc/mvp/07-test-harness.md)、[03-input.md](03-input.md)、[01-rng.md](01-rng.md)

## 1. 核心原则

> **只录输入，不录状态。** 回放依赖确定性 = `(seed, level_config, input_frames)` 三元组在新进程中重跑出**逐帧一致**的 World。

这也意味着：**任何破坏确定性的改动（隐式全局 RNG、读 wall-clock、字典遍历顺序依赖等）都会让旧录像作废**。引擎在 `tools/run_headless.py --determinism-check` 中提供机制保护（[08-tools.md §5](08-tools.md)）。

## 2. API

```python
from dataclasses import dataclass
from os import PathLike
from typing import Callable, Generic, TypeVar

from toy_engine.input import InputFrame

ConfigT = TypeVar("ConfigT")  # 业务自定义的 LevelConfig 类型；引擎不限制其结构

class Recorder(Generic[ConfigT]):
    def __init__(self, level_config: ConfigT, seed: int | None = None, engine_version: str = "0.1.0", config_serializer: Callable[[ConfigT], dict] | None = None) -> None: ...
    def record(self, frame_idx: int, input_frame: InputFrame) -> None: ...
    def save(self, path: str | PathLike[str], gzip: bool | None = None) -> None: ...
    @classmethod
    def load(cls, path: str | PathLike[str], config_deserializer: Callable[[dict], ConfigT] | None = None, *, strict_hash: bool = True) -> "Recording[ConfigT]": ...

@dataclass
class Recording(Generic[ConfigT]):
    level_config: ConfigT
    seed: int
    frames: list[InputFrame]
    config_hash: str
    engine_version: str
    meta: dict          # 附加元信息：录制时间、玩家来源（human/bot/replay）等
    file_config_hash: str | None = None  # 仅 in-memory诊断字段，不参与 save / wire
```

兼容性与语义：

- `Recorder(level_config)` 必须可用；当 `seed is None` 时实现从 `level_config.seed` 读取，若不存在则抛 `ValueError`。显式传入 `seed` 时以参数为准。
- 一个 `Recorder` 实例只录**一局**。`record()` 要求 `frame_idx` 从 `0` 开始、严格递增；`save()` 后实例冻结，继续 `record()` 抛 `RuntimeError`。
- 第一帧必须写入，即使它等于静止输入；否则全程静止的合法录像会被误判为空。
- 文件内 `frames` 可以是稀疏变化点；`Recorder.load()` 返回的 `Recording.frames` 必须是按帧号索引的**稠密** `list[InputFrame]`，可直接传给 `ReplayInput(rec.frames)`。
- `load()` 返回 `Recording` 是 [fish-doc progress.md](../../fish-doc/mvp/progress.md) 契约 #5 的增量；若历史调用方需要旧式二元组，可显式使用 `(rec.level_config, rec.frames)`。
- `load(..., strict_hash=True)`（默认）行为与原有实现一致：重算 hash 不匹配时抛 `ConfigDriftError`。`strict_hash=False` 时，hash 不匹配仅发 `ConfigDriftWarning(UserWarning)`并继续加载；`Recording.config_hash` 取**重算值**（与当前 `config` 一致），原文件中记录的 hash 保留到 `Recording.file_config_hash`。`file_config_hash` 只是 in-memory 诊断字段，**不入 wire / 不参与 save**。`tools/replay.py --force` 底层走这条路径（见 [08-tools.md §6](08-tools.md)）。

## 3. 文件格式

JSON（`.json` 或 `.json.gz`），结构：

```json
{
  "engine_version": "0.1.0",
  "seed": 12345,
  "config_hash": "sha256:ab3f...",
  "config": { "...": "由业务 serializer 决定的自描述字典" },
  "meta": {
    "recorded_at": "2026-04-27T12:34:56Z",
    "source": "human",
    "duration_frames": 5230
  },
  "frames": [
    { "i": 0,    "dir": null,        "dash": false },
    { "i": 1,    "dir": [1.0, 0.0],  "dash": false },
    { "i": 1234, "dir": [0.7, -0.7], "dash": false }
  ]
}
```

顶层字段固定如下；MVP 不接受未声明顶层字段静默生效。

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `engine_version` | 是 | `str` | 录制时的引擎语义版本 |
| `seed` | 是 | `int` | 构造 `World(level_config, seed)` 使用的随机种子 |
| `config_hash` | 是 | `str` | `sha256:<hex>`，见 §3.2 |
| `config` | 是 | `dict` | `LevelConfig` 的 JSON 原生表示；字段名使用 `config`，加载后映射为 `Recording.level_config` |
| `meta` | 是 | `dict` | 至少包含 `duration_frames: int`；其它字段只作诊断信息 |
| `frames` | 是 | `list[dict]` | 输入变化点列表，按 `i` 严格递增 |

帧字段与 [03-input.md](03-input.md) 的 `InputFrame` 序列化约定对齐。内存中 `InputFrame.desired_dir` 的 canonical 类型为 `Vec2 | None`；文件中的 `dir` 是 wire format，仍固定写成 `null` 或 `[x, y]` JSON 数组。`Recording.frames` 中对应 `dir` 的值在 `load()` 后已还原为 `Vec2`，不是 tuple。

| 字段 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `i` | 是 | `int` | 帧号，第一条必须是 `0` |
| `dir` | 是 | `null` 或 `[float, float]`（wire） | 对应 `InputFrame.desired_dir`；加载时 JSON 数组还原为 `Vec2` |
| `dash` | 是 | `bool` | 对应 `InputFrame.dash` |

文件名与 gzip 识别：

- 普通 JSON 建议后缀 `.json`，gzip JSON 建议后缀 `.json.gz`。
- `save(path, gzip=None)` 时按后缀是否为 `.gz` 自动决定；显式 `gzip=True/False` 时按参数决定。
- `load()` 不信任后缀，读取文件头两个字节；魔数 `0x1f 0x8b` 走 gzip，否则按普通 UTF-8 JSON 读取。

### 3.1 帧压缩约定

- **只在输入变化时写文件**：`record(i, frame)` 内部比较与上一帧的差异，相同则不追加变化点；第一帧永远写入
- 回放加载时按 `meta.duration_frames` 展开：`frames[k].i` 到下一变化点之间重复上一帧，最终得到稠密 `list[InputFrame]`
- 这能把"鼠标静止 3 秒"压缩到 1 行，文件体积下降一两个数量级
- `gzip=True` 时再走一次外层 gzip（10 分钟 × 60fps = 36000 帧：全量 JSON 约 2~4MB；变化点 JSON 常见 < 1MB；gzip 后常见 50~300KB）

### 3.2 `config_hash` 的用途

```python
raw_config = config_serializer(level_config) if config_serializer else to_jsonable(level_config)
canonical = json.dumps(
  raw_config,
  sort_keys=True,
  separators=(",", ":"),
  ensure_ascii=False,
  allow_nan=False,
)
config_hash = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

约束：

- hash 只基于文件中的 `config` 字段计算，不包含 `meta`、`frames`、`engine_version`。
- `config_serializer` 必须输出 JSON 原生类型：`dict/list/str/int/float/bool/None`。未提供 serializer 时，引擎默认 `to_jsonable()` 递归支持 dataclass、tuple/list、dict、`Enum.name` key 与基础类型；遇到未知对象必须抛 `TypeError`，不能用 `str(obj)` 静默糊弄。
- `load()` 先对原始 `config` 重算 hash；若与文件内 `config_hash` 不匹配，抛 `ConfigDriftError`，`tools/replay.py --force` 才可忽略。这是录像配置被编辑、损坏或 serializer 规范漂移的早期预警。

### 3.3 `engine_version`

引擎自身版本号常量，采用 semver：

- `MAJOR`：破坏录像兼容性的输入/循环/随机/物理语义变更，必须递增。
- `MINOR`：向后兼容的字段追加或工具增强。
- `PATCH`：不改变确定性语义的修复。

回放时若 `MAJOR` 不一致 → `EngineVersionWarning`（不抛错；实际差异由 `--determinism-check` 或 `tools/replay.py --headless` 的 state hash 比对兜底）。

## 4. 与 fish / GameLoop 的对接

```python
recorder = Recorder(level_config=cfg, seed=42, config_serializer=cfg_to_dict)

def on_frame(state):
    recorder.record(state.frame_idx, state.last_input_frame)
    ...

GameLoop(world, KeyboardMouseInput(), on_frame=on_frame).run_realtime()
recorder.save("recordings/run_42.json.gz", gzip=True)
```

回放：

```python
rec = Recorder.load("recordings/run_42.json.gz", config_deserializer=cfg_from_dict)
world = World(rec.level_config, rec.seed)
GameLoop(world, ReplayInput(rec.frames)).run_headless()
```

## 5. 错误模式

| 异常 | 触发 | 处理 |
|---|---|---|
| `ConfigDriftError` | `config_hash` 不匹配 | 抛出，附带新旧 hash；`tools/replay.py --force` 可忽略 |
| `EngineVersionWarning` | 主版本号不一致 | warning，不阻塞 |
| `EmptyRecordingError` | `frames == []` | save 时检测，避免产生废录像 |

## 6. **不做**的事

- 不录 `world_state` 快照，也不在录像内保存周期性 `World.snapshot_hash()` checkpoint；MVP 只在 `tools/run_headless.py --determinism-check` / `tools/replay.py --headless` 端到端使用 state hash
- 不录渲染层数据（颜色抖动等）——渲染层有自己独立的 `SeededRng("visuals")` 子流，回放时用同样 seed 自然一致
- 不做"剪辑/拼接"工具
- 不支持二进制格式（JSON 足以；可读性 > 体积）

## DoD 验收清单

- [ ] 录制一局 60s（约 3600 帧）的人类游玩，文件 < 200KB（gzip 后 < 30KB）
- [ ] 录制一局 10min（约 36000 帧）的人类游玩，普通 JSON 和 gzip JSON 体积落在 §3.1 估算范围内，且保存过程使用 `json.dump`/gzip 文件流而不是拼接巨型字符串
- [ ] `Recording` 在新 Python 进程加载后驱动 `World` 跑出与原局逐帧一致的 state hash
- [ ] 修改录像文件中 `config` 一个字段但不更新 `config_hash` 后，回放抛 `ConfigDriftError`
- [ ] `--determinism-check` 通过（同 seed 跑两次 state hash 一致，见 [08-tools.md §5](08-tools.md)）
- [ ] 录像文件**不含**任何浮点精度依赖问题（dir 用 stdlib JSON 原样写 `[float, float]`、`allow_nan=False` 禁止 NaN/Inf、加载后还原为 `Vec2`）

## 未决问题

- 是否要加"心跳 state hash"（每 60 帧存一个）以便发现录像中段失效？MVP **不做**，靠端到端 hash 比较即可。
- 录像目录命名规范由 fish 决定，引擎不管（`tools/run_headless.py` 默认 `--out` 路径见 [08-tools.md](08-tools.md)）。

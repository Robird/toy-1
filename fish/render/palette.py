"""fish/render/palette.py — fish 业务调色板（M3-08）。

颜色常量来自 fish-doc/mvp/05-visuals.md §1（"锁死，不许 subagent 自由发挥"）。
此处构造一个 :class:`toy_engine.render.Palette` 实例 ``FISH_PALETTE`` 集中
保存；所有渲染函数应通过 palette[name] 读取，**禁止**在 visuals.py 里硬编码
RGB（fish-doc/05 DoD 第 1 条）。

命名规则与文档对齐：
- 背景层：``bg_deep`` / ``bg_mid`` / ``bg_shallow`` / ``bg_foam`` / ``bg_highlight``
- 角色色：``role_player`` / ``role_prey`` / ``role_peer`` / ``role_threat`` /
  ``role_boss``
- UI：``ui_text`` / ``ui_bar_bg`` / ``ui_bar_fill`` / ``ui_warning``
- Boss 状态附加色：``boss_eye_patrol`` / ``boss_eye_chase`` / ``boss_eye_charge``
  / ``boss_eye_stunned``

Tier→主色映射 ``tier_to_role_name(tier, player_tier)`` 是辅助函数，便于
visuals.py 按"玩家相对档位"挑色（prey/peer/threat）。
"""

from __future__ import annotations

from toy_engine.render import Palette

__all__ = ["FISH_PALETTE", "tier_to_role_name", "build_fish_palette"]


# fish-doc/mvp/05-visuals.md §1 锁定值。
# UI / Boss 状态色为 MVP 派生（基于文档语义微调，未在 §1 列出）。
_FISH_PALETTE_COLORS: dict[str, tuple[int, int, int]] = {
    # 背景三层（fish-doc/05 §1）
    "bg_deep": (11, 29, 58),         # PALETTE_DEEP
    "bg_mid": (21, 68, 107),         # PALETTE_MID
    "bg_shallow": (43, 140, 190),    # PALETTE_SHALLOW
    "bg_foam": (126, 200, 197),      # PALETTE_FOAM
    "bg_highlight": (232, 246, 243), # PALETTE_HIGHLIGHT

    # 角色色（fish-doc/05 §1）
    "role_player": (255, 215, 0),    # ROLE_PLAYER 金
    "role_prey": (126, 200, 197),    # ROLE_PREY 青绿
    "role_peer": (240, 196, 25),     # ROLE_PEER 琥珀
    "role_threat": (220, 80, 60),    # ROLE_THREAT 红
    "role_boss": (60, 20, 80),       # ROLE_BOSS 深紫

    # UI（MVP 派生：基于 bg_highlight / role_threat 配色）
    "ui_text": (232, 246, 243),       # = bg_highlight；fish-doc/05 §7 "极简"
    "ui_bar_bg": (21, 68, 107),       # = bg_mid 半透
    "ui_bar_fill": (126, 200, 197),   # = bg_foam（成长进度青绿）
    "ui_bar_boss": (220, 80, 60),     # boss HP 用威胁色
    "ui_warning": (220, 80, 60),      # Tier-4 警示 = role_threat
    "ui_dim": (60, 80, 100),          # 灰阶遮罩（终态用）

    # Boss 双眼（fish-doc/05 §4 各状态颜色）
    "boss_eye_patrol": (240, 196, 25),   # 黄
    "boss_eye_chase": (255, 140, 0),     # 橙
    "boss_eye_charge": (220, 50, 50),    # 红
    "boss_eye_stunned": (170, 170, 170), # 灰
}


def build_fish_palette() -> Palette:
    """构造一个新的 ``Palette``（避免被外部 mutate 后污染全局缓存）。"""
    return Palette(_FISH_PALETTE_COLORS)


# 全局共享实例：渲染热路径用；测试可以另起一份。
FISH_PALETTE: Palette = build_fish_palette()


def tier_to_role_name(fish_tier: int, player_tier: int) -> str:
    """按"玩家相对档位"返回该 fish 的主色名。

    裁决 #13：``can_eat = a.tier >= b.tier - 1``，即玩家可吃 ``tier <= player+1``。
    但同 tier 在 ``CollisionSystem`` 中优先走 bounce，因此应标为 peer 而非 prey。
    据此挑色：
        - ``fish.tier == player.tier``      → ``role_peer``（琥珀，同级紧张 / 弹开）
        - ``fish.tier <= player.tier + 1``  → ``role_prey``（青绿，可吃，含以小搏大一档）
        - 其余                                → ``role_threat``（红，威胁）

    当 ``player_tier == 4`` 且普通鱼 tier ∈ [1,4] 时，不会返回 threat：
    Tier-1..3 是 prey，Tier-4 是 peer。
    """
    if fish_tier == player_tier:
        return "role_peer"
    if fish_tier <= player_tier + 1:
        return "role_prey"
    return "role_threat"

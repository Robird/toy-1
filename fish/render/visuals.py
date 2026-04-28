"""fish/render/visuals.py — 几何卡通绘制（M3-08）。

只通过 :class:`toy_engine.render.GeoCanvas` 与 :class:`toy_engine.render.Palette`
作画；**不**直接 import pygame。所有颜色名走 ``palette[name]``，禁止硬编码
RGB（fish-doc/05 DoD 第 1 条）。

本模块函数签名遵循"纯函数式渲染"约定：
- 不持有状态
- 输入是 snapshot/实体的只读属性 + canvas + palette + (可选 font)
- 不写回任何对象

不在本步实现：拖尾粒子 / 屏震 / 慢镜 / squash（M3-09 手感）；
本步只画静态外形 + 简单 UI。
"""

from __future__ import annotations

import math
from typing import Any

from toy_engine.render import GeoCanvas, Palette

from fish.config.constants import (
    BOSS_RADIUS,
    PLAYER_RADIUS,
    TIER_GIANT,
    WORLD_H,
    WORLD_W,
)
from fish.render.palette import tier_to_role_name


__all__ = [
    "draw_player",
    "draw_fish",
    "draw_boss",
    "draw_parallax_background",
    "draw_ui",
    "draw_game_over",
]


# ---------------------------------------------------------------------------
# 内部 helper：卡通鱼形（fish-doc/05 §3 模板）
# ---------------------------------------------------------------------------


def _fish_body_length(radius: float) -> float:
    """统一把"碰撞半径"换算成"鱼身长度（视觉）"。

    碰撞 radius 取的是身体的"半短轴"概念；视觉鱼身按 length:width = 2:1 渲染，
    因此 length = 4 * radius（直径 * 2）。
    """
    return max(4.0, float(radius) * 4.0)


def _draw_cartoon_fish(
    canvas: GeoCanvas,
    palette: Palette,
    *,
    pos: tuple[float, float],
    heading: float,
    radius: float,
    role_color_name: str,
    t_seconds: float,
    phase_offset: float = 0.0,
    flip_marker: bool = False,
    squash: tuple[float, float] = (1.0, 1.0),
) -> None:
    """画一条标准卡通鱼（fish-doc/05 §3）。

    Parameters
    ----------
    pos: 世界坐标。
    heading: 朝向（弧度，0=+x）。
    radius: 碰撞半径；视觉长度 = 4*radius。
    role_color_name: ``role_player`` / ``role_prey`` / ``role_peer`` / ``role_threat``。
    t_seconds: 全局动画时间，用于尾巴摆动相位（``sin(t*6 + phase)``）。
    phase_offset: 同 tier 多条鱼用 eid 抖动相位；外部传入 ``eid * 0.4`` 之类。
    flip_marker: True 时在身体上叠一个小三角作"反向标记"（FLEE 用）。
    """
    base_rgb = palette[role_color_name]
    light_rgb = palette.lighten(role_color_name, 0.40)
    dark_rgb = palette.darken(role_color_name, 0.40)

    length = _fish_body_length(radius)
    width = length * 0.5
    try:
        sx, sy = squash
        sx = float(sx)
        sy = float(sy)
    except (TypeError, ValueError):
        sx, sy = 1.0, 1.0
    if not math.isfinite(sx) or sx <= 0.0:
        sx = 1.0
    if not math.isfinite(sy) or sy <= 0.0:
        sy = 1.0
    length = length * sx
    width = width * sy

    # 1. 椭圆身体（线性渐变 dark→light，沿短轴）
    canvas.gradient_ellipse(
        center=pos, length=length, width=width, angle=heading,
        color_a=dark_rgb, color_b=light_rgb, mode="linear", steps=8,
    )

    # 2. 三角尾巴：附在身体尾端 (-length/2)，张角 60°，
    #    绕尾根旋转 sin(t*6 + phase) * 18°（弧度 ≈ 0.314）
    sway_rad = math.sin(t_seconds * 6.0 + phase_offset) * (18.0 * math.pi / 180.0)
    tail_root_local = (-length * 0.5, 0.0)
    tail_len = length * 0.35
    half_spread = math.tan(math.radians(30.0)) * tail_len  # 60° 张角 → 半角 30°
    # 在 tail_root 局部坐标系内建尾三角，然后整体绕 tail_root 旋转 sway。
    cs, sn = math.cos(sway_rad), math.sin(sway_rad)
    def _rot_around_root(lx: float, ly: float) -> tuple[float, float]:
        # 先平移到尾根原点，旋转，平移回 fish 局部
        rx = (lx - tail_root_local[0]) * cs - (ly - tail_root_local[1]) * sn + tail_root_local[0]
        ry = (lx - tail_root_local[0]) * sn + (ly - tail_root_local[1]) * cs + tail_root_local[1]
        return (rx, ry)
    tail_pts_local = [
        tail_root_local,
        _rot_around_root(-length * 0.5 - tail_len, +half_spread),
        _rot_around_root(-length * 0.5 - tail_len, -half_spread),
    ]
    canvas.rotated_polygon(pos, tail_pts_local, heading, dark_rgb)

    # 3. 上下鳍：半透明小三角
    fin_len = length * 0.20
    fin_h = width * 0.45
    fin_top_local = [
        (-length * 0.05, -width * 0.45),
        (-length * 0.05 - fin_len, -width * 0.45 - fin_h),
        (length * 0.10, -width * 0.45),
    ]
    fin_bot_local = [(p[0], -p[1]) for p in fin_top_local]
    canvas.rotated_polygon(pos, fin_top_local, heading, base_rgb, alpha=120)
    canvas.rotated_polygon(pos, fin_bot_local, heading, base_rgb, alpha=120)

    # 4. 眼：白色实心圆 r=length*0.08，内部黑点 r*0.5
    #    位置：身体前 1/3、上 1/4 → 局部 (length*0.18, -width*0.18)
    eye_local = (length * 0.18, -width * 0.18)
    cs_h, sn_h = math.cos(heading), math.sin(heading)
    eye_world = (
        pos[0] + eye_local[0] * cs_h - eye_local[1] * sn_h,
        pos[1] + eye_local[0] * sn_h + eye_local[1] * cs_h,
    )
    eye_r = max(2.0, length * 0.08)
    canvas.circle(eye_world, eye_r, palette["bg_highlight"])
    canvas.circle(eye_world, eye_r * 0.5, palette["bg_deep"])

    # 5. 高光弧线（身体上半部一段细弧线，alpha 80）
    #    用 arc(start_angle, end_angle) 在椭圆上端画
    canvas.arc(
        center=pos, length=length * 0.85, height=width * 0.85, angle=heading,
        start_angle=math.radians(20.0), end_angle=math.radians(160.0),
        color=palette["bg_highlight"], stroke_width=1, alpha=80,
    )

    # FLEE 反向标记（极简：在尾部加一个小点，告诉玩家"这条在跑")
    if flip_marker:
        marker_local = (-length * 0.30, 0.0)
        marker_world = (
            pos[0] + marker_local[0] * cs_h - marker_local[1] * sn_h,
            pos[1] + marker_local[0] * sn_h + marker_local[1] * cs_h,
        )
        canvas.circle(marker_world, max(1.5, length * 0.05), palette["bg_highlight"], alpha=180)


# ---------------------------------------------------------------------------
# Player / Fish / Boss
# ---------------------------------------------------------------------------


def draw_player(
    canvas: GeoCanvas,
    player: Any,
    palette: Palette,
    *,
    t_seconds: float = 0.0,
    squash: tuple[float, float] = (1.0, 1.0),
) -> None:
    """画玩家鱼。

    ``squash`` 为可选 (scale_x, scale_y)；M3-09 手感层会传入「高速变细」的
    形变。默认 (1.0, 1.0) 保证向后兼容。
    """
    if player is None or not getattr(player, "alive", True):
        # 死亡瞬间仍画一帧（提示玩家"被吞"），调用方决定是否短路
        if player is None:
            return
    radius = float(getattr(player, "radius", 0.0)) or float(
        PLAYER_RADIUS[max(0, min(int(getattr(player, "tier", 0)), len(PLAYER_RADIUS) - 1))]
    )
    _draw_cartoon_fish(
        canvas,
        palette,
        pos=(float(player.pos.x), float(player.pos.y)),
        heading=float(getattr(player, "heading", 0.0)),
        radius=radius,
        role_color_name="role_player",
        t_seconds=t_seconds,
        phase_offset=0.0,
        squash=squash,
    )


def draw_fish(
    canvas: GeoCanvas,
    fish: Any,
    palette: Palette,
    *,
    player_tier: int = 0,
    t_seconds: float = 0.0,
) -> None:
    """画一条 NPC 鱼。颜色由"玩家相对档位"决定（prey/peer/threat）。

    FLEE 状态加一个尾点小标记，便于玩家直觉判断"这条在跑"。
    """
    if fish is None:
        return
    # 修正：玩家 tier=1 时，tier=1 的 NPC 应为 role_prey（可吃），而非 role_peer（同级弹开）。
    fish_tier = int(getattr(fish, "tier", 1))
    pt = int(player_tier)
    if pt >= 1 and fish_tier == pt:
        role = "role_prey"
    else:
        role = tier_to_role_name(fish_tier, pt)
    state_name = ""
    state = getattr(fish, "state", None)
    if state is not None:
        state_name = getattr(state, "name", str(state))
    flip = state_name == "FLEE"
    _draw_cartoon_fish(
        canvas,
        palette,
        pos=(float(fish.pos.x), float(fish.pos.y)),
        heading=float(getattr(fish, "heading", 0.0)),
        radius=float(fish.radius),
        role_color_name=role,
        t_seconds=t_seconds,
        phase_offset=float(int(getattr(fish, "eid", 0)) % 16) * 0.4,
        flip_marker=flip,
    )


def draw_boss(
    canvas: GeoCanvas,
    boss: Any,
    palette: Palette,
    *,
    t_seconds: float = 0.0,
) -> None:
    """画 Boss。

    fish-doc/05 §4：单独函数；3~4 段贝塞尔轮廓的不规则椭圆 + 双眼随状态变色 +
    嘴每 1.5s 张合一次 + STUNNED 时头顶 3 颗旋转星 + ENRAGED/REVENGE 红边。

    MVP 简化：贝塞尔用 ``canvas.gradient_ellipse(mode="linear")`` + 描边一圈
    `arc` 表示"轮廓不规则感"（避免 boss 形状抖动 / 不需要预生成种子）；
    ENRAGED 在外侧叠一圈红色低透明描边；CHARGE_WINDUP 在前方一段红色短弧
    标"准备冲撞"。
    """
    if boss is None or not getattr(boss, "alive", True):
        return
    pos = (float(boss.pos.x), float(boss.pos.y))
    heading = float(getattr(boss, "heading", 0.0))
    state = getattr(boss, "state", None)
    state_name = getattr(state, "name", str(state)) if state is not None else "PATROL"
    enraged = bool(getattr(boss, "enraged", False))
    radius = float(getattr(boss, "radius", BOSS_RADIUS))

    length = radius * 2.4
    width = radius * 1.6

    # 主体（深紫渐变）
    canvas.gradient_ellipse(
        center=pos,
        length=length,
        width=width,
        angle=heading,
        color_a=palette.darken("role_boss", 0.40),
        color_b=palette.lighten("role_boss", 0.30),
        mode="linear",
        steps=12,
    )

    # 进场未结束：全身淡化（用一圈半透明 deep 色描边模拟"渐显"）
    intro_remaining = float(getattr(boss, "intro_remaining", 0.0))
    if intro_remaining > 0.0:
        canvas.ellipse(
            center=pos, length=length * 1.05, height=width * 1.05, angle=heading,
            color=palette["bg_deep"], stroke_width=2, alpha=160,
        )

    # ENRAGED：外侧红边（也覆盖 fish-doc/05 §4 "PHASE_REVENGE 偏色"的 MVP 替代）
    if enraged:
        canvas.ellipse(
            center=pos, length=length * 1.10, height=width * 1.10, angle=heading,
            color=palette["role_threat"], stroke_width=3, alpha=200,
        )

    # 双眼（按状态变色；位置在身体前 1/3、上下各一只）
    eye_color = palette["boss_eye_patrol"]
    if state_name == "CHASE":
        eye_color = palette["boss_eye_chase"]
    elif state_name in ("CHARGE_WINDUP", "CHARGE"):
        eye_color = palette["boss_eye_charge"]
    elif state_name == "STUNNED":
        eye_color = palette["boss_eye_stunned"]
    cs_h, sn_h = math.cos(heading), math.sin(heading)
    short_side = min(canvas.size)
    eye_r = max(3.0, short_side * 0.015)  # 屏短边 1.5%
    for sign in (-1.0, +1.0):
        eye_local = (length * 0.28, sign * width * 0.20)
        eye_world = (
            pos[0] + eye_local[0] * cs_h - eye_local[1] * sn_h,
            pos[1] + eye_local[0] * sn_h + eye_local[1] * cs_h,
        )
        canvas.circle(eye_world, eye_r, palette["bg_highlight"])
        canvas.circle(eye_world, eye_r * 0.6, eye_color)
        # CHARGE_WINDUP 给眼外发光（emphasis）
        if state_name == "CHARGE_WINDUP":
            canvas.circle(eye_world, eye_r * 1.6, eye_color, width=1, alpha=120)

    # 嘴：每 1.5s 张合一次。张开 0.4s，露出 3 颗白色三角"牙"。
    mouth_phase = (t_seconds % 1.5) / 1.5
    mouth_open = mouth_phase < 0.27
    mouth_local = (length * 0.46, 0.0)
    mouth_world = (
        pos[0] + mouth_local[0] * cs_h - mouth_local[1] * sn_h,
        pos[1] + mouth_local[0] * sn_h + mouth_local[1] * cs_h,
    )
    if mouth_open:
        # 三颗牙：以 mouth_world 为中心，在朝向方向上铺开
        for k in (-1.0, 0.0, 1.0):
            tooth_local = (length * 0.42, k * width * 0.10)
            t_world = (
                pos[0] + tooth_local[0] * cs_h - tooth_local[1] * sn_h,
                pos[1] + tooth_local[0] * sn_h + tooth_local[1] * cs_h,
            )
            canvas.circle(t_world, max(2.0, eye_r * 0.6), palette["bg_highlight"])
    else:
        canvas.line(
            (mouth_world[0] - 4 * cs_h, mouth_world[1] - 4 * sn_h),
            (mouth_world[0] + 4 * cs_h, mouth_world[1] + 4 * sn_h),
            palette["bg_deep"], width=2,
        )

    # CHARGE_WINDUP：前方红色短线段标"准备冲撞"（M3-09 会换粒子，但这里给个静态提示）
    if state_name == "CHARGE_WINDUP":
        front_world = (
            pos[0] + cs_h * length * 0.9,
            pos[1] + sn_h * length * 0.9,
        )
        canvas.line(pos, front_world, palette["role_threat"], width=2, alpha=180)

    # STUNNED：头顶 3 颗旋转星星（圆点替代）
    if state_name == "STUNNED":
        n_stars = 3
        ring_r = radius * 0.9
        for i in range(n_stars):
            ang = t_seconds * 3.0 + i * (2.0 * math.pi / n_stars)
            sx = pos[0] + math.cos(ang) * ring_r
            sy = pos[1] - radius * 0.6 + math.sin(ang) * (ring_r * 0.4)
            canvas.circle((sx, sy), max(2.0, eye_r * 0.7), palette["boss_eye_patrol"])


# ---------------------------------------------------------------------------
# 视差背景
# ---------------------------------------------------------------------------


def draw_parallax_background(
    canvas: GeoCanvas,
    palette: Palette,
    *,
    frame_count: int,
    player_offset: tuple[float, float] | None = None,
) -> None:
    """画三层视差背景（fish-doc/05 §5）。

    MVP 简化：
    - Far：径向渐变 deep→mid（`gradient_ellipse(mode="radial")` 覆盖整屏）
    - Mid：3 丛贝塞尔海草，控制点随 ``frame_count`` 摆动；按 player_offset*0.4
      做小幅水平视差（最大 30px，fish-doc/05 §5 末段）
    - Near：随机分布的小气泡，随 frame_count 向上漂；按 player_offset*1.0 视差
    """
    w, h = canvas.size

    t = frame_count / 60.0
    px_off, py_off = (player_offset or (0.0, 0.0))
    # 视差最大 30px（§5 末段）
    def _clamp30(v: float) -> float:
        if v > 30.0:
            return 30.0
        if v < -30.0:
            return -30.0
        return v
    far_dx = _clamp30(px_off * 0.1)
    far_dy = _clamp30(py_off * 0.1)
    mid_dx = _clamp30(px_off * 0.4)
    mid_dy = _clamp30(py_off * 0.4)
    near_dx = _clamp30(px_off * 1.0)
    near_dy = _clamp30(py_off * 1.0)

    # ---- Far：底色 + 径向渐变 ----
    canvas.clear(palette["bg_deep"])
    # 椭圆覆盖整屏，作"光井"效果；远层也按 0.1× 参与视差。
    canvas.gradient_ellipse(
        center=(w / 2.0 - far_dx, h / 2.0 - far_dy),
        length=int(w * 1.4), width=int(h * 1.4),
        angle=0.0,
        color_a=palette["bg_mid"], color_b=palette["bg_deep"],
        mode="radial", steps=10,
    )

    # ---- Mid：海草丛 ----
    n_seaweed = 5
    for i in range(n_seaweed):
        # 在 [50, w-50] 间均匀分布
        base_x = 50.0 + (w - 100.0) * (i + 0.5) / n_seaweed - mid_dx
        base_y = h - 8.0 - mid_dy
        height = h * 0.30 + (i * 17 % 50)
        sway = math.sin(t * 1.2 + i * 0.7) * 14.0
        tip = (base_x + sway, base_y - height)
        ctrl = (base_x + sway * 0.5 - 12.0, base_y - height * 0.5)
        # 二次贝塞尔
        canvas.bezier_quad(
            (base_x, base_y), ctrl, tip,
            palette["bg_foam"], width=3, samples=12, alpha=140,
        )

    # ---- Near：气泡 ----
    n_bubbles = 30
    for i in range(n_bubbles):
        # 用稳定的伪散布：(i*53 % w, ...)
        bx = (i * 53 % w) - near_dx
        seed_y = (i * 91 % h)
        # 漂浮：每个气泡按 frame 周期向上
        period = 200 + (i * 7 % 80)
        progress = (frame_count + i * 13) % period
        by = h - (progress / period) * h - near_dy
        # 左右轻微抖动
        bx += math.sin((frame_count + i * 11) * 0.05) * 4.0
        r = 2.0 + (i % 4)
        canvas.circle((bx, by), r, palette["bg_highlight"], alpha=80)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------


def _draw_progress_bar(
    canvas: GeoCanvas, palette: Palette,
    *, x: float, y: float, w: float, h: float,
    ratio: float,
    bg_name: str = "ui_bar_bg",
    fill_name: str = "ui_bar_fill",
) -> None:
    if ratio < 0.0:
        ratio = 0.0
    elif ratio > 1.0:
        ratio = 1.0
    canvas.rect((x, y, w, h), palette[bg_name], alpha=200)
    canvas.rect((x, y, w * ratio, h), palette[fill_name])


def draw_ui(
    canvas: GeoCanvas,
    snapshot: dict,
    palette: Palette,
    font,
) -> None:
    """画顶部 HUD（fish-doc/05 §7 极简版）。

    左上：玩家 Tier 徽章（5 格进度条）+ 当前 exp / next 阈值
    右上：关卡时间 + 当前 Phase 名
    顶部居中：事件提示（Tier-4 警示 / 进入 BOSS 等）
    Boss HP：BOSS 阶段右下角
    """
    if font is None:
        return  # 测试可能传 None 跳过文字
    w, h = canvas.size

    # ---- 左上：Tier 徽章 + exp 进度 ----
    tier = int(snapshot.get("player_tier", 0))
    exp = float(snapshot.get("player_exp", 0.0))
    # 用 TIER_THRESHOLDS 计算下一阈值
    from fish.config.constants import TIER_THRESHOLDS
    cur_th = TIER_THRESHOLDS[min(tier, len(TIER_THRESHOLDS) - 1)]
    if tier + 1 < len(TIER_THRESHOLDS):
        next_th = TIER_THRESHOLDS[tier + 1]
        denom = max(1.0, float(next_th - cur_th))
        ratio = (exp - cur_th) / denom
    else:
        next_th = cur_th
        ratio = 1.0
    canvas.text(f"Tier {tier}", (12, 10), palette["ui_text"], font, anchor="topleft")
    _draw_progress_bar(canvas, palette, x=12, y=36, w=180, h=12, ratio=ratio)
    canvas.text(
        f"{int(exp)}/{int(next_th)}",
        (200, 36), palette["ui_text"], font, anchor="topleft",
    )

    # ---- 右上：时间 + Phase ----
    elapsed = float(snapshot.get("elapsed_s", 0.0))
    phase = str(snapshot.get("phase", ""))
    canvas.text(
        f"{elapsed:5.1f}s",
        (w - 12, 10), palette["ui_text"], font, anchor="topright",
    )
    canvas.text(
        phase, (w - 12, 36), palette["ui_text"], font, anchor="topright",
    )

    # ---- 顶部居中：事件提示（优先 Tier-4 警示）----
    if bool(snapshot.get("tier4_warning", False)):
        canvas.text(
            "WARNING: Apex predator nearby!",
            (w // 2, 14), palette["ui_warning"], font, anchor="midtop",
        )

    # ---- Boss HP（snapshot.boss 非空时）----
    boss = snapshot.get("boss")
    if isinstance(boss, dict):
        bx = w - 200
        by = h - 36
        hp = int(boss.get("hp", 0))
        max_hp = max(1, int(boss.get("max_hp", 1)))
        canvas.text(
            f"BOSS  {hp}/{max_hp}",
            (bx, by - 18), palette["ui_text"], font, anchor="topleft",
        )
        _draw_progress_bar(
            canvas, palette,
            x=bx, y=by, w=180, h=14, ratio=hp / max_hp,
            fill_name="ui_bar_boss",
        )
        if bool(boss.get("enraged", False)):
            canvas.text(
                "ENRAGED",
                (bx + 90, by - 36), palette["ui_warning"], font, anchor="midtop",
            )


def draw_game_over(
    canvas: GeoCanvas,
    snapshot: dict,
    palette: Palette,
    font,
) -> None:
    """终态遮罩 + 大字。

    snapshot['game_result'] ∈ {'DEAD', 'VICTORY', 'TIMEOUT'} 任一时绘制。
    """
    if font is None:
        return
    result = snapshot.get("game_result")
    if result is None:
        return
    w, h = canvas.size
    # 半透明遮罩（用 ui_dim + alpha）
    canvas.rect((0, 0, w, h), palette["ui_dim"], alpha=160)
    title_color_name = {
        "DEAD": "role_threat",
        "VICTORY": "role_player",
        "TIMEOUT": "ui_text",
    }.get(str(result), "ui_text")
    title_text = {
        "DEAD": "YOU DIED",
        "VICTORY": "VICTORY",
        "TIMEOUT": "TIME OUT",
    }.get(str(result), str(result))
    canvas.text(
        title_text, (w // 2, h // 2 - 20),
        palette[title_color_name], font, anchor="center",
    )
    canvas.text(
        "Press ESC to quit",
        (w // 2, h // 2 + 28),
        palette["ui_text"], font, anchor="center",
    )

"""
合成大西瓜 (Suika / Merge Balls Game)
--------------------------------------
左右方向键 或 鼠标移动 —— 控制投放位置
空格键 或 鼠标左键 —— 投放小球
Tab 键 —— 拥有炸弹时切换到炸弹模式（再次按 Tab/右键 退出）
  · 炸弹模式下左键点击将引爆任意球（不加分）
  · 每累计 2000 分获得 1 枚炸弹，可叠加
Esc —— 优先退出炸弹模式；非炸弹模式下退出游戏
R 键 —— Game Over 后重新开始
"""

import pygame
import sys
import random
import math
import pymunk

from audio_utils import Timbre, concat_samples, generate_samples, make_sound, mix_samples, notes_to_samples, synthesize_sound
from audio_runtime import AudioRuntime, init_pygame_audio
from font_utils import load_font

# ──────────────────────────────────────
# 常量
# ──────────────────────────────────────
WIDTH, HEIGHT = 480, 750
FPS = 60

# 物理世界的重力加速度，单位近似为“像素/秒²”。
# 调大：下落更快，碰撞更重，更容易压实底部堆叠，但也会增加合并后的小幅震荡。
# 调小：整体更轻、更飘，堆叠压力变小，容器里会更容易出现松散悬空感。
GRAVITY = 1260.0

# 空间阻尼，会在每次 step 时对所有动态刚体的速度做统一衰减。
# 1.0 表示几乎不额外耗能；越小表示空气阻力/能量损失越明显。
# 调大：球会滚得更久、更活跃。
# 调小：球更快停稳，抖动更容易收敛，但也可能显得“发黏”。
SPACE_DAMPING = 0.92

# 约束求解迭代次数。Pymunk/Chipmunk 会在每个物理步内多次迭代接触约束，
# 用来处理“球不能互相穿透”“球不能穿墙”“摩擦如何生效”等问题。
# 调大：堆叠更稳、穿插更少，但 CPU 开销更高。
# 调小：性能更好，但多球堆叠时更容易轻微下陷或抖动。
SPACE_ITERATIONS = 30

# 每帧渲染里拆成多少个物理子步。
# 这比“每帧只 step 一次”更稳定，因为每次位移更短，碰撞更容易被及时处理。
# 调大：高速接触更稳定，穿透风险更低，但计算量线性上升。
# 调小：性能更省，但快速碰撞和密集堆叠更容易不稳。
PHYSICS_STEPS_PER_FRAME = 3

# 单个物理子步的 dt，和上面的子步数配套使用。
# 这里固定为 1 / (FPS * 子步数)，属于典型 fixed timestep 做法，
# 好处是同一套参数在不同机器上的行为更一致，手感也更容易调。
PHYSICS_DT = 1.0 / (FPS * PHYSICS_STEPS_PER_FRAME)

# 球与球、球与墙接触时的弹性系数。
# 越接近 1 越“弹”，越接近 0 越“闷”。
# Suika 这类堆叠合并游戏通常会用较小值，避免球来回弹跳导致局面不稳定。
BALL_ELASTICITY = 0.01

# 球表面的摩擦系数。
# 调大：球之间更不容易横向滑开，堆叠更“抓地”。
# 调小：球更容易滚动和滑落，画面更活跃，但塔状结构更难稳定。
BALL_FRICTION = 0.8

# 静态墙体和地板的弹性系数。
# 这里单独留出来，是为了以后如果想做“更弹的边墙”或“更软的地板”时可单独调。
WALL_ELASTICITY = 0.01

# 墙和地板的摩擦系数。
# 调大：落地后的横向速度更快被吃掉，球会更快停稳。
# 调小：球更容易在底部滚来滚去，手感会更滑。
WALL_FRICTION = 0.8

# 合并判定的额外容差，单位是像素。
# 两个同等级球的中心距离只要小于“半径和 + 这个容差”，就允许合并。
# 它不是物理参数，而是玩法参数：用来补偿离散步进带来的微小间隙，
# 避免明明已经贴在一起、视觉上应当合并，却因为数值误差没有触发。
MERGE_DISTANCE_SLOP = 0.5

# “基本静止”速度阈值的平方，用于危险线判定。
# 只有球已经足够慢，才会被视为“真正卡在危险线附近”，从而累计 game over 宽限帧。
# 之所以存平方值，是为了避免每帧开平方。
# 调大：更容易把慢速晃动中的球视为“已停稳”。
# 调小：必须几乎完全静止才算稳定，判定会更严格。
RESTING_SPEED_SQ = 900.0

WALL_THICKNESS = 12
WALL_LEFT = WALL_THICKNESS
WALL_RIGHT = WIDTH - WALL_THICKNESS
FLOOR_Y = HEIGHT - WALL_THICKNESS
DANGER_Y = 130          # 危险线高度
SPAWN_Y = 70            # 投放点高度
MOVE_SPEED = 6
DROP_COOLDOWN_FRAMES = 25
GAME_OVER_GRACE = 90    # 球超过危险线后的宽限帧数
CONTAINER_TOP = DANGER_Y - 10

# 释放点的额外横向安全边距。
# 即使球半径刚好允许贴边投放，也给它预留一点额外空间，
# 避免抖动、容差和投放微扰让新球在进入容器时擦到侧墙。
DROP_SIDE_MARGIN = 2.0

# 投放时保留轻微横向随机扰动，避免“完美垂直落柱”。
# 实际生成时会再次经过夹紧，因此不会把球抖进墙里。
DROP_X_JITTER = 1.0

# 球的等级配置: level -> (radius, color, name, score)
BALL_CONFIG = {
    1:  (16,  (220, 40,  40),   "樱桃",   1),
    2:  (22,  (240, 90,  90),   "草莓",   3),
    3:  (30,  (170, 50,  200),  "葡萄",   6),
    4:  (37,  (255, 160, 50),   "橙子",  10),
    5:  (45,  (255, 210, 20),   "柠檬",  15),
    6:  (53,  (40,  190, 60),   "猕猴桃", 21),
    7:  (62,  (255, 130, 170),  "桃子",  28),
    8:  (72,  (255, 200, 80),   "菠萝",  36),
    9:  (84,  (80,  180, 220),  "椰子",  45),
    10: (96,  (240, 200, 50),   "蜜瓜",  55),
    11: (110, (50,  200, 50),   "西瓜",  66),
}

MAX_LEVEL = 11
SPAWN_MAX_LEVEL = 5     # 投放只出现 1~5 级

# 颜色
BG_COLOR        = (255, 248, 230)
WALL_COLOR      = (139, 90,  43)
DANGER_COLOR    = (255, 60,  60)
GUIDE_COLOR     = (210, 210, 200)
TEXT_COLOR       = (60,  60,  60)
OVERLAY_COLOR   = (0,   0,   0,  140)
WHITE           = (255, 255, 255)

# ── 炸弹（Bomb）机制相关 ──
# 每攒满这么多分，授予 1 枚炸弹。固定阈值，简单直观。
BOMB_SCORE_THRESHOLD = 2000
# 炸弹模式下屏幕内描边（警戒红）。
BOMB_BORDER_COLOR = (220, 50, 50, 180)
BOMB_BORDER_THICKNESS = 4
# 鼠标准星与悬停高亮颜色。
BOMB_AIM_COLOR = (255, 60, 60)
# HUD 上炸弹图标/进度条颜色。
BOMB_HUD_COLOR = (40, 40, 40)         # 炸弹主体
BOMB_HUD_FUSE = (160, 110, 60)        # 引信
BOMB_HUD_SPARK = (255, 210, 80)       # 引信火花 / 高亮
BOMB_HUD_BAR = (220, 80, 60)          # 进度条填充色
BOMB_HUD_DIM   = (200, 200, 200)
# 刚获得炸弹时的闪烁颜色（金色，更像奖励）。
BOMB_FLASH_COLOR = (240, 180, 30)
# 爆炸火星颜色调色板（从该调色板随机抽取）。
EXPLOSION_PALETTE = (
    (255, 230, 120),
    (255, 170, 50),
    (255, 100, 30),
    (220, 60, 40),
)


# ──────────────────────────────────────
# 音效合成（纯代码生成，无需外部文件）
# ──────────────────────────────────────
def _generate_tone(freq, duration_ms, volume=0.3, fade=True):
    """合成一段正弦波音调，返回 pygame.mixer.Sound"""
    return synthesize_sound(
        freq,
        duration_ms / 1000.0,
        volume=volume,
        timbre=Timbre.Sine,
        fade_out=fade,
        fade_out_start=0.0,
    )


def _generate_merge_sound(level):
    """合并音效：双音叮，等级越高音调越高"""
    base = 420 + level * 80
    return make_sound(
        concat_samples(
            generate_samples(base, 0.08, volume=0.35, fade_out_start=0.0),
            generate_samples(base * 1.5, 0.12, volume=0.30, fade_out_start=0.0),
        )
    )


def _generate_drop_sound():
    """投放音效：短促低沉"""
    return _generate_tone(220, 60, volume=0.18)


def _generate_gameover_sound():
    """游戏结束：下行三连音"""
    return make_sound(
        concat_samples(*[
            generate_samples(freq, 0.18, volume=0.30, fade_out_start=0.0)
            for freq in (440, 370, 294)
        ])
    )


def _generate_pop_sound():
    """爆炸音效：高频 burst + 低频下行“轰”尾巴。

    分三段拼接：
      1) 高频方波 burst——仿压力释放的裂口声；
      2) 中频下行——过渡、填胸腔感；
      3) 低频下行（Hollow）——轰鸣尾。
    三段总时长 ≈230ms，足够重但不拖节奏。
    """
    return make_sound(
        concat_samples(
            generate_samples(900, 0.04, volume=0.32,
                             timbre=Timbre.Square, fade_out_start=0.0),
            generate_samples(360, 0.07, volume=0.28,
                             timbre=Timbre.Square, fade_out_start=0.0),
            generate_samples(120, 0.12, volume=0.30,
                             timbre=Timbre.Hollow, fade_out_start=0.0),
        )
    )


def _generate_charge_sound():
    """获得炸弹：上行三连音，用 Hollow 增加金属“装填”质感。"""
    return make_sound(
        concat_samples(*[
            generate_samples(freq, 0.10, volume=0.30,
                             timbre=Timbre.Hollow, fade_out_start=0.0)
            for freq in (523, 659, 880)
        ])
    )


def _generate_bgm():
    """合成一段 chiptune 风格循环 BGM（约 30 秒），返回 pygame.mixer.Sound"""
    bpm = 140
    beat = 60.0 / bpm            # 秒/拍
    note_dur = beat * 0.5        # 每音符时长（八分音符）

    # 主旋律（欢快跳跃感），每个元素 = 一个八分音符
    melody = [
        # Part A
        'E4', 'G4', 'C5', 'B4', 'A4', 'G4', 'E4', 'R',
        'D4', 'F4', 'A4', 'G4', 'F4', 'E4', 'D4', 'R',
        'C4', 'E4', 'G4', 'A4', 'B4', 'C5', 'B4', 'A4',
        'G4', 'E4', 'D4', 'E4', 'C4', 'R',  'C4', 'R',
        
        # Part A variant
        'E4', 'G4', 'C5', 'B4', 'A4', 'G4', 'E4', 'R',
        'D4', 'F4', 'A4', 'G4', 'F4', 'E4', 'D4', 'R',
        'C4', 'E4', 'G4', 'A4', 'B4', 'C5', 'D5', 'C5',
        'B4', 'G4', 'A4', 'B4', 'C5', 'R',  'C5', 'R',
        
        # Part B
        'D4', 'E4', 'F4', 'D4', 'E4', 'F4', 'G4', 'E4',
        'F4', 'G4', 'A4', 'F4', 'G4', 'A4', 'B4', 'G4',
        'C5', 'B4', 'A4', 'G4', 'F4', 'E4', 'D4', 'E4',
        'F4', 'D4', 'B3', 'G3', 'C4', 'R',  'C4', 'R',
        
        # Part A return
        'E4', 'G4', 'C5', 'B4', 'A4', 'G4', 'E4', 'R',
        'D4', 'F4', 'A4', 'G4', 'F4', 'E4', 'D4', 'R',
        'C4', 'E4', 'G4', 'A4', 'B4', 'C5', 'D5', 'C5',
        'B4', 'G4', 'A4', 'B4', 'C5', 'R',  'C5', 'R',
    ]

    # 低音 bass line（每个音持续两个八分音符节拍）
    bass = [
        # Part A
        'C3', 'C3', 'G3', 'G3', 'A3', 'A3', 'E3', 'E3',
        'F3', 'F3', 'C3', 'C3', 'G3', 'G3', 'C3', 'C3',
        'C3', 'C3', 'E3', 'E3', 'F3', 'F3', 'G3', 'G3',
        'A3', 'A3', 'F3', 'F3', 'G3', 'G3', 'C3', 'C3',
        
        # Part A variant
        'C3', 'C3', 'G3', 'G3', 'A3', 'A3', 'E3', 'E3',
        'F3', 'F3', 'C3', 'C3', 'G3', 'G3', 'C3', 'C3',
        'C3', 'C3', 'E3', 'E3', 'F3', 'F3', 'G3', 'G3',
        'G3', 'G3', 'G3', 'G3', 'C3', 'C3', 'C3', 'C3',
        
        # Part B
        'G2', 'G2', 'G2', 'G2', 'C3', 'C3', 'C3', 'C3',
        'F2', 'F2', 'F2', 'F2', 'G2', 'G2', 'G2', 'G2',
        'A2', 'A2', 'E3', 'E3', 'F3', 'F3', 'C3', 'C3',
        'G2', 'G2', 'G2', 'G2', 'C3', 'C3', 'C3', 'C3',
        
        # Part A return
        'C3', 'C3', 'G3', 'G3', 'A3', 'A3', 'E3', 'E3',
        'F3', 'F3', 'C3', 'C3', 'G3', 'G3', 'C3', 'C3',
        'C3', 'C3', 'E3', 'E3', 'F3', 'F3', 'G3', 'G3',
        'G3', 'G3', 'G3', 'G3', 'C3', 'C3', 'C3', 'C3',
    ]

    melody_samples = notes_to_samples(
        melody,
        note_dur,
        volume=0.12,
        timbre=Timbre.Sine,
        fade_out_start=0.0,
        release_end=0.4,
        harmonics=((1.0, 1.0), (3.0, 0.33)),
    )
    bass_samples = notes_to_samples(
        bass,
        note_dur,
        volume=0.10,
        timbre=Timbre.Sine,
        fade_out=False,
    )
    return make_sound(mix_samples(melody_samples, bass_samples))


def level_to_str(level:int):
    return str(1<<(level-1))

# ──────────────────────────────────────
# Ball 类
# ──────────────────────────────────────
class Ball:
    __slots__ = ("body", "shape", "level", "radius", "color",
                 "merged", "drop_frame", "settled_above_danger")

    def __init__(self, space, x, y, level, drop_frame=0):
        self.level = level
        cfg = BALL_CONFIG[level]
        self.radius = cfg[0]
        self.color = cfg[1]
        self.merged = False
        self.drop_frame = drop_frame
        self.settled_above_danger = 0

        # 这里用半径²近似质量，让大球明显比小球“重”，
        # 但又不按真实体积 r³ 增长得那么夸张，便于维持游戏手感。
        # 除以 180 只是把数值缩回到适合当前重力和尺寸范围的量级。
        mass = max(1.0, (self.radius * self.radius) / 180.0)
        moment = pymunk.moment_for_circle(mass, 0, self.radius)
        self.body = pymunk.Body(mass, moment)
        self.body.position = (float(x), float(y))
        self.shape = pymunk.Circle(self.body, self.radius)
        self.shape.elasticity = BALL_ELASTICITY
        self.shape.friction = BALL_FRICTION
        space.add(self.body, self.shape)

    @property
    def x(self):
        return float(self.body.position.x)

    @x.setter
    def x(self, value):
        self.body.position = (float(value), self.body.position.y)

    @property
    def y(self):
        return float(self.body.position.y)

    @y.setter
    def y(self, value):
        self.body.position = (self.body.position.x, float(value))

    @property
    def vx(self):
        return float(self.body.velocity.x)

    @vx.setter
    def vx(self, value):
        self.body.velocity = (float(value), self.body.velocity.y)

    @property
    def vy(self):
        return float(self.body.velocity.y)

    @vy.setter
    def vy(self, value):
        self.body.velocity = (self.body.velocity.x, float(value))

    def remove_from_space(self, space):
        space.remove(self.body, self.shape)

    # ---------- 绘制 ----------
    def draw(self, surface, font):
        ix, iy = int(self.x), int(self.y)
        r = self.radius

        # 主体
        pygame.draw.circle(surface, self.color, (ix, iy), r)

        # 高光
        hl_offset = max(3, r // 3)
        hl_radius = max(3, r // 4)
        hl_color = tuple(min(255, c + 70) for c in self.color)
        pygame.draw.circle(surface, hl_color,
                           (ix - hl_offset, iy - hl_offset), hl_radius)

        # 边框
        pygame.draw.circle(surface, WHITE, (ix, iy), r, 2)

        # 等级数字
        txt = font.render(level_to_str(self.level), True, WHITE)
        surface.blit(txt, txt.get_rect(center=(ix, iy)))

    @property
    def speed_sq(self):
        vx, vy = self.body.velocity
        return float(vx * vx + vy * vy)


# ──────────────────────────────────────
# 合并特效粒子（简单版）
# ──────────────────────────────────────
class MergeParticle:
    __slots__ = ("x", "y", "vx", "vy", "life", "color", "r")

    def __init__(self, x, y, color):
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(1.5, 4.5)
        self.x = x
        self.y = y
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed - 2
        self.life = random.randint(12, 25)
        self.color = color
        self.r = random.randint(2, 5)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.15
        self.life -= 1

    def draw(self, surface):
        if self.life > 0:
            # 简单方式：直接画圆
            pygame.draw.circle(surface, self.color[:3],
                               (int(self.x), int(self.y)), self.r)


# ──────────────────────────────────────
# 爆炸动画（中心闪光 + 冲击波环）
# ──────────────────────────────────────
class Explosion:
    """一次炸裂的视觉表现：中心白色闪光 + 向外扩散的偷环。

    不走物理、不造伤害。升出在“帧计数 + 起始半径”两个变量上。
    """
    __slots__ = ("x", "y", "r0", "frame", "life")

    LIFE = 18  # 总帧数（约 0.3 秒）

    def __init__(self, x, y, r0):
        self.x = float(x)
        self.y = float(y)
        self.r0 = float(r0)
        self.frame = 0
        self.life = self.LIFE

    @property
    def alive(self):
        return self.frame < self.life

    def update(self):
        self.frame += 1

    def draw(self, surface):
        t = self.frame / self.life  # 0..1
        if t >= 1.0:
            return
        # 中心闪光：前 1/3 为主，之后迅速消失
        flash_a = max(0.0, 1.0 - t * 1.6)
        if flash_a > 0:
            flash_r = int(self.r0 * (0.4 + 0.7 * t))
            flash = pygame.Surface((flash_r * 2 + 2, flash_r * 2 + 2),
                                   pygame.SRCALPHA)
            pygame.draw.circle(flash, (255, 240, 200, int(220 * flash_a)),
                               (flash_r + 1, flash_r + 1), flash_r)
            surface.blit(flash, (int(self.x) - flash_r - 1,
                                 int(self.y) - flash_r - 1))
        # 冲击波环：半径从 r0 扩到 ~2.2*r0，alpha 从高到低
        ring_r = int(self.r0 * (1.0 + 1.2 * t))
        ring_a = int(220 * (1.0 - t))
        if ring_a > 0 and ring_r > 0:
            ring = pygame.Surface((ring_r * 2 + 4, ring_r * 2 + 4),
                                  pygame.SRCALPHA)
            # 外浅内深，双环增加层次
            pygame.draw.circle(ring, (255, 200, 80, ring_a),
                               (ring_r + 2, ring_r + 2), ring_r, 3)
            inner_r = max(1, ring_r - 5)
            pygame.draw.circle(ring, (255, 90, 40, max(0, ring_a - 60)),
                               (ring_r + 2, ring_r + 2), inner_r, 2)
            surface.blit(ring, (int(self.x) - ring_r - 2,
                                int(self.y) - ring_r - 2))


# ──────────────────────────────────────
# 主游戏类
# ──────────────────────────────────────
class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("合成大西瓜  Suika Game")
        self.clock = pygame.time.Clock()

        # 鼠标锁定在窗口内
        pygame.event.set_grab(True)
        pygame.mouse.set_visible(True)

        # 预生成音效
        self.snd_merge = {lv: _generate_merge_sound(lv) for lv in range(2, MAX_LEVEL + 1)}
        self.snd_drop = _generate_drop_sound()
        self.snd_gameover = _generate_gameover_sound()
        self.snd_explode = _generate_pop_sound()
        self.snd_bomb_ready = _generate_charge_sound()

        # BGM
        self.bgm = _generate_bgm()
        self.audio = AudioRuntime(total_channels=8)
        self.audio.play_bgm(self.bgm, volume=0.18)

        self.reset()

    def reset(self):
        self._setup_space()
        self.balls: list[Ball] = []
        self.particles: list[MergeParticle] = []
        self.score = 0
        self.max_level_reached = 0
        self.game_over = False
        self.spawn_x = WIDTH // 2
        self.frame = 0

        self.current_level = random.randint(1, SPAWN_MAX_LEVEL)
        self.next_level = random.randint(1, SPAWN_MAX_LEVEL)
        self.can_drop = True
        self.drop_cooldown = 0
        self._refresh_spawn_x()

        # ── 炸弹机制状态 ──
        # bombs：剩余炸弹数（叠加）。
        # score_for_next_bomb：下一枚炸弹发放阈值。
        # bomb_mode：是否处于炸弹模式（投放被禁用）。
        # bomb_flash：刚获得炸弹时的 HUD 闪烁帧数。
        # explosions：炸裂冲击波动画列表。
        self.bombs = 0
        self.score_for_next_bomb = BOMB_SCORE_THRESHOLD
        self.bomb_mode = False
        self.bomb_flash = 0
        self.explosions: list[Explosion] = []
        self.mouse_pos = (WIDTH // 2, SPAWN_Y)

        self.font_large = load_font(44, "simhei", "microsoftyahei", "simsun", fallback_size=48)
        self.font_mid   = load_font(28, "simhei", "microsoftyahei", "simsun", fallback_size=30)
        self.font_small = load_font(20, "simhei", "microsoftyahei", "simsun", fallback_size=22)
        self.font_ball  = load_font(22, "simhei", "microsoftyahei", "simsun", fallback_size=24)

    def _setup_space(self):
        self.space = pymunk.Space()
        self.space.gravity = (0.0, GRAVITY)
        self.space.damping = SPACE_DAMPING
        self.space.iterations = SPACE_ITERATIONS

        # 刚体在低速稳定一段时间后会自动 sleep，不再继续参与求解。
        # 这是消除“看起来停住了却还在微抖”的关键机制之一。
        # sleep_time_threshold：低速持续多久后允许睡眠。
        # idle_speed_threshold：多慢才算“低速”。
        self.space.sleep_time_threshold = 0.8
        self.space.idle_speed_threshold = 8.0

        # 接触容差（penetration slop）。
        # 求解器允许极小的重叠存在，而不是每帧都强行修正到完全零重叠。
        # 这样能显著减少堆叠时的高频抖动，是成熟物理引擎常见做法。
        # 调大：更稳，但视觉上可能出现极轻微“软接触”。
        # 调小：更刚硬，但更容易因为过度修正而抖。
        self.space.collision_slop = 0.5

        wall_radius = WALL_THICKNESS / 2
        walls = [
            pymunk.Segment(self.space.static_body,
                           (wall_radius, CONTAINER_TOP + wall_radius),
                           (wall_radius, HEIGHT - wall_radius), wall_radius),
            pymunk.Segment(self.space.static_body,
                           (WIDTH - wall_radius, CONTAINER_TOP + wall_radius),
                           (WIDTH - wall_radius, HEIGHT - wall_radius), wall_radius),
            pymunk.Segment(self.space.static_body,
                           (WALL_LEFT, HEIGHT - wall_radius),
                           (WALL_RIGHT, HEIGHT - wall_radius), wall_radius),
        ]
        for wall in walls:
            wall.elasticity = WALL_ELASTICITY
            wall.friction = WALL_FRICTION
        self.space.add(*walls)

    def _spawn_limits(self, level=None, extra_margin=0.0):
        if level is None:
            level = self.current_level
        radius = BALL_CONFIG[level][0]
        margin = radius + DROP_SIDE_MARGIN + extra_margin
        return WALL_LEFT + margin, WALL_RIGHT - margin

    def _clamp_spawn_x(self, x, level=None, extra_margin=0.0):
        left, right = self._spawn_limits(level, extra_margin)
        return max(left, min(right, x))

    def _refresh_spawn_x(self):
        self.spawn_x = self._clamp_spawn_x(self.spawn_x)

    # ---------- 炸弹机制 ----------
    def _award_bombs_if_due(self):
        """若分数跨过阈值则发放炸弹，支持一次跨多个阈值。"""
        awarded = 0
        while self.score >= self.score_for_next_bomb:
            self.bombs += 1
            self.score_for_next_bomb += BOMB_SCORE_THRESHOLD
            awarded += 1
        if awarded > 0:
            self.bomb_flash = 45
            self.snd_bomb_ready.play()

    def _toggle_bomb_mode(self):
        if self.game_over:
            return
        if self.bomb_mode:
            self.bomb_mode = False
        elif self.bombs > 0:
            self.bomb_mode = True

    def _exit_bomb_mode(self):
        self.bomb_mode = False

    def _ball_under_point(self, mx, my):
        """返回点 (mx,my) 命中的最上层球；用渲染顺序的反序近似 z-order。"""
        for b in reversed(self.balls):
            dx = b.x - mx
            dy = b.y - my
            if dx * dx + dy * dy <= b.radius * b.radius:
                return b
        return None

    def _detonate_at(self, mx, my):
        if not self.bomb_mode or self.bombs <= 0 or self.game_over:
            return
        target = self._ball_under_point(mx, my)
        if target is None:
            return
        # 炸裂火星：暂仅使用暑色调色板（脱离球本身的颜色，更像火星不是“碎末”）
        for _ in range(16):
            color = random.choice(EXPLOSION_PALETTE)
            self.particles.append(MergeParticle(target.x, target.y, color))
        # 中心闪光 + 冲击波环
        self.explosions.append(Explosion(target.x, target.y, target.radius))
        target.remove_from_space(self.space)
        self.balls.remove(target)
        self.snd_explode.play()
        self.bombs -= 1
        if self.bombs <= 0:
            self.bomb_mode = False

    # ---------- 投放 ----------
    def drop_ball(self):
        if not self.can_drop or self.game_over or self.bomb_mode:
            return
        self._refresh_spawn_x()

        # 投放时加随机微小扰动，避免完美纵向堆叠。
        # 抖动后仍会重新夹紧，保证新球不会因为抖动贴进侧墙。
        x_jitter = random.uniform(-DROP_X_JITTER, DROP_X_JITTER)
        drop_x = self._clamp_spawn_x(self.spawn_x + x_jitter, self.current_level)
        ball = Ball(self.space, drop_x, SPAWN_Y,
                    self.current_level, self.frame)
        ball.vx = random.uniform(-1.0, 1.0)
        self.balls.append(ball)
        self.snd_drop.play()
        self.current_level = self.next_level
        self.next_level = random.randint(1, SPAWN_MAX_LEVEL)
        self._refresh_spawn_x()
        self.can_drop = False
        self.drop_cooldown = DROP_COOLDOWN_FRAMES

    # ---------- 逻辑更新 ----------
    def update(self):
        if self.bomb_flash > 0:
            self.bomb_flash -= 1
        if self.game_over:
            # 游戏结束时禁用炸弹：濒死救场过强，剩余炸弹也清零。
            if self.bomb_mode:
                self.bomb_mode = False
            self.bombs = 0
            # 粒子与爆炸动画继续更新
            self._update_particles()
            self._update_explosions()
            return

        self.frame += 1

        # 冷却
        if self.drop_cooldown > 0:
            self.drop_cooldown -= 1
            if self.drop_cooldown <= 0:
                self.can_drop = True

        for _ in range(PHYSICS_STEPS_PER_FRAME):
            self.space.step(PHYSICS_DT)

        self._handle_merges()

        # 游戏结束检测
        for b in self.balls:
            # 投放后至少 60 帧才判定
            if self.frame - b.drop_frame < 60:
                continue
            if b.y - b.radius < DANGER_Y and b.speed_sq < RESTING_SPEED_SQ:
                b.settled_above_danger += 1
                if b.settled_above_danger > GAME_OVER_GRACE:
                    self.game_over = True
                    self.snd_gameover.play()
                    self.audio.set_bgm_volume(0.06)  # Game Over 时压低 BGM
                    break
            else:
                b.settled_above_danger = 0

        # 粒子 / 爆炸动画
        self._update_particles()
        self._update_explosions()

    def _update_particles(self):
        for p in self.particles:
            p.update()
        self.particles = [p for p in self.particles if p.life > 0]

    def _update_explosions(self):
        for e in self.explosions:
            e.update()
        self.explosions = [e for e in self.explosions if e.alive]

    def _handle_merges(self):
        while True:
            merged_any = False
            n = len(self.balls)
            for i in range(n):
                b1 = self.balls[i]
                for j in range(i + 1, n):
                    b2 = self.balls[j]
                    if not self._can_merge(b1, b2):
                        continue
                    self._merge_pair(b1, b2)
                    merged_any = True
                    break
                if merged_any:
                    break
            if not merged_any:
                return

    def _can_merge(self, b1, b2):
        if b1.level != b2.level or b1.level >= MAX_LEVEL:
            return False
        dx = b2.x - b1.x
        dy = b2.y - b1.y
        rsum = b1.radius + b2.radius + MERGE_DISTANCE_SLOP
        return dx * dx + dy * dy <= rsum * rsum

    def _merge_pair(self, b1, b2):
        new_level = b1.level + 1
        nx = (b1.x + b2.x) / 2.0
        ny = (b1.y + b2.y) / 2.0
        vx = (b1.vx + b2.vx) * 0.35
        vy = min(b1.vy, b2.vy) - 120.0

        b1.remove_from_space(self.space)
        b2.remove_from_space(self.space)
        self.balls.remove(b1)
        self.balls.remove(b2)

        new_ball = Ball(self.space, nx, ny, new_level, self.frame)
        new_ball.body.velocity = (vx, vy)
        self.balls.append(new_ball)

        self.score += BALL_CONFIG[new_level][3]
        self._award_bombs_if_due()
        if new_level in self.snd_merge:
            self.snd_merge[new_level].play()
        if new_level > self.max_level_reached:
            self.max_level_reached = new_level
        for _ in range(10):
            self.particles.append(
                MergeParticle(nx, ny, BALL_CONFIG[new_level][1]))

    # ---------- 绘制 ----------
    def draw(self):
        self.screen.fill(BG_COLOR)

        # 容器壁
        pygame.draw.rect(self.screen, WALL_COLOR,
                         (0, CONTAINER_TOP, WALL_LEFT, HEIGHT - CONTAINER_TOP))
        pygame.draw.rect(self.screen, WALL_COLOR,
                         (WALL_RIGHT, CONTAINER_TOP,
                          WIDTH - WALL_RIGHT, HEIGHT - CONTAINER_TOP))
        pygame.draw.rect(self.screen, WALL_COLOR,
                         (0, FLOOR_Y, WIDTH, HEIGHT - FLOOR_Y))

        # 危险线
        for x in range(WALL_LEFT, WALL_RIGHT, 16):
            pygame.draw.line(self.screen, DANGER_COLOR,
                             (x, DANGER_Y), (x + 8, DANGER_Y), 2)

        # 引导线 & 待投放球（炸弹模式下隐藏，避免和投放视觉混淆）
        if self.can_drop and not self.game_over and not self.bomb_mode:
            pygame.draw.line(self.screen, GUIDE_COLOR,
                             (self.spawn_x, SPAWN_Y + BALL_CONFIG[self.current_level][0]),
                             (self.spawn_x, FLOOR_Y), 1)
            self._draw_preview_ball(self.spawn_x, SPAWN_Y, self.current_level, 1.0)

        # "下一个" 预览
        preview_x, preview_y = WIDTH - 55, 50
        self._draw_preview_ball(preview_x, preview_y, self.next_level, 0.6)
        label = self.font_small.render("NEXT", True, TEXT_COLOR)
        self.screen.blit(label,
                         label.get_rect(center=(preview_x, preview_y - 25)))

        # 所有球
        for b in self.balls:
            b.draw(self.screen, self.font_ball)

        # 粒子
        for p in self.particles:
            p.draw(self.screen)

        # 爆炸动画（画在粒子之上，让闪光/冲击波靠前）
        for e in self.explosions:
            e.draw(self.screen)

        # 分数 & 最高等级
        s1 = self.font_mid.render(f"Score: {self.score}", True, TEXT_COLOR)
        self.screen.blit(s1, (WALL_LEFT + 8, 8))
        if self.max_level_reached > 0:
            name = BALL_CONFIG[self.max_level_reached][2]
            s2 = self.font_small.render(f"Max: Lv{self.max_level_reached} {name}",
                                        True, TEXT_COLOR)
            self.screen.blit(s2, (WALL_LEFT + 8, 42))

        # 炸弹 HUD
        self._draw_bomb_hud()

        # 炸弹模式下的悬停高亮 + 顶部提示 + 屏幕边框
        if self.bomb_mode:
            self._draw_bomb_mode_overlay()

        # Game Over 覆盖层
        if self.game_over:
            self._draw_game_over()

        pygame.display.flip()

    def _draw_preview_ball(self, cx, cy, level, scale):
        cfg = BALL_CONFIG[level]
        r = max(5, int(cfg[0] * scale))
        color = cfg[1]
        pygame.draw.circle(self.screen, color, (int(cx), int(cy)), r)
        hl_off = max(2, r // 3)
        hl_r = max(2, r // 4)
        hl_c = tuple(min(255, c + 70) for c in color)
        pygame.draw.circle(self.screen, hl_c,
                           (int(cx) - hl_off, int(cy) - hl_off), hl_r)
        pygame.draw.circle(self.screen, WHITE, (int(cx), int(cy)), r, 2)
        if scale >= 0.8:
            txt = self.font_ball.render(level_to_str(level), True, WHITE)
            self.screen.blit(txt, txt.get_rect(center=(int(cx), int(cy))))

    def _draw_bomb_icon(self, cx, cy, radius=6, sparkle=False):
        """手绘小炸弹：黑色圆体 + 棕色引信 + 高亮点（可选火花）。"""
        cx, cy = int(cx), int(cy)
        # 主体
        pygame.draw.circle(self.screen, BOMB_HUD_COLOR, (cx, cy), radius)
        # 高亮
        hl_r = max(1, radius // 3)
        pygame.draw.circle(self.screen, (110, 110, 110),
                           (cx - radius // 3, cy - radius // 3), hl_r)
        # 引信（左上斜出的短棒）
        fuse_x1, fuse_y1 = cx - int(radius * 0.6), cy - int(radius * 0.9)
        fuse_x2, fuse_y2 = cx - int(radius * 1.0), cy - int(radius * 1.7)
        pygame.draw.line(self.screen, BOMB_HUD_FUSE,
                         (fuse_x1, fuse_y1), (fuse_x2, fuse_y2), 2)
        # 引信火花
        if sparkle:
            pygame.draw.circle(self.screen, BOMB_HUD_SPARK,
                               (fuse_x2, fuse_y2), 3)
            pygame.draw.circle(self.screen, (255, 255, 200),
                               (fuse_x2, fuse_y2), 1)

    def _draw_bomb_hud(self):
        """HUD：剩余炸弹数 + 炸弹图标列 + 距下一枚进度条。"""
        base_x = WALL_LEFT + 8
        base_y = 70

        # 闪烁：刚获得炸弹时文字变金色
        if self.bomb_flash > 0 and (self.bomb_flash // 6) % 2 == 0:
            text_color = BOMB_FLASH_COLOR
        else:
            text_color = TEXT_COLOR
        label = self.font_small.render(f"Bombs: {self.bombs}", True, text_color)
        self.screen.blit(label, (base_x, base_y))

        # 炸弹图标（最多 5 个，超出用 +N）
        icon_x = base_x + label.get_width() + 14
        icon_y = base_y + label.get_height() // 2 + 1
        max_icons = 5
        shown = min(self.bombs, max_icons)
        # 闪烁帧内，顶部那枚炸弹画火花，强化“快点交付”貃示
        sparkle_first = self.bomb_flash > 0 or self.bomb_mode
        for i in range(shown):
            self._draw_bomb_icon(icon_x + i * 18, icon_y, radius=6,
                                 sparkle=(sparkle_first and i == 0))
        if self.bombs > max_icons:
            extra = self.font_small.render(f"+{self.bombs - max_icons}",
                                           True, BOMB_HUD_COLOR)
            self.screen.blit(extra, (icon_x + max_icons * 18 + 2, base_y))

        # 进度条：距下一枚炸弹还差多少分
        bar_x = base_x
        bar_y = base_y + label.get_height() + 6
        bar_w = 140
        bar_h = 6
        progress_score = self.score - (self.score_for_next_bomb - BOMB_SCORE_THRESHOLD)
        progress_score = max(0, min(BOMB_SCORE_THRESHOLD, progress_score))
        ratio = progress_score / BOMB_SCORE_THRESHOLD
        pygame.draw.rect(self.screen, BOMB_HUD_DIM,
                         (bar_x, bar_y, bar_w, bar_h), border_radius=3)
        pygame.draw.rect(self.screen, BOMB_HUD_BAR,
                         (bar_x, bar_y, int(bar_w * ratio), bar_h),
                         border_radius=3)
        remain = self.score_for_next_bomb - self.score
        hint = self.font_small.render(f"next +{remain}", True, TEXT_COLOR)
        self.screen.blit(hint, (bar_x + bar_w + 8, bar_y - 6))

    def _draw_bomb_mode_overlay(self):
        """炸弹模式：脉动警戒红边框 + 顶部提示 + 鼠标准星高亮。"""
        # 脉动边框
        pulse = (math.sin(self.frame * 0.18) + 1.0) * 0.5  # 0..1
        alpha = int(110 + 110 * pulse)
        border_color = (BOMB_BORDER_COLOR[0], BOMB_BORDER_COLOR[1],
                        BOMB_BORDER_COLOR[2], alpha)
        border = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        pygame.draw.rect(border, border_color,
                         (0, 0, WIDTH, HEIGHT),
                         BOMB_BORDER_THICKNESS)
        self.screen.blit(border, (0, 0))

        # 顶部居中提示条
        hint = self.font_small.render(
            "BOMB MODE — 左键点击引爆任意球    Tab/右键 取消",
            True, WHITE)
        pad_x, pad_y = 12, 6
        rect = hint.get_rect(center=(WIDTH // 2, 24))
        bg_rect = rect.inflate(pad_x * 2, pad_y * 2)
        bg = pygame.Surface(bg_rect.size, pygame.SRCALPHA)
        bg.fill((BOMB_BORDER_COLOR[0], BOMB_BORDER_COLOR[1],
                 BOMB_BORDER_COLOR[2], 210))
        self.screen.blit(bg, bg_rect.topleft)
        self.screen.blit(hint, rect)

        # 鼠标悬停球：双环高亮 + 中心十字准星
        mx, my = self.mouse_pos
        target = self._ball_under_point(mx, my)
        if target is not None:
            tx, ty = int(target.x), int(target.y)
            outer_r = int(target.radius + 6 + 3 * pulse)
            inner_r = int(target.radius + 2)
            pygame.draw.circle(self.screen, BOMB_AIM_COLOR,
                               (tx, ty), outer_r, 2)
            pygame.draw.circle(self.screen, BOMB_AIM_COLOR,
                               (tx, ty), inner_r, 2)
            # 十字准星（中间留空，避免遮住等级数字）
            gap = 4
            tick = 8
            pygame.draw.line(self.screen, BOMB_AIM_COLOR,
                             (tx - inner_r - tick, ty), (tx - inner_r - gap, ty), 2)
            pygame.draw.line(self.screen, BOMB_AIM_COLOR,
                             (tx + inner_r + gap, ty), (tx + inner_r + tick, ty), 2)
            pygame.draw.line(self.screen, BOMB_AIM_COLOR,
                             (tx, ty - inner_r - tick), (tx, ty - inner_r - gap), 2)
            pygame.draw.line(self.screen, BOMB_AIM_COLOR,
                             (tx, ty + inner_r + gap), (tx, ty + inner_r + tick), 2)

    def _draw_game_over(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill(OVERLAY_COLOR)
        self.screen.blit(overlay, (0, 0))

        t1 = self.font_large.render("GAME OVER", True, (255, 80, 80))
        self.screen.blit(t1, t1.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 50)))

        t2 = self.font_mid.render(f"Score: {self.score}", True, WHITE)
        self.screen.blit(t2, t2.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 10)))

        if self.max_level_reached > 0:
            name = BALL_CONFIG[self.max_level_reached][2]
            t3 = self.font_small.render(
                f"Max: Lv{self.max_level_reached} {name}", True, WHITE)
            self.screen.blit(t3, t3.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 45)))

        t4 = self.font_small.render("Press  R  to  Restart", True,
                                    (200, 200, 200))
        self.screen.blit(t4, t4.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 85)))

    # ---------- 主循环 ----------
    def run(self):
        use_mouse = False   # 一旦检测到鼠标移动就切换为鼠标模式

        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.event.set_grab(False)
                    pygame.quit()
                    sys.exit()

                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    # 两段式：先退出炸弹模式，再退出游戏
                    if self.bomb_mode:
                        self._exit_bomb_mode()
                    else:
                        pygame.event.set_grab(False)
                        pygame.quit()
                        sys.exit()

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        self.drop_ball()
                    elif event.key == pygame.K_TAB:
                        self._toggle_bomb_mode()
                    elif event.key == pygame.K_r and self.game_over:
                        self.reset()
                        self.audio.set_bgm_volume(0.18)  # 重开时恢复 BGM 音量

                elif event.type == pygame.MOUSEMOTION:
                    self.mouse_pos = event.pos
                    if not self.game_over and not self.bomb_mode:
                        use_mouse = True
                        mx = event.pos[0]
                        self.spawn_x = self._clamp_spawn_x(mx)

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        if self.bomb_mode:
                            self._detonate_at(*event.pos)
                        else:
                            self.drop_ball()
                    elif event.button == 3:
                        # 右键：炸弹模式下作为"取消"
                        if self.bomb_mode:
                            self._exit_bomb_mode()

            # 连续按键（方向键）
            if not self.game_over and not use_mouse:
                keys = pygame.key.get_pressed()
                if keys[pygame.K_LEFT]:
                    self.spawn_x = self._clamp_spawn_x(self.spawn_x - MOVE_SPEED)
                    use_mouse = False
                if keys[pygame.K_RIGHT]:
                    self.spawn_x = self._clamp_spawn_x(self.spawn_x + MOVE_SPEED)
                    use_mouse = False
            elif not self.game_over:
                # 鼠标模式下仍允许键盘微调
                keys = pygame.key.get_pressed()
                if keys[pygame.K_LEFT] or keys[pygame.K_RIGHT]:
                    use_mouse = False
                    if keys[pygame.K_LEFT]:
                        self.spawn_x = self._clamp_spawn_x(self.spawn_x - MOVE_SPEED)
                    if keys[pygame.K_RIGHT]:
                        self.spawn_x = self._clamp_spawn_x(self.spawn_x + MOVE_SPEED)

            self.update()
            self.draw()
            self.clock.tick(FPS)


# ──────────────────────────────────────
# 入口
# ──────────────────────────────────────
if __name__ == "__main__":
    init_pygame_audio()
    game = Game()
    game.run()

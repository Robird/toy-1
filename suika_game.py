"""
合成大西瓜 (Suika / Merge Balls Game)
--------------------------------------
左右方向键 或 鼠标移动 —— 控制投放位置
空格键 或 鼠标左键 —— 投放小球
R 键 —— Game Over 后重新开始
"""

import pygame
import sys
import random
import math
import array
import pymunk

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


# ──────────────────────────────────────
# 音效合成（纯代码生成，无需外部文件）
# ──────────────────────────────────────
def _generate_tone(freq, duration_ms, volume=0.3, fade=True, sample_rate=44100):
    """合成一段正弦波音调，返回 pygame.mixer.Sound"""
    n = int(sample_rate * duration_ms / 1000)
    buf = array.array('h')          # signed 16-bit
    mv = int(32767 * volume)
    dur_s = duration_ms / 1000
    for i in range(n):
        t = i / sample_rate
        env = max(0.0, 1.0 - t / dur_s) if fade else 1.0
        val = int(mv * env * math.sin(2 * math.pi * freq * t))
        buf.append(val)   # L
        buf.append(val)   # R
    return pygame.mixer.Sound(buffer=buf)


def _generate_merge_sound(level):
    """合并音效：双音叮，等级越高音调越高"""
    base = 420 + level * 80
    s1 = _generate_tone(base, 80, volume=0.35)
    s2 = _generate_tone(base * 1.5, 120, volume=0.30)
    # 把两段拼在一起
    buf = array.array('h')
    buf.frombytes(s1.get_raw())
    buf.frombytes(s2.get_raw())
    return pygame.mixer.Sound(buffer=buf)


def _generate_drop_sound():
    """投放音效：短促低沉"""
    return _generate_tone(220, 60, volume=0.18)


def _generate_gameover_sound():
    """游戏结束：下行三连音"""
    parts = array.array('h')
    for freq in (440, 370, 294):
        s = _generate_tone(freq, 180, volume=0.30)
        parts.frombytes(s.get_raw())
    return pygame.mixer.Sound(buffer=parts)


def _generate_bgm(sample_rate=44100):
    """合成一段 chiptune 风格循环 BGM（约 8 秒），返回 pygame.mixer.Sound"""
    bpm = 140
    beat = 60.0 / bpm            # 秒/拍
    note_dur = beat * 0.5        # 每音符时长（八分音符）

    # C 大调音符频率表
    NOTE = {
        'C3': 130.81, 'D3': 146.83, 'E3': 164.81, 'F3': 174.61,
        'G3': 196.00, 'A3': 220.00, 'B3': 246.94,
        'C4': 261.63, 'D4': 293.66, 'E4': 329.63, 'F4': 349.23,
        'G4': 392.00, 'A4': 440.00, 'B4': 493.88,
        'C5': 523.25, 'D5': 587.33, 'E5': 659.25,
        'R': 0,  # 休止符
    }

    # 主旋律（欢快跳跃感），每个元素 = 一个八分音符
    melody = [
        'E4', 'G4', 'C5', 'B4', 'A4', 'G4', 'E4', 'R',
        'D4', 'F4', 'A4', 'G4', 'F4', 'E4', 'D4', 'R',
        'C4', 'E4', 'G4', 'A4', 'B4', 'C5', 'B4', 'A4',
        'G4', 'E4', 'D4', 'E4', 'C4', 'R',  'C4', 'R',
    ]

    # 低音 bass line（每个音持续两个八分音符节拍）
    bass = [
        'C3', 'C3', 'G3', 'G3', 'A3', 'A3', 'E3', 'E3',
        'F3', 'F3', 'C3', 'C3', 'G3', 'G3', 'C3', 'C3',
        'C3', 'C3', 'E3', 'E3', 'F3', 'F3', 'G3', 'G3',
        'A3', 'A3', 'F3', 'F3', 'G3', 'G3', 'C3', 'C3',
    ]

    total_notes = len(melody)
    samples_per_note = int(sample_rate * note_dur)
    total_samples = samples_per_note * total_notes

    buf = array.array('h')  # stereo 16-bit

    for idx in range(total_notes):
        mel_freq = NOTE[melody[idx]]
        bas_freq = NOTE[bass[idx]]

        for i in range(samples_per_note):
            t = i / sample_rate
            frac = i / samples_per_note  # 0..1 在本音符内的进度

            # 音量包络：快速起音 + 缓慢衰减，给 chiptune 弹性感
            env = max(0.0, 1.0 - frac * 0.6)

            # 旋律：方波近似（基频 + 3次谐波），音量较小
            mel = 0.0
            if mel_freq > 0:
                mel = (math.sin(2 * math.pi * mel_freq * t)
                       + 0.33 * math.sin(2 * math.pi * mel_freq * 3 * t))
                mel *= env * 0.12

            # Bass：纯正弦低音，稍大音量给厚度
            bas = 0.0
            if bas_freq > 0:
                bas = math.sin(2 * math.pi * bas_freq * t) * 0.10

            val = int(32767 * max(-1.0, min(1.0, mel + bas)))
            buf.append(val)
            buf.append(val)

    return pygame.mixer.Sound(buffer=buf)


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
            alpha = max(0, min(255, self.life * 12))
            c = (*self.color[:3], alpha) if len(self.color) == 4 else (*self.color, alpha)
            # 简单方式：直接画圆
            pygame.draw.circle(surface, self.color[:3],
                               (int(self.x), int(self.y)), self.r)


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

        # BGM
        self.bgm = _generate_bgm()
        self.bgm_channel = pygame.mixer.Channel(7)  # 专用通道
        self.bgm_channel.set_volume(0.18)
        self.bgm_channel.play(self.bgm, loops=-1)

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

    # ---------- 投放 ----------
    def drop_ball(self):
        if not self.can_drop or self.game_over:
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
        if self.game_over:
            # 粒子继续更新
            self._update_particles()
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
                    self.bgm_channel.set_volume(0.06)  # Game Over 时压低 BGM
                    break
            else:
                b.settled_above_danger = 0

        # 粒子
        self._update_particles()

    def _update_particles(self):
        for p in self.particles:
            p.update()
        self.particles = [p for p in self.particles if p.life > 0]

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

        # 引导线 & 待投放球
        if self.can_drop and not self.game_over:
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

        # 分数 & 最高等级
        s1 = self.font_mid.render(f"Score: {self.score}", True, TEXT_COLOR)
        self.screen.blit(s1, (WALL_LEFT + 8, 8))
        if self.max_level_reached > 0:
            name = BALL_CONFIG[self.max_level_reached][2]
            s2 = self.font_small.render(f"Max: Lv{self.max_level_reached} {name}",
                                        True, TEXT_COLOR)
            self.screen.blit(s2, (WALL_LEFT + 8, 42))

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
                    pygame.event.set_grab(False)
                    pygame.quit()
                    sys.exit()

                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        self.drop_ball()
                    elif event.key == pygame.K_r and self.game_over:
                        self.reset()
                        self.bgm_channel.set_volume(0.18)  # 重开时恢复 BGM 音量

                elif event.type == pygame.MOUSEMOTION:
                    if not self.game_over:
                        use_mouse = True
                        mx = event.pos[0]
                        self.spawn_x = self._clamp_spawn_x(mx)

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.drop_ball()

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
    pygame.init()
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
    game = Game()
    game.run()

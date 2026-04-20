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

# ──────────────────────────────────────
# 常量
# ──────────────────────────────────────
WIDTH, HEIGHT = 480, 750
FPS = 60
GRAVITY = 1260.0
SPACE_DAMPING = 0.92
SPACE_ITERATIONS = 30
PHYSICS_STEPS_PER_FRAME = 3
PHYSICS_DT = 1.0 / (FPS * PHYSICS_STEPS_PER_FRAME)
BALL_ELASTICITY = 0.08
BALL_FRICTION = 0.9
WALL_ELASTICITY = 0.0
WALL_FRICTION = 1.1
MERGE_DISTANCE_SLOP = 0.5
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
        txt = font.render(str(self.level), True, WHITE)
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

        # 字体（尝试中文字体，回退默认）
        try:
            self.font_large = pygame.font.SysFont("simhei", 44)
            self.font_mid   = pygame.font.SysFont("simhei", 28)
            self.font_small = pygame.font.SysFont("simhei", 20)
            self.font_ball  = pygame.font.SysFont("simhei", 22)
        except Exception:
            self.font_large = pygame.font.SysFont(None, 48)
            self.font_mid   = pygame.font.SysFont(None, 30)
            self.font_small = pygame.font.SysFont(None, 22)
            self.font_ball  = pygame.font.SysFont(None, 24)

    def _setup_space(self):
        self.space = pymunk.Space()
        self.space.gravity = (0.0, GRAVITY)
        self.space.damping = SPACE_DAMPING
        self.space.iterations = SPACE_ITERATIONS
        self.space.sleep_time_threshold = 0.4
        self.space.idle_speed_threshold = 18.0
        self.space.collision_slop = 0.5

        walls = [
            pymunk.Segment(self.space.static_body,
                           (WALL_LEFT, DANGER_Y*1.25),
                           (WALL_LEFT, FLOOR_Y), WALL_THICKNESS / 2),
            pymunk.Segment(self.space.static_body,
                           (WALL_RIGHT, DANGER_Y*1.25),
                           (WALL_RIGHT, FLOOR_Y), WALL_THICKNESS / 2),
            pymunk.Segment(self.space.static_body,
                           (WALL_LEFT, FLOOR_Y),
                           (WALL_RIGHT, FLOOR_Y), WALL_THICKNESS / 2),
        ]
        for wall in walls:
            wall.elasticity = WALL_ELASTICITY
            wall.friction = WALL_FRICTION
        self.space.add(*walls)

    # ---------- 投放 ----------
    def drop_ball(self):
        if not self.can_drop or self.game_over:
            return
        # 投放时加随机微小扰动，避免完美纵向堆叠
        x_jitter = random.uniform(-1.0, 1.0)
        ball = Ball(self.space, self.spawn_x + x_jitter, SPAWN_Y,
                    self.current_level, self.frame)
        ball.vx = random.uniform(-1.0, 1.0)
        self.balls.append(ball)
        self.snd_drop.play()
        self.current_level = self.next_level
        self.next_level = random.randint(1, SPAWN_MAX_LEVEL)
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
                         (0, DANGER_Y - 10, WALL_LEFT, HEIGHT - DANGER_Y + 10))
        pygame.draw.rect(self.screen, WALL_COLOR,
                         (WALL_RIGHT, DANGER_Y - 10,
                          WIDTH - WALL_RIGHT, HEIGHT - DANGER_Y + 10))
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
            txt = self.font_ball.render(str(level), True, WHITE)
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

                elif event.type == pygame.MOUSEMOTION:
                    if not self.game_over:
                        use_mouse = True
                        r = BALL_CONFIG[self.current_level][0]
                        mx = event.pos[0]
                        self.spawn_x = max(WALL_LEFT + r,
                                           min(WALL_RIGHT - r, mx))

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        self.drop_ball()

            # 连续按键（方向键）
            if not self.game_over and not use_mouse:
                keys = pygame.key.get_pressed()
                r = BALL_CONFIG[self.current_level][0]
                if keys[pygame.K_LEFT]:
                    self.spawn_x = max(WALL_LEFT + r,
                                       self.spawn_x - MOVE_SPEED)
                    use_mouse = False
                if keys[pygame.K_RIGHT]:
                    self.spawn_x = min(WALL_RIGHT - r,
                                       self.spawn_x + MOVE_SPEED)
                    use_mouse = False
            elif not self.game_over:
                # 鼠标模式下仍允许键盘微调
                keys = pygame.key.get_pressed()
                r = BALL_CONFIG[self.current_level][0]
                if keys[pygame.K_LEFT] or keys[pygame.K_RIGHT]:
                    use_mouse = False
                    if keys[pygame.K_LEFT]:
                        self.spawn_x = max(WALL_LEFT + r,
                                           self.spawn_x - MOVE_SPEED)
                    if keys[pygame.K_RIGHT]:
                        self.spawn_x = min(WALL_RIGHT - r,
                                           self.spawn_x + MOVE_SPEED)

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

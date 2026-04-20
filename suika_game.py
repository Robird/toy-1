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

# ──────────────────────────────────────
# 常量
# ──────────────────────────────────────
WIDTH, HEIGHT = 480, 750
FPS = 60
GRAVITY = 0.35
DAMPING = 0.985
RESTITUTION = 0.25
FLOOR_FRICTION = 0.92

WALL_THICKNESS = 12
WALL_LEFT = WALL_THICKNESS
WALL_RIGHT = WIDTH - WALL_THICKNESS
FLOOR_Y = HEIGHT - WALL_THICKNESS
DANGER_Y = 130          # 危险线高度
SPAWN_Y = 70            # 投放点高度
MOVE_SPEED = 6
DROP_COOLDOWN_FRAMES = 25
GAME_OVER_GRACE = 90    # 球超过危险线后的宽限帧数

COLLISION_ITERATIONS = 8

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
# Ball 类
# ──────────────────────────────────────
class Ball:
    __slots__ = ("x", "y", "vx", "vy", "level", "radius", "color",
                 "merged", "drop_frame", "settled_above_danger")

    def __init__(self, x, y, level, drop_frame=0):
        self.x = float(x)
        self.y = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.level = level
        cfg = BALL_CONFIG[level]
        self.radius = cfg[0]
        self.color = cfg[1]
        self.merged = False
        self.drop_frame = drop_frame
        self.settled_above_danger = 0

    # ---------- 物理更新 ----------
    def update(self):
        self.vy += GRAVITY
        self.vx *= DAMPING

        self.x += self.vx
        self.y += self.vy

        # 左右墙壁
        if self.x - self.radius < WALL_LEFT:
            self.x = WALL_LEFT + self.radius
            self.vx = abs(self.vx) * RESTITUTION
        elif self.x + self.radius > WALL_RIGHT:
            self.x = WALL_RIGHT - self.radius
            self.vx = -abs(self.vx) * RESTITUTION

        # 地板
        if self.y + self.radius > FLOOR_Y:
            self.y = FLOOR_Y - self.radius
            self.vy = -abs(self.vy) * RESTITUTION
            if abs(self.vy) < 0.8:
                self.vy = 0.0
            self.vx *= FLOOR_FRICTION

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
        return self.vx * self.vx + self.vy * self.vy


# ──────────────────────────────────────
# 碰撞检测 & 响应
# ──────────────────────────────────────
def collide_pair(b1, b2):
    """返回 (是否碰撞, 距离, dx, dy)"""
    dx = b2.x - b1.x
    dy = b2.y - b1.y
    dist_sq = dx * dx + dy * dy
    rsum = b1.radius + b2.radius
    if dist_sq < rsum * rsum:
        dist = math.sqrt(dist_sq) if dist_sq > 0 else 0.01
        return True, dist, dx, dy
    return False, 0, 0, 0


def resolve_bounce(b1, b2, dist, dx, dy):
    """弹性碰撞响应"""
    if dist < 0.01:
        dist = 0.01
        dx, dy = 0.01, 0.0

    nx = dx / dist
    ny = dy / dist
    overlap = (b1.radius + b2.radius) - dist

    # 近乎完美纵向堆叠时注入横向微扰，让上面的球滑落
    if abs(nx) < 0.08 and overlap > 0:
        nudge = random.choice([-1, 1]) * random.uniform(0.3, 0.8)
        b1.vx += nudge
        b2.vx -= nudge * 0.5

    # 按质量比（半径²）分配位移
    m1 = b1.radius * b1.radius
    m2 = b2.radius * b2.radius
    total = m1 + m2
    b1.x -= nx * overlap * (m2 / total)
    b1.y -= ny * overlap * (m2 / total)
    b2.x += nx * overlap * (m1 / total)
    b2.y += ny * overlap * (m1 / total)

    # 相对速度投影
    dvx = b1.vx - b2.vx
    dvy = b1.vy - b2.vy
    dvn = dvx * nx + dvy * ny

    if dvn > 0:
        j = dvn * (1 + RESTITUTION) / (1.0 / m1 + 1.0 / m2)
        b1.vx -= j * nx / m1
        b1.vy -= j * ny / m1
        b2.vx += j * nx / m2
        b2.vy += j * ny / m2


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
        self.reset()

    def reset(self):
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

    # ---------- 投放 ----------
    def drop_ball(self):
        if not self.can_drop or self.game_over:
            return
        # 投放时加随机微小扰动，避免完美纵向堆叠
        x_jitter = random.uniform(-1.5, 1.5)
        ball = Ball(self.spawn_x + x_jitter, SPAWN_Y, self.current_level, self.frame)
        ball.vx = random.uniform(-0.3, 0.3)
        self.balls.append(ball)
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

        # 物理
        for b in self.balls:
            b.update()

        # 碰撞 & 合并
        for _it in range(COLLISION_ITERATIONS):
            merge_pairs = []
            n = len(self.balls)
            for i in range(n):
                b1 = self.balls[i]
                if b1.merged:
                    continue
                for j in range(i + 1, n):
                    b2 = self.balls[j]
                    if b2.merged:
                        continue
                    hit, dist, dx, dy = collide_pair(b1, b2)
                    if not hit:
                        continue
                    if b1.level == b2.level and b1.level < MAX_LEVEL:
                        merge_pairs.append((i, j))
                    else:
                        resolve_bounce(b1, b2, dist, dx, dy)

            # 处理合并
            for i, j in merge_pairs:
                b1 = self.balls[i]
                b2 = self.balls[j]
                if b1.merged or b2.merged:
                    continue
                new_level = b1.level + 1
                nx = (b1.x + b2.x) / 2
                ny = (b1.y + b2.y) / 2
                new_ball = Ball(nx, ny, new_level, self.frame)
                # 给新球一个轻微弹跳
                new_ball.vy = -2.0
                self.balls.append(new_ball)
                b1.merged = True
                b2.merged = True
                self.score += BALL_CONFIG[new_level][3]
                if new_level > self.max_level_reached:
                    self.max_level_reached = new_level
                # 粒子特效
                for _ in range(10):
                    self.particles.append(
                        MergeParticle(nx, ny, BALL_CONFIG[new_level][1]))

            self.balls = [b for b in self.balls if not b.merged]

        # 游戏结束检测
        for b in self.balls:
            # 投放后至少 60 帧才判定
            if self.frame - b.drop_frame < 60:
                continue
            if b.y - b.radius < DANGER_Y and b.speed_sq < 2.0:
                b.settled_above_danger += 1
                if b.settled_above_danger > GAME_OVER_GRACE:
                    self.game_over = True
                    break
            else:
                b.settled_above_danger = 0

        # 粒子
        self._update_particles()

    def _update_particles(self):
        for p in self.particles:
            p.update()
        self.particles = [p for p in self.particles if p.life > 0]

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
    game = Game()
    game.run()

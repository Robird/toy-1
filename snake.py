"""
🐍 可爱贪吃蛇！🐍
用方向键控制小蛇，吃掉水果变长变强！
适合小朋友玩的 Pygame 小游戏~
"""
import pygame
import random
import math
import sys

from audio_utils import Timbre, concat_samples, generate_samples, make_sound, mix_samples, notes_to_samples
from audio_runtime import AudioRuntime, init_pygame_audio
from font_utils import load_font

# ===== 初始化 =====
init_pygame_audio()

# 屏幕 & 网格
CELL = 32          # 每格像素
COLS, ROWS = 20, 16
WIDTH = CELL * COLS   # 640
HEIGHT = CELL * ROWS  # 512
HUD_H = 56           # 顶部计分栏高度
WIN_W, WIN_H = WIDTH, HEIGHT + HUD_H

screen = pygame.display.set_mode((WIN_W, WIN_H))
pygame.display.set_caption("🐍 可爱贪吃蛇！")
clock = pygame.time.Clock()

# 颜色
WHITE   = (255, 255, 255)
BLACK   = (0,   0,   0)
YELLOW  = (255, 215, 0)
BG_A    = (30,  42,  56)   # 棋盘深色
BG_B    = (36,  50,  66)   # 棋盘浅色

SNAKE_COLORS = [
    (78,  205, 96),   # 头 - 翠绿
    (85,  230, 110),
    (100, 240, 130),
    (120, 245, 150),
    (140, 250, 170),  # 尾巴渐浅
]

FRUIT_TYPES = [
    {"emoji": "🍎", "color": (255, 70,  70),  "points": 1},
    {"emoji": "🍊", "color": (255, 165, 0),   "points": 1},
    {"emoji": "🍇", "color": (148, 103, 189), "points": 2},
    {"emoji": "🍓", "color": (255, 105, 140), "points": 1},
    {"emoji": "🌟", "color": (255, 215, 0),   "points": 3},
]

# 字体
font_big   = load_font(44, "microsoftyahei", "simhei", "simsun", fallback_size=52)
font_med   = load_font(28, "microsoftyahei", "simhei", "simsun", fallback_size=36)
font_small = load_font(20, "microsoftyahei", "simhei", "simsun", fallback_size=26)
font_emoji = load_font(24, "segoeuiemoji", fallback_size=30)

# ===== 音频生成 =====
print("正在生成音效...")

# 吃到水果 - 清脆上行
snd_eat = make_sound(
    concat_samples(
        generate_samples(660, 0.06),
        generate_samples(880, 0.06),
        generate_samples(1100, 0.10),
    )
)
# 吃到特殊水果(🌟/🍇) - 更华丽
snd_eat_special = make_sound(
    concat_samples(
        generate_samples(880, 0.05),
        generate_samples(1100, 0.05),
        generate_samples(1320, 0.05),
        generate_samples(1760, 0.12),
    )
)
# 转向 - 轻微咔嗒
snd_turn = make_sound(generate_samples(500, 0.03, volume=0.10))
# 撞墙/自己 - 低闷声
snd_die = make_sound(
    concat_samples(
        generate_samples(300, 0.15, timbre=Timbre.Triangle),
        generate_samples(200, 0.15, timbre=Timbre.Triangle),
        generate_samples(130, 0.30, timbre=Timbre.Triangle),
    )
)
# 重新开始
snd_restart = make_sound(
    concat_samples(
        generate_samples(523, 0.08),
        generate_samples(659, 0.08),
        generate_samples(784, 0.08),
        generate_samples(1047, 0.15),
    )
)

# BGM: 简单欢快的循环小调 (~4秒)
def _gen_bgm():
    melody = [
        ('E4',1),('E4',1),('F4',1),('G4',1),
        ('G4',1),('F4',1),('E4',1),('D4',1),
        ('C4',1),('C4',1),('D4',1),('E4',1),
        ('E4',1.5),('D4',0.5),('D4',2),
        ('E4',1),('E4',1),('F4',1),('G4',1),
        ('G4',1),('F4',1),('E4',1),('D4',1),
        ('C4',1),('C4',1),('D4',1),('E4',1),
        ('D4',1.5),('C4',0.5),('C4',2),
    ]
    bass = [
        ('C4',2),('C4',2),('C4',2),('G4',2),
        ('C4',2),('C4',2),('G4',2),('G4',2),
        ('C4',2),('C4',2),('C4',2),('G4',2),
        ('C4',2),('C4',2),('C4',4),
    ]
    beat = 0.20
    mel = notes_to_samples(melody, beat, volume=0.10, timbre=Timbre.Sine)
    bas = notes_to_samples(
        bass,
        beat,
        volume=0.05,
        timbre=Timbre.Triangle,
        freq_scale=0.5,
    )
    return make_sound(mix_samples(mel, bas))

snd_bgm = _gen_bgm()
print("音效就绪！")

# ===== 粒子 =====
class Particle:
    def __init__(self, x, y, color):
        self.x, self.y = x, y
        self.color = color
        self.vx = random.uniform(-4, 4)
        self.vy = random.uniform(-6, -1)
        self.life = 25
        self.r = random.uniform(2, 5)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.2
        self.life -= 1
        self.r = max(0, self.r - 0.12)

    def draw(self, surf):
        if self.life > 0 and self.r > 0:
            pygame.draw.circle(surf, self.color,
                               (int(self.x), int(self.y)), int(self.r))

# ===== 绘图辅助 =====
def grid_to_px(col, row):
    """网格坐标 → 像素左上角 (含 HUD 偏移)"""
    return col * CELL, row * CELL + HUD_H

def draw_rounded_rect(surf, color, rect, radius=8):
    """画圆角矩形"""
    pygame.draw.rect(surf, color, rect, border_radius=radius)

def draw_snake_segment(surf, col, row, idx, length, direction, is_head):
    """画蛇的一节身体（带渐变色与圆角）"""
    x, y = grid_to_px(col, row)
    # 颜色从头到尾渐变
    ci = min(idx, len(SNAKE_COLORS) - 1)
    ratio = idx / max(1, length - 1)
    c0 = SNAKE_COLORS[min(ci, len(SNAKE_COLORS) - 1)]
    c1 = SNAKE_COLORS[-1]
    color = tuple(int(c0[j] + (c1[j] - c0[j]) * ratio) for j in range(3))

    pad = 1
    draw_rounded_rect(surf, color,
                      (x + pad, y + pad, CELL - pad * 2, CELL - pad * 2), 10)

    if is_head:
        # 画眼睛 👀
        cx, cy = x + CELL // 2, y + CELL // 2
        dx, dy = direction
        # 两只眼睛的位置
        eye_offset = 6
        perp_x, perp_y = -dy, dx  # 垂直方向
        for side in (-1, 1):
            ex = cx + dx * 4 + perp_x * eye_offset * side
            ey = cy + dy * 4 + perp_y * eye_offset * side
            # 白色眼球
            pygame.draw.circle(surf, WHITE, (int(ex), int(ey)), 5)
            # 黑色瞳孔
            px = ex + dx * 2
            py = ey + dy * 2
            pygame.draw.circle(surf, BLACK, (int(px), int(py)), 2)

def draw_fruit(surf, col, row, fruit_type, anim_tick):
    """画水果（带轻微弹跳动画）"""
    x, y = grid_to_px(col, row)
    cx, cy = x + CELL // 2, y + CELL // 2

    # 弹跳
    bounce = math.sin(anim_tick * 0.1) * 3
    cy += int(bounce)

    # 光晕
    glow_r = int(CELL * 0.55 + math.sin(anim_tick * 0.08) * 3)
    glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
    glow_color = (*fruit_type["color"], 50)
    pygame.draw.circle(glow_surf, glow_color, (glow_r, glow_r), glow_r)
    surf.blit(glow_surf, (cx - glow_r, cy - glow_r))

    # 水果本体（圆形）
    r = CELL // 2 - 3
    pygame.draw.circle(surf, fruit_type["color"], (cx, cy), r)
    # 高光
    hl = tuple(min(c + 80, 255) for c in fruit_type["color"])
    pygame.draw.circle(surf, hl, (cx - 3, cy - 3), r // 3)

    # Emoji 文字
    try:
        txt = font_emoji.render(fruit_type["emoji"], True, WHITE)
        surf.blit(txt, (cx - txt.get_width() // 2, cy - txt.get_height() // 2))
    except Exception:
        pass

# ===== 游戏逻辑 =====
DIR_MAP = {
    pygame.K_UP:    (0, -1),
    pygame.K_DOWN:  (0,  1),
    pygame.K_LEFT:  (-1, 0),
    pygame.K_RIGHT: (1,  0),
    pygame.K_w:     (0, -1),
    pygame.K_s:     (0,  1),
    pygame.K_a:     (-1, 0),
    pygame.K_d:     (1,  0),
}

def spawn_fruit(snake_body):
    """在空白位置随机生成水果"""
    while True:
        pos = (random.randint(0, COLS - 1), random.randint(0, ROWS - 1))
        if pos not in snake_body:
            ft = random.choices(
                FRUIT_TYPES,
                weights=[35, 25, 15, 20, 5],  # 🌟 最稀有
                k=1
            )[0]
            return pos, ft

def main():
    # 蛇初始状态
    start_x, start_y = COLS // 2, ROWS // 2
    snake = [(start_x - i, start_y) for i in range(4)]  # 头在前
    direction = (1, 0)  # 向右
    next_dir = direction

    # 水果
    fruit_pos, fruit_type = spawn_fruit(set(snake))

    # 状态
    score = 0
    high_score = 0
    game_over = False
    paused = False

    # 速度控制 (越吃越快，但有下限)
    base_fps = 7
    move_fps = base_fps

    # 动画
    anim_tick = 0
    particles = []
    score_popups = []  # (text, px_x, px_y, timer, color)
    eat_flash = 0.0
    snake_grow = 0  # 待生长的节数

    # 音频
    audio = AudioRuntime(("bgm", "sfx"))
    bgm_ch = audio.bgm_channel
    sfx_ch = audio.channel("sfx")
    audio.play_bgm(snd_bgm, volume=0.5)

    # 鼠标锁定
    pygame.event.set_grab(True)

    # 移动计时 (用独立计时器控制蛇的移动速度，渲染帧率保持60fps)
    move_timer = 0.0
    last_time = pygame.time.get_ticks()

    running = True
    while running:
        # 时间
        now = pygame.time.get_ticks()
        dt = (now - last_time) / 1000.0
        last_time = now
        anim_tick += 1

        # 事件
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.event.set_grab(False)
                    running = False
                elif event.key == pygame.K_p:
                    paused = not paused
                elif event.key == pygame.K_r and game_over:
                    # 重新开始
                    snake = [(start_x - i, start_y) for i in range(4)]
                    direction = (1, 0)
                    next_dir = direction
                    fruit_pos, fruit_type = spawn_fruit(set(snake))
                    score = 0
                    game_over = False
                    paused = False
                    move_fps = base_fps
                    particles = []
                    score_popups = []
                    snake_grow = 0
                    eat_flash = 0.0
                    move_timer = 0.0
                    sfx_ch.play(snd_restart)
                    audio.restart_bgm()
                elif event.key in DIR_MAP and not game_over and not paused:
                    nd = DIR_MAP[event.key]
                    # 不能180度掉头
                    if (nd[0] + direction[0] != 0) or (nd[1] + direction[1] != 0):
                        if nd != direction:
                            next_dir = nd
                            sfx_ch.play(snd_turn)

        # 逻辑更新
        if not game_over and not paused:
            move_timer += dt / 4
            move_interval = 1.0 / move_fps

            while move_timer >= move_interval:
                move_timer -= move_interval
                direction = next_dir

                # 蛇头新位置
                hx, hy = snake[0]
                nx, ny = hx + direction[0], hy + direction[1]

                # 穿墙模式（对小朋友更友好）
                nx %= COLS
                ny %= ROWS

                # 撞自己？
                if (nx, ny) in set(snake[:-1]):
                    game_over = True
                    audio.fadeout_bgm(500)
                    sfx_ch.play(snd_die)
                    high_score = max(high_score, score)
                    # 死亡粒子效果
                    px, py = grid_to_px(hx, hy)
                    for _ in range(30):
                        particles.append(Particle(
                            px + CELL // 2, py + CELL // 2,
                            random.choice([(255,80,80),(255,160,60),(255,220,50)])
                        ))
                    break

                # 移动蛇
                snake.insert(0, (nx, ny))
                if snake_grow > 0:
                    snake_grow -= 1
                else:
                    snake.pop()

                # 吃水果？
                if (nx, ny) == fruit_pos:
                    pts = fruit_type["points"]
                    score += pts
                    snake_grow += pts  # 高分水果多长几节

                    # 速度提升
                    move_fps = min(15, base_fps + score // 5)

                    # 音效
                    if pts >= 2:
                        sfx_ch.play(snd_eat_special)
                    else:
                        sfx_ch.play(snd_eat)

                    # 粒子
                    px, py = grid_to_px(nx, ny)
                    for _ in range(20):
                        particles.append(Particle(
                            px + CELL // 2, py + CELL // 2,
                            fruit_type["color"]
                        ))

                    # 得分弹出
                    score_popups.append(
                        (f"+{pts}", px + CELL // 2, py, 35, fruit_type["color"])
                    )
                    eat_flash = 1.0

                    # 新水果
                    fruit_pos, fruit_type = spawn_fruit(set(snake))

        # 粒子更新
        for p in particles[:]:
            p.update()
            if p.life <= 0:
                particles.remove(p)

        # 得分弹出更新
        for i, (t, x, y, timer, c) in enumerate(score_popups):
            score_popups[i] = (t, x, y - 1.2, timer - 1, c)
        score_popups = [s for s in score_popups if s[3] > 0]

        eat_flash = max(0.0, eat_flash - 0.04)

        # ===== 绘制 =====
        screen.fill(BG_A)

        # HUD 背景
        pygame.draw.rect(screen, (20, 30, 45), (0, 0, WIN_W, HUD_H))
        pygame.draw.line(screen, (50, 70, 100), (0, HUD_H - 1), (WIN_W, HUD_H - 1), 2)

        # 分数
        stxt = font_med.render(f"🐍 分数: {score}", True, YELLOW)
        screen.blit(stxt, (16, 12))
        # 蛇长度
        lt = font_small.render(f"长度: {len(snake)}", True, (170, 200, 220))
        screen.blit(lt, (WIN_W - 120, 18))

        # 棋盘背景
        for r in range(ROWS):
            for c in range(COLS):
                x, y = grid_to_px(c, r)
                color = BG_A if (r + c) % 2 == 0 else BG_B
                pygame.draw.rect(screen, color, (x, y, CELL, CELL))

        # 吃到水果的全屏微闪
        if eat_flash > 0:
            flash_surf = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            alpha = int(eat_flash * 40)
            flash_surf.fill((255, 255, 200, alpha))
            screen.blit(flash_surf, (0, 0))

        # 水果
        draw_fruit(screen, fruit_pos[0], fruit_pos[1], fruit_type, anim_tick)

        # 蛇身
        for idx, (sc, sr) in enumerate(snake):
            draw_snake_segment(screen, sc, sr, idx, len(snake),
                               direction, is_head=(idx == 0))

        # 粒子
        for p in particles:
            p.draw(screen)

        # 得分弹出
        for text, px, py, timer, color in score_popups:
            alpha = min(255, timer * 8)
            tsurf = font_med.render(text, True, color)
            screen.blit(tsurf, (int(px) - tsurf.get_width() // 2, int(py)))

        # 暂停
        if paused and not game_over:
            ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 120))
            screen.blit(ov, (0, 0))
            pt = font_big.render("⏸ 暂停", True, YELLOW)
            screen.blit(pt, (WIN_W // 2 - pt.get_width() // 2, WIN_H // 2 - 30))
            ht = font_small.render("按 P 继续", True, (200, 200, 200))
            screen.blit(ht, (WIN_W // 2 - ht.get_width() // 2, WIN_H // 2 + 30))

        # Game Over
        if game_over:
            ov = pygame.Surface((WIN_W, WIN_H), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 160))
            screen.blit(ov, (0, 0))

            gt = font_big.render("💥 游戏结束！", True, (255, 100, 80))
            screen.blit(gt, (WIN_W // 2 - gt.get_width() // 2, WIN_H // 2 - 90))

            ft = font_med.render(f"得分: {score}   长度: {len(snake)}", True, WHITE)
            screen.blit(ft, (WIN_W // 2 - ft.get_width() // 2, WIN_H // 2 - 25))

            if score == high_score and score > 0:
                nt = font_med.render("🏆 新纪录！", True, YELLOW)
                screen.blit(nt, (WIN_W // 2 - nt.get_width() // 2, WIN_H // 2 + 20))

            if score >= 20:
                msg, mc = "🐍 超级长蛇！太厉害了！", YELLOW
            elif score >= 10:
                msg, mc = "👍 很棒！再接再厉！", (85, 239, 196)
            else:
                msg, mc = "😊 不错哦！再来一次吧！", (116, 185, 255)
            mt = font_small.render(msg, True, mc)
            screen.blit(mt, (WIN_W // 2 - mt.get_width() // 2, WIN_H // 2 + 60))

            rt = font_small.render("按 R 重新开始 | 按 ESC 退出", True, (180, 180, 180))
            screen.blit(rt, (WIN_W // 2 - rt.get_width() // 2, WIN_H // 2 + 105))

        pygame.display.flip()
        clock.tick(60)

    pygame.event.set_grab(False)
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()

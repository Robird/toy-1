"""
⌨️ 打字保卫战！⌨️
太空侵略者风格的打字防御游戏
看到敌方发来的字符，按对应键发射相同字符来防御！
空闲时主动进攻，击败 BOSS！
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

# ===== 常量 =====
WIDTH, HEIGHT = 900, 640
FPS = 60

# 字符 → pygame 键码 映射（A-Z + 0-9）
CHAR_TO_CODE = {chr(c): getattr(pygame, f"K_{chr(c).lower()}") for c in range(ord('A'), ord('Z') + 1)}
CHAR_TO_CODE.update({str(d): getattr(pygame, f"K_{d}") for d in range(10)})

def make_key_codes(chars):
    """将字符序列（字符串或列表）转换为 {pygame_key_code: 索引} 字典，用于关卡键位配置。
    示例: make_key_codes("FGHJ") → {K_f: 0, K_g: 1, K_h: 2, K_j: 3}
    """
    return {CHAR_TO_CODE[ch.upper()]: i for i, ch in enumerate(chars)}

# 键位设定 —— 只需修改 KEYS 即可切换关卡键位
# 示例: list("FJ"), list("FGHJ"), list("ASDFGHJKL"), list("QWERTYUIOP")
# KEYS = list("QWERTYUIOP")
# KEYS = list("FGHJ")
KEYS = list("FJ")
# KEYS = list("FG")
# KEYS = list("F")
# KEYS = list("A")
# KEYS = list("R")

KEY_CODES = make_key_codes(KEYS)

N_COLS = len(KEYS)

# 布局
MARGIN_X = 70               # 两侧留白
FIELD_W = WIDTH - MARGIN_X * 2  # 战场宽度
COL_W = FIELD_W // N_COLS    # 每列宽度
FIELD_TOP = 90               # 战场顶端 Y（敌方发射线）
FIELD_BOT = HEIGHT - 100     # 战场底端 Y（我方发射线）
FIELD_H = FIELD_BOT - FIELD_TOP

# 子弹速度（像素/帧）—— 偏慢，给小朋友反应时间
BULLET_SPEED = 1.8

# 冷却时间（帧）—— 所有键共享 CD，防止乱按
COOLDOWN_FRAMES = 35  # ≈ 0.58 秒（共享 CD，比独立 CD 短一些）

# HP
PLAYER_MAX_HP = 15
ENEMY_MAX_HP = 30

# 颜色
WHITE    = (255, 255, 255)
BLACK    = (0,   0,   0)
YELLOW   = (255, 215, 0)
RED      = (255, 80,  80)
GREEN    = (80,  220, 120)
CYAN     = (80,  220, 255)
DARKBG   = (14,  20,  32)

# 每列颜色（彩虹渐变）
import colorsys
COL_COLORS = []
for i in range(N_COLS):
    r, g, b = colorsys.hsv_to_rgb(i / N_COLS, 0.75, 1.0)
    COL_COLORS.append((int(r * 255), int(g * 255), int(b * 255)))

# 敌方子弹颜色（偏红/暗）
ENEMY_BULLET_COLOR = (255, 90, 90)

screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("⌨️ 打字保卫战！")
clock = pygame.time.Clock()

# 字体
font_big    = load_font(42, "microsoftyahei", "simhei", "simsun", fallback_size=50)
font_med    = load_font(26, "microsoftyahei", "simhei", "simsun", fallback_size=32)
font_small  = load_font(18, "microsoftyahei", "simhei", "simsun", fallback_size=24)
font_key    = load_font(22, "consolas", fallback_size=28, bold=True)
font_bullet = load_font(20, "consolas", fallback_size=26, bold=True)


# ===== 音频生成 =====
print("正在生成音效...")

# 我方发射 - 清脆短促
snd_shoot = make_sound(
    concat_samples(
        generate_samples(700, 0.05, volume=0.15),
        generate_samples(900, 0.04, volume=0.12),
    )
)
# 碰撞抵消 - 叮一声
snd_clash = make_sound(
    concat_samples(
        generate_samples(1200, 0.04, volume=0.18),
        generate_samples(1500, 0.06, volume=0.14),
    )
)
# 敌方被击中 - 沉闷爆破
snd_enemy_hit = make_sound(
    concat_samples(
        generate_samples(400, 0.08, volume=0.20, timbre=Timbre.Triangle),
        generate_samples(600, 0.06, volume=0.15),
    )
)
# 我方被击中 - 低沉警告
snd_player_hit = make_sound(
    concat_samples(
        generate_samples(200, 0.12, volume=0.22, timbre=Timbre.Triangle),
        generate_samples(150, 0.15, volume=0.18, timbre=Timbre.Triangle),
    )
)
# 冷却中按键 - 闷响提示
snd_cooldown = make_sound(generate_samples(250, 0.06, volume=0.08, timbre=Timbre.Square))
# 胜利
snd_win = make_sound(
    concat_samples(
        generate_samples(523, 0.12),
        generate_samples(659, 0.12),
        generate_samples(784, 0.12),
        generate_samples(1047, 0.25),
    )
)
# 失败
snd_lose = make_sound(
    concat_samples(
        generate_samples(400, 0.2, timbre=Timbre.Triangle),
        generate_samples(300, 0.2, timbre=Timbre.Triangle),
        generate_samples(200, 0.3, timbre=Timbre.Triangle),
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

# BGM - 紧张的进行曲风格
def _gen_bgm():
    melody = [
        ('E4',1),('E4',0.5),('E4',0.5),('C4',1),('E4',1),
        ('G4',2),('R',1),('G4',1),
        ('C5',1),('R',0.5),('G4',0.5),('R',1),('E4',1),
        ('A4',1),('B4',1),('Bb4',0.5),('A4',1.5),
        ('G4',1),('E5',1),('G4',1),('A4',1),
        ('F4',1),('G4',1),('R',0.5),('E4',0.5),
        ('C4',1),('D4',1),('B4',2),
    ]
    beat = 0.16
    mel = notes_to_samples(melody, beat, volume=0.09, timbre=Timbre.Sine)
    bas_notes = [
        ('C4',2),('G4',2),('C4',2),('G4',2),
        ('C4',2),('E4',2),('G4',2),('C4',2),
        ('A4',2),('E4',2),('G4',2),('C4',2),
        ('F4',2),('C4',2),('G4',4),
    ]
    bas = notes_to_samples(
        bas_notes,
        beat,
        volume=0.04,
        timbre=Timbre.Triangle,
        freq_scale=0.5,
    )
    return make_sound(mix_samples(mel, bas))

snd_bgm = _gen_bgm()
print("音效就绪！")


# ===== 粒子系统 =====
class Particle:
    def __init__(self, x, y, color, speed_mult=1.0):
        self.x, self.y = x, y
        self.color = color
        self.vx = random.uniform(-3, 3) * speed_mult
        self.vy = random.uniform(-3, 3) * speed_mult
        self.life = random.randint(15, 30)
        self.r = random.uniform(2, 5)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.life -= 1
        self.r = max(0, self.r - 0.1)

    def draw(self, surf):
        if self.life > 0 and self.r > 0:
            alpha_ratio = self.life / 30
            c = tuple(max(0, min(255, int(ch * alpha_ratio))) for ch in self.color)
            pygame.draw.circle(surf, c, (int(self.x), int(self.y)), int(self.r))


# ===== 子弹类 =====
class Bullet:
    def __init__(self, col_idx, y, direction, char):
        """
        col_idx: 列索引 (0-9)
        y: 起始 Y
        direction: +1 向下（敌方）, -1 向上（我方）
        char: 字符
        """
        self.col = col_idx
        self.x = MARGIN_X + col_idx * COL_W + COL_W // 2
        self.y = y
        self.direction = direction
        self.char = char
        self.alive = True
        self.speed = BULLET_SPEED

        # 视觉
        if direction == -1:
            # 我方：该列的彩色
            self.color = COL_COLORS[col_idx]
        else:
            # 敌方：红色系
            self.color = ENEMY_BULLET_COLOR

        self.trail = []  # 拖尾位置

    def update(self):
        # 拖尾
        self.trail.append((self.x, self.y))
        if len(self.trail) > 8:
            self.trail.pop(0)

        self.y += self.speed * self.direction

        # 出界检测
        if self.direction == -1 and self.y < FIELD_TOP - 20:
            self.alive = False
        elif self.direction == 1 and self.y > FIELD_BOT + 20:
            self.alive = False

    def draw(self, surf, anim_tick):
        if not self.alive:
            return

        # 拖尾
        for i, (tx, ty) in enumerate(self.trail):
            ratio = i / max(1, len(self.trail))
            alpha = ratio * 0.4
            r = int(12 * ratio)
            if r > 0:
                c = tuple(int(ch * alpha) for ch in self.color)
                pygame.draw.circle(surf, c, (int(tx), int(ty)), r)

        # 子弹本体 - 圆形气泡
        radius = 16
        # 光晕
        glow_r = radius + 4 + int(math.sin(anim_tick * 0.15) * 2)
        glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        glow_c = (*self.color, 60)
        pygame.draw.circle(glow_surf, glow_c, (glow_r, glow_r), glow_r)
        surf.blit(glow_surf, (int(self.x) - glow_r, int(self.y) - glow_r))

        # 气泡
        pygame.draw.circle(surf, self.color, (int(self.x), int(self.y)), radius)

        # 边框
        border = tuple(min(255, c + 60) for c in self.color)
        pygame.draw.circle(surf, border, (int(self.x), int(self.y)), radius, 2)

        # 字符
        txt = font_bullet.render(self.char, True, WHITE)
        surf.blit(txt, (int(self.x) - txt.get_width() // 2,
                        int(self.y) - txt.get_height() // 2))


# ===== 碰撞闪光 =====
class ClashFlash:
    def __init__(self, x, y, color):
        self.x, self.y = x, y
        self.color = color
        self.life = 15
        self.max_life = 15

    def update(self):
        self.life -= 1

    def draw(self, surf):
        if self.life <= 0:
            return
        ratio = self.life / self.max_life
        r = int(30 * (1 - ratio))
        alpha = int(200 * ratio)
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        c = (*self.color, alpha)
        pygame.draw.circle(s, c, (r, r), r)
        surf.blit(s, (int(self.x) - r, int(self.y) - r))


# ===== 绘图辅助 =====
def col_center_x(col_idx):
    """列的中心 X 坐标"""
    return MARGIN_X + col_idx * COL_W + COL_W // 2

def draw_hp_bar(surf, x, y, w, h, current, maximum, color, label=""):
    """绘制 HP 条"""
    # 背景
    pygame.draw.rect(surf, (40, 40, 50), (x, y, w, h), border_radius=4)
    # HP 填充
    fill_w = int(w * max(0, current) / maximum)
    if fill_w > 0:
        pygame.draw.rect(surf, color, (x, y, fill_w, h), border_radius=4)
    # 边框
    pygame.draw.rect(surf, (100, 100, 120), (x, y, w, h), 2, border_radius=4)
    # 文字
    if label:
        txt = font_small.render(f"{label} {current}/{maximum}", True, WHITE)
        surf.blit(txt, (x + w // 2 - txt.get_width() // 2,
                        y + h // 2 - txt.get_height() // 2))

def draw_key_slot(surf, col_idx, cooldown_ratio, is_pressed, anim_tick):
    """绘制底部的按键槽位"""
    cx = col_center_x(col_idx)
    y = FIELD_BOT + 18
    size = 36
    half = size // 2

    # 冷却完毕 → 呼吸发光
    ready = cooldown_ratio <= 0

    # 底板
    if is_pressed:
        bg_color = (180, 200, 255)
    elif ready:
        pulse = 0.6 + 0.4 * math.sin(anim_tick * 0.08)
        bg_color = tuple(int(c * pulse) for c in COL_COLORS[col_idx])
    else:
        bg_color = (40, 45, 55)

    pygame.draw.rect(surf, bg_color,
                     (cx - half, y, size, size), border_radius=6)
    pygame.draw.rect(surf, COL_COLORS[col_idx],
                     (cx - half, y, size, size), 2, border_radius=6)

    # CD 遮罩（从下往上消退）
    if cooldown_ratio > 0:
        mask_h = int(size * cooldown_ratio)
        mask_surf = pygame.Surface((size, mask_h), pygame.SRCALPHA)
        mask_surf.fill((0, 0, 0, 140))
        surf.blit(mask_surf, (cx - half, y + size - mask_h))

    # 字符
    char_color = WHITE if ready else (120, 120, 130)
    txt = font_key.render(KEYS[col_idx], True, char_color)
    surf.blit(txt, (cx - txt.get_width() // 2, y + size // 2 - txt.get_height() // 2))

def draw_enemy_slot(surf, col_idx, anim_tick):
    """绘制顶部的敌方发射器"""
    cx = col_center_x(col_idx)
    y = FIELD_TOP - 38
    size = 28
    half = size // 2

    # 微妙的红色呼吸
    pulse = 0.5 + 0.2 * math.sin(anim_tick * 0.05 + col_idx * 0.5)
    c = (int(180 * pulse), int(40 * pulse), int(40 * pulse))
    pygame.draw.rect(surf, c, (cx - half, y, size, size), border_radius=4)
    pygame.draw.rect(surf, (180, 60, 60), (cx - half, y, size, size), 1, border_radius=4)

    txt = font_small.render(KEYS[col_idx], True, (200, 100, 100))
    surf.blit(txt, (cx - txt.get_width() // 2, y + size // 2 - txt.get_height() // 2))

def draw_column_lanes(surf):
    """绘制战场列分隔线（淡淡的）"""
    for i in range(N_COLS + 1):
        x = MARGIN_X + i * COL_W
        pygame.draw.line(surf, (30, 35, 50), (x, FIELD_TOP), (x, FIELD_BOT), 1)
    # 上下边界线
    pygame.draw.line(surf, (60, 80, 110), (MARGIN_X, FIELD_TOP), (MARGIN_X + FIELD_W, FIELD_TOP), 2)
    pygame.draw.line(surf, (60, 110, 80), (MARGIN_X, FIELD_BOT), (MARGIN_X + FIELD_W, FIELD_BOT), 2)


# ===== 敌方 AI =====
class EnemyAI:
    def __init__(self):
        self.reset()

    def reset(self):
        self.timer = 0
        self.base_interval = 90    # 初始：每 90 帧 ≈ 1.5 秒射一次
        self.min_interval = 25     # 最快
        self.difficulty = 0        # 随时间增加

    def update(self, frame_count):
        self.timer += 1
        # 难度随时间缓慢提高
        self.difficulty = min(60, frame_count // (FPS * 8))  # 每8秒加一档，上限60
        interval = max(self.min_interval,
                       self.base_interval - self.difficulty)

        if self.timer >= interval:
            self.timer = 0
            # 射多少发？难度高了可能同时射两发
            n_shots = 1
            if self.difficulty > 20 and random.random() < 0.25:
                n_shots = 2
            if self.difficulty > 40 and random.random() < 0.15:
                n_shots = 3

            cols = random.sample(range(N_COLS), min(n_shots, N_COLS))
            return cols
        return []


# ===== 主游戏 =====
def main():
    # 游戏状态
    player_hp = PLAYER_MAX_HP
    enemy_hp = ENEMY_MAX_HP
    score = 0
    game_over = False
    game_won = False

    # 子弹
    player_bullets = []
    enemy_bullets = []

    # 冷却 (所有键共享，0 = 就绪)
    shared_cooldown = 0

    # 按键闪烁
    key_pressed = [0] * N_COLS  # 按下后闪几帧

    # 视觉效果
    particles = []
    flashes = []
    score_popups = []   # (text, x, y, timer, color)
    hit_flash_player = 0.0   # 受击全屏闪
    hit_flash_enemy = 0.0

    # 敌方 AI
    enemy_ai = EnemyAI()
    frame_count = 0
    anim_tick = 0

    # 音频
    audio = AudioRuntime(("bgm", "sfx", "sfx2", "sfx3"))
    bgm_ch = audio.bgm_channel
    sfx_ch = audio.channel("sfx")
    sfx_ch2 = audio.channel("sfx2")
    sfx_ch3 = audio.channel("sfx3")
    audio.play_bgm(snd_bgm, volume=0.45)

    running = True

    while running:
        anim_tick += 1
        frame_count += 1

        # 事件
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                elif event.key == pygame.K_r and (game_over or game_won):
                    # 重新开始
                    player_hp = PLAYER_MAX_HP
                    enemy_hp = ENEMY_MAX_HP
                    score = 0
                    game_over = False
                    game_won = False
                    player_bullets = []
                    enemy_bullets = []
                    shared_cooldown = 0
                    key_pressed = [0] * N_COLS
                    particles = []
                    flashes = []
                    score_popups = []
                    hit_flash_player = 0.0
                    hit_flash_enemy = 0.0
                    enemy_ai.reset()
                    frame_count = 0
                    sfx_ch.play(snd_restart)
                    audio.restart_bgm()

                elif event.key in KEY_CODES and not game_over and not game_won:
                    col = KEY_CODES[event.key]
                    if shared_cooldown <= 0:
                        # 发射！
                        b = Bullet(col, FIELD_BOT, -1, KEYS[col])
                        player_bullets.append(b)
                        shared_cooldown = COOLDOWN_FRAMES
                        key_pressed[col] = 8
                        sfx_ch.play(snd_shoot)
                    else:
                        # CD 中
                        sfx_ch3.play(snd_cooldown)
                        key_pressed[col] = 4

        if not game_over and not game_won:
            # === 冷却更新 ===
            if shared_cooldown > 0:
                shared_cooldown -= 1
            for i in range(N_COLS):
                if key_pressed[i] > 0:
                    key_pressed[i] -= 1

            # === 敌方 AI ===
            shot_cols = enemy_ai.update(frame_count)
            for col in shot_cols:
                b = Bullet(col, FIELD_TOP, +1, KEYS[col])
                enemy_bullets.append(b)

            # === 更新子弹 ===
            for b in player_bullets:
                b.update()
            for b in enemy_bullets:
                b.update()

            # === 碰撞检测：同列的我方子弹 vs 敌方子弹 ===
            for pb in player_bullets:
                if not pb.alive:
                    continue
                for eb in enemy_bullets:
                    if not eb.alive:
                        continue
                    if pb.col != eb.col:
                        continue
                    # 同列 → 检测 Y 距离
                    if abs(pb.y - eb.y) < 28:
                        # 碰撞！抵消！
                        pb.alive = False
                        eb.alive = False
                        mid_y = (pb.y + eb.y) / 2
                        cx = col_center_x(pb.col)
                        # 粒子爆炸
                        for _ in range(18):
                            particles.append(Particle(cx, mid_y,
                                                      COL_COLORS[pb.col], 1.2))
                        flashes.append(ClashFlash(cx, mid_y, COL_COLORS[pb.col]))
                        sfx_ch2.play(snd_clash)
                        score += 1
                        score_popups.append(
                            ("防御 +1", cx, mid_y - 10, 35, COL_COLORS[pb.col])
                        )

            # === 我方子弹到达顶端 → 击中敌方 ===
            for pb in player_bullets:
                if not pb.alive:
                    continue
                if pb.y <= FIELD_TOP:
                    pb.alive = False
                    enemy_hp -= 1
                    score += 2
                    hit_flash_enemy = 1.0
                    cx = col_center_x(pb.col)
                    for _ in range(12):
                        particles.append(Particle(cx, FIELD_TOP, (255, 160, 60), 1.0))
                    flashes.append(ClashFlash(cx, FIELD_TOP, (255, 200, 60)))
                    sfx_ch2.play(snd_enemy_hit)
                    score_popups.append(
                        ("进攻 +2", cx, FIELD_TOP + 10, 35, YELLOW)
                    )
                    if enemy_hp <= 0:
                        game_won = True
                        audio.fadeout_bgm(800)
                        sfx_ch.play(snd_win)

            # === 敌方子弹到达底端 → 击中我方 ===
            for eb in enemy_bullets:
                if not eb.alive:
                    continue
                if eb.y >= FIELD_BOT:
                    eb.alive = False
                    player_hp -= 1
                    hit_flash_player = 1.0
                    cx = col_center_x(eb.col)
                    for _ in range(12):
                        particles.append(Particle(cx, FIELD_BOT, (255, 80, 80), 1.0))
                    flashes.append(ClashFlash(cx, FIELD_BOT, RED))
                    sfx_ch2.play(snd_player_hit)
                    if player_hp <= 0:
                        game_over = True
                        audio.fadeout_bgm(800)
                        sfx_ch.play(snd_lose)

            # === 清理死亡子弹 ===
            player_bullets = [b for b in player_bullets if b.alive]
            enemy_bullets = [b for b in enemy_bullets if b.alive]

        # === 粒子/效果更新 ===
        for p in particles[:]:
            p.update()
            if p.life <= 0:
                particles.remove(p)

        for f in flashes[:]:
            f.update()
            if f.life <= 0:
                flashes.remove(f)

        for i, (t, x, y, timer, c) in enumerate(score_popups):
            score_popups[i] = (t, x, y - 1.0, timer - 1, c)
        score_popups = [s for s in score_popups if s[3] > 0]

        hit_flash_player = max(0, hit_flash_player - 0.05)
        hit_flash_enemy = max(0, hit_flash_enemy - 0.05)

        # ==================== 绘制 ====================
        screen.fill(DARKBG)

        # 星空背景（点点星光）
        random.seed(42)  # 固定种子让背景不闪烁
        for _ in range(60):
            sx = random.randint(0, WIDTH)
            sy = random.randint(0, HEIGHT)
            br = random.randint(60, 150)
            screen.set_at((sx, sy), (br, br, br + 20))
        random.seed()  # 恢复随机

        # 列分隔线
        draw_column_lanes(screen)

        # 顶部 HUD: 敌方 HP
        draw_hp_bar(screen, WIDTH // 2 - 160, 10, 320, 22,
                    enemy_hp, ENEMY_MAX_HP, (200, 60, 60), "👾 BOSS")

        # 底部 HUD: 我方 HP
        draw_hp_bar(screen, WIDTH // 2 - 160, HEIGHT - 30, 320, 22,
                    player_hp, PLAYER_MAX_HP, (60, 200, 120), "🛡️ 我方")

        # 分数
        stxt = font_med.render(f"⭐ {score}", True, YELLOW)
        screen.blit(stxt, (16, 8))

        # 难度指示
        diff_txt = font_small.render(
            f"难度 Lv.{enemy_ai.difficulty // 10 + 1}", True, (150, 150, 170))
        screen.blit(diff_txt, (WIDTH - 110, 12))

        # 敌方发射器
        for i in range(N_COLS):
            draw_enemy_slot(screen, i, anim_tick)

        # 受击闪烁（敌方区域）
        if hit_flash_enemy > 0:
            s = pygame.Surface((FIELD_W + 20, 50), pygame.SRCALPHA)
            s.fill((255, 200, 50, int(hit_flash_enemy * 100)))
            screen.blit(s, (MARGIN_X - 10, FIELD_TOP - 45))

        # 受击闪烁（我方区域）
        if hit_flash_player > 0:
            s = pygame.Surface((FIELD_W + 20, 60), pygame.SRCALPHA)
            s.fill((255, 50, 50, int(hit_flash_player * 80)))
            screen.blit(s, (MARGIN_X - 10, FIELD_BOT))

        # 子弹
        for b in enemy_bullets:
            b.draw(screen, anim_tick)
        for b in player_bullets:
            b.draw(screen, anim_tick)

        # 碰撞闪光
        for f in flashes:
            f.draw(screen)

        # 粒子
        for p in particles:
            p.draw(screen)

        # 我方键位
        cd_ratio = shared_cooldown / COOLDOWN_FRAMES if shared_cooldown > 0 else 0
        for i in range(N_COLS):
            draw_key_slot(screen, i, cd_ratio, key_pressed[i] > 0, anim_tick)

        # 得分弹出
        for text, x, y, timer, color in score_popups:
            t = font_small.render(text, True, color)
            screen.blit(t, (int(x) - t.get_width() // 2, int(y)))

        # === 胜利画面 ===
        if game_won:
            ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 140))
            screen.blit(ov, (0, 0))

            wt = font_big.render("🎉 胜利！BOSS 被击败了！", True, YELLOW)
            screen.blit(wt, (WIDTH // 2 - wt.get_width() // 2, HEIGHT // 2 - 70))

            st = font_med.render(f"总得分: {score}", True, WHITE)
            screen.blit(st, (WIDTH // 2 - st.get_width() // 2, HEIGHT // 2 - 10))

            mt = font_small.render("你是打字小英雄！ 🏆", True, (85, 239, 196))
            screen.blit(mt, (WIDTH // 2 - mt.get_width() // 2, HEIGHT // 2 + 35))

            rt = font_small.render("按 R 再来一局 | 按 ESC 退出", True, (180, 180, 180))
            screen.blit(rt, (WIDTH // 2 - rt.get_width() // 2, HEIGHT // 2 + 80))

        # === 失败画面 ===
        if game_over:
            ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 140))
            screen.blit(ov, (0, 0))

            gt = font_big.render("💥 防线失守！", True, RED)
            screen.blit(gt, (WIDTH // 2 - gt.get_width() // 2, HEIGHT // 2 - 70))

            st = font_med.render(f"得分: {score}   BOSS 剩余: {enemy_hp} HP", True, WHITE)
            screen.blit(st, (WIDTH // 2 - st.get_width() // 2, HEIGHT // 2 - 10))

            if score >= 30:
                msg, mc = "💪 打得已经很好了！再来！", (85, 239, 196)
            elif score >= 15:
                msg, mc = "👍 不错！多练练键盘就更强了！", (116, 185, 255)
            else:
                msg, mc = "😊 加油！认识键盘就能赢！", (200, 200, 220)
            mt = font_small.render(msg, True, mc)
            screen.blit(mt, (WIDTH // 2 - mt.get_width() // 2, HEIGHT // 2 + 35))

            rt = font_small.render("按 R 再来一局 | 按 ESC 退出", True, (180, 180, 180))
            screen.blit(rt, (WIDTH // 2 - rt.get_width() // 2, HEIGHT // 2 + 80))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()

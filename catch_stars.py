"""
⭐ 接星星小游戏！⭐
用鼠标左右移动小篮子，接住掉下来的彩色星星！
适合小朋友玩的 Pygame 小游戏~
"""
import pygame
import random
import math
import sys
import array

# 初始化
pygame.mixer.pre_init(44100, -16, 2, 512)
pygame.init()

# 屏幕设置
WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("⭐ 接星星！⭐")

# 颜色
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
YELLOW = (255, 215, 0)
COLORS = [
    (255, 107, 107),   # 红
    (78, 205, 196),    # 青
    (255, 234, 167),   # 黄
    (129, 236, 236),   # 浅蓝
    (255, 118, 117),   # 粉红
    (85, 239, 196),    # 浅绿
    (253, 203, 110),   # 橙
    (116, 185, 255),   # 蓝
    (223, 230, 233),   # 浅灰白
    (255, 105, 180),   # 热粉
    (50, 205, 50),     # 绿
    (255, 69, 0),      # 橙红
]

# 节拍常量（与 BGM 生成保持一致）
BEAT_DUR = 0.28       # 每拍秒数
BEATS_PER_LOOP = 48   # BGM 一轮总拍数 (小星星完整一遍)
FPS = 60
CATCH_Y = HEIGHT - 70 # 接星星的 Y 坐标

# 字体
try:
    font_big = pygame.font.SysFont("microsoftyahei", 48)
    font_med = pygame.font.SysFont("microsoftyahei", 32)
    font_small = pygame.font.SysFont("microsoftyahei", 24)
except:
    font_big = pygame.font.Font(None, 56)
    font_med = pygame.font.Font(None, 40)
    font_small = pygame.font.Font(None, 30)

clock = pygame.time.Clock()

# ===== 音频生成 =====
SAMPLE_RATE = 44100

def _make_samples(freq, duration, volume=0.3, wave="sine", fade_out=True, fade_in=0.01):
    """生成原始音频采样数据"""
    n_samples = int(SAMPLE_RATE * duration)
    samples = []
    for i in range(n_samples):
        t = i / SAMPLE_RATE
        # 波形
        if wave == "sine":
            val = math.sin(2 * math.pi * freq * t)
        elif wave == "square":
            val = 1.0 if math.sin(2 * math.pi * freq * t) >= 0 else -1.0
            val *= 0.4  # 方波音量小一点
        elif wave == "triangle":
            val = 2 * abs(2 * (t * freq - math.floor(t * freq + 0.5))) - 1
        else:
            val = math.sin(2 * math.pi * freq * t)
        # 包络 - 淡入
        fade_in_samples = int(SAMPLE_RATE * fade_in)
        if i < fade_in_samples:
            val *= i / fade_in_samples
        # 包络 - 淡出
        if fade_out:
            fade_start = int(n_samples * 0.6)
            if i > fade_start:
                val *= 1.0 - (i - fade_start) / (n_samples - fade_start)
        val *= volume
        samples.append(int(val * 32767))
    return samples

def make_sound(samples_list):
    """从采样列表创建 pygame.mixer.Sound（立体声）"""
    mono = array.array('h', samples_list)
    stereo = array.array('h', [0]) * (len(mono) * 2)
    stereo[0::2] = mono  # 左声道
    stereo[1::2] = mono  # 右声道
    sound = pygame.mixer.Sound(buffer=stereo)
    return sound

def generate_catch_sound():
    """接住星星：欢快的上升叮咚声"""
    samples = []
    # 两个快速上升的音符
    notes = [(880, 0.06), (1175, 0.06), (1397, 0.1)]
    for freq, dur in notes:
        samples.extend(_make_samples(freq, dur, volume=0.25, wave="sine"))
    return make_sound(samples)

def generate_miss_sound():
    """漏掉星星：低沉的下降嗡声"""
    samples = []
    n_samples = int(SAMPLE_RATE * 0.25)
    for i in range(n_samples):
        t = i / SAMPLE_RATE
        # 频率从300下降到150
        freq = 300 - 150 * (i / n_samples)
        val = math.sin(2 * math.pi * freq * t)
        # 淡出
        envelope = 1.0 - (i / n_samples) ** 0.5
        val *= envelope * 0.2
        samples.append(int(val * 32767))
    return make_sound(samples)

def generate_gameover_sound():
    """游戏结束：下行旋律"""
    samples = []
    notes = [(523, 0.2), (466, 0.2), (392, 0.2), (349, 0.4)]
    for freq, dur in notes:
        samples.extend(_make_samples(freq, dur, volume=0.25, wave="triangle"))
    return make_sound(samples)

def generate_restart_sound():
    """重新开始：上行小号角"""
    samples = []
    notes = [(523, 0.1), (659, 0.1), (784, 0.1), (1047, 0.2)]
    for freq, dur in notes:
        samples.extend(_make_samples(freq, dur, volume=0.2, wave="sine"))
    return make_sound(samples)

def generate_bgm():
    """生成《小星星》完整旋律BGM (Twinkle Twinkle Little Star)"""
    # C大调音符频率
    NOTE = {
        'C4': 262, 'D4': 294, 'E4': 330, 'F4': 349, 'G4': 392,
        'A4': 440, 'B4': 494,
        'C5': 523, 'D5': 587, 'E5': 659, 'F5': 698, 'G5': 784,
        'A5': 880, 'R': 0,
    }
    # 完整《小星星》旋律: 1155665 4433221 5544332 5544332 1155665 4433221
    # 用C5作为"1"，所以 1=C5 2=D5 3=E5 4=F5 5=G5 6=A5
    melody = [
        # 一闪一闪亮晶晶 (1 1 5 5 6 6 5-)
        ('C5', 1), ('C5', 1), ('G5', 1), ('G5', 1),
        ('A5', 1), ('A5', 1), ('G5', 2),
        # 满天都是小星星 (4 4 3 3 2 2 1-)
        ('F5', 1), ('F5', 1), ('E5', 1), ('E5', 1),
        ('D5', 1), ('D5', 1), ('C5', 2),
        # 挂在天上放光明 (5 5 4 4 3 3 2-)
        ('G5', 1), ('G5', 1), ('F5', 1), ('F5', 1),
        ('E5', 1), ('E5', 1), ('D5', 2),
        # 好像许多小眼睛 (5 5 4 4 3 3 2-)
        ('G5', 1), ('G5', 1), ('F5', 1), ('F5', 1),
        ('E5', 1), ('E5', 1), ('D5', 2),
        # 一闪一闪亮晶晶 (1 1 5 5 6 6 5-)
        ('C5', 1), ('C5', 1), ('G5', 1), ('G5', 1),
        ('A5', 1), ('A5', 1), ('G5', 2),
        # 满天都是小星星 (4 4 3 3 2 2 1-)
        ('F5', 1), ('F5', 1), ('E5', 1), ('E5', 1),
        ('D5', 1), ('D5', 1), ('C5', 2),
    ]
    # 低音伴奏 - 每两拍一个和弦根音
    bass_notes = [
        # 第1-2小节: C - F
        ('C4', 2), ('C4', 2), ('F4', 2), ('C4', 2),
        # 第3-4小节: F/C - G/C
        ('F4', 2), ('C4', 2), ('G4', 2), ('C4', 2),
        # 第5-6小节: C - F
        ('C4', 2), ('F4', 2), ('C4', 2), ('G4', 2),
        # 第7-8小节: C - F
        ('C4', 2), ('F4', 2), ('C4', 2), ('G4', 2),
        # 第9-10小节: C - F (重复第1-2)
        ('C4', 2), ('C4', 2), ('F4', 2), ('C4', 2),
        # 第11-12小节: F/C - G/C
        ('F4', 2), ('C4', 2), ('G4', 2), ('C4', 2),
    ]

    beat_dur = 0.28  # 每拍时长（秒），稍慢一些更像小星星的节奏

    # 生成旋律
    melody_samples = []
    for note_name, beats in melody:
        dur = beats * beat_dur
        n = int(SAMPLE_RATE * dur)
        if note_name == 'R' or NOTE[note_name] == 0:
            melody_samples.extend([0] * n)
        else:
            melody_samples.extend(_make_samples(NOTE[note_name], dur, volume=0.13, wave="sine", fade_out=True, fade_in=0.008))

    # 生成低音伴奏
    bass_samples = []
    for note_name, beats in bass_notes:
        dur = beats * beat_dur
        n = int(SAMPLE_RATE * dur)
        if note_name == 'R' or NOTE[note_name] == 0:
            bass_samples.extend([0] * n)
        else:
            bass_samples.extend(_make_samples(NOTE[note_name], dur, volume=0.06, wave="triangle", fade_out=True, fade_in=0.008))

    # 混合旋律和伴奏
    mixed = []
    for i in range(len(melody_samples)):
        m = melody_samples[i]
        b = bass_samples[i % len(bass_samples)] if i < len(bass_samples) else 0
        val = max(-32767, min(32767, m + b))
        mixed.append(val)

    return make_sound(mixed)

# 预生成所有音效
print("正在生成音效...")
snd_catch = generate_catch_sound()
snd_miss = generate_miss_sound()
snd_gameover = generate_gameover_sound()
snd_restart = generate_restart_sound()
snd_bgm = generate_bgm()
print("音效就绪！")

# ===== 绘制星星 =====
def draw_star(surface, color, center, size, points=5):
    """画一个漂亮的星星"""
    cx, cy = center
    outer_r = size
    inner_r = size * 0.4
    angle_step = math.pi / points
    
    star_points = []
    for i in range(points * 2):
        r = outer_r if i % 2 == 0 else inner_r
        angle = -math.pi / 2 + i * angle_step
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        star_points.append((x, y))
    
    pygame.draw.polygon(surface, color, star_points)
    # 高光效果
    highlight = tuple(min(c + 60, 255) for c in color)
    inner_points = []
    for i in range(points * 2):
        r = (outer_r if i % 2 == 0 else inner_r) * 0.5
        angle = -math.pi / 2 + i * angle_step
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        inner_points.append((x, y))
    pygame.draw.polygon(surface, highlight, inner_points)

# ===== 绘制篮子 =====
def draw_basket(surface, x, y, width, height):
    """画一个可爱的篮子"""
    # 篮子身体（梯形）
    points = [
        (x - width // 2 + 10, y),
        (x + width // 2 - 10, y),
        (x + width // 2, y + height),
        (x - width // 2, y + height),
    ]
    pygame.draw.polygon(surface, (139, 90, 43), points)
    pygame.draw.polygon(surface, (101, 67, 33), points, 3)
    
    # 篮子条纹
    for i in range(3):
        stripe_y = y + 8 + i * (height // 3)
        start_offset = 10 - (i * 3)
        pygame.draw.line(surface, (101, 67, 33), 
                        (x - width // 2 + start_offset + 5, stripe_y),
                        (x + width // 2 - start_offset - 5, stripe_y), 2)
    
    # 手柄
    pygame.draw.arc(surface, (139, 90, 43), 
                   (x - 25, y - 20, 50, 30), 
                   0, math.pi, 3)

# ===== 粒子效果 =====
class Particle:
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.color = color
        self.vx = random.uniform(-3, 3)
        self.vy = random.uniform(-5, -1)
        self.life = 30
        self.size = random.randint(2, 5)
    
    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += 0.15
        self.life -= 1
        self.size = max(0, self.size - 0.1)
    
    def draw(self, surface):
        if self.life > 0 and self.size > 0:
            alpha = int(255 * self.life / 30)
            color = tuple(min(c, 255) for c in self.color)
            pygame.draw.circle(surface, color, (int(self.x), int(self.y)), int(self.size))

# ===== 星星类 =====
class Star:
    def __init__(self, speed=None):
        self.reset(speed)
    
    def reset(self, speed=None):
        self.x = random.randint(40, WIDTH - 40)
        self.y = random.randint(-100, -20)
        self.size = random.randint(15, 30)
        self.color = random.choice(COLORS)
        self.speed = speed if speed is not None else random.uniform(1.5, 3.5)
        self.wobble = random.uniform(0, math.pi * 2)
        self.wobble_speed = random.uniform(0.02, 0.06)
        self.rotation = 0
        self.rot_speed = random.uniform(-2, 2)
        self.points = random.choice([5, 6])
    
    def update(self):
        self.y += self.speed
        self.wobble += self.wobble_speed
        self.x += math.sin(self.wobble) * 1.0
        self.rotation += self.rot_speed
    
    def draw(self, surface):
        draw_star(surface, self.color, (int(self.x), int(self.y)), self.size, self.points)

# ===== 背景星星（装饰）=====
class BgStar:
    def __init__(self):
        self.x = random.randint(0, WIDTH)
        self.y = random.randint(0, HEIGHT)
        self.size = random.uniform(0.5, 2.5)
        self.twinkle = random.uniform(0, math.pi * 2)
        self.twinkle_speed = random.uniform(0.02, 0.08)
    
    def update(self):
        self.twinkle += self.twinkle_speed
    
    def draw(self, surface):
        brightness = int(150 + 105 * math.sin(self.twinkle))
        color = (brightness, brightness, min(255, brightness + 30))
        if self.size > 1.5:
            pygame.draw.circle(surface, color, (int(self.x), int(self.y)), int(self.size))
        else:
            surface.set_at((int(self.x), int(self.y)), color)

# ===== 主游戏 =====
def main():
    # 篮子属性
    basket_x = WIDTH // 2
    basket_y = CATCH_Y
    basket_width = 100
    basket_height = 40
    
    # 游戏状态
    score = 0
    missed = 0
    max_missed = 100
    game_over = False
    
    # 星星列表（由节拍系统生成，不再预生成）
    stars = []
    
    # 节拍追踪
    bgm_start_ticks = pygame.time.get_ticks()
    last_beat_int = -1
    beat_flash = 0.0  # 0~1，用于节拍脉冲视觉效果
    
    # 背景星星
    bg_stars = [BgStar() for _ in range(80)]
    
    # 粒子
    particles = []
    
    # 得分动画
    score_popups = []  # (text, x, y, timer, color)
    
    running = True
    
    # 播放BGM（循环）
    bgm_channel = pygame.mixer.Channel(0)
    sfx_channel = pygame.mixer.Channel(1)
    sfx_channel2 = pygame.mixer.Channel(2)
    bgm_channel.play(snd_bgm, loops=-1)
    bgm_channel.set_volume(0.7)

    # 锁定鼠标在窗口内，小朋友不会把鼠标移出去啦！
    pygame.event.set_grab(True)

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.event.set_grab(False)
                    running = False
                if event.key == pygame.K_r and game_over:
                    # 重新开始
                    score = 0
                    missed = 0
                    game_over = False
                    stars = []
                    particles = []
                    score_popups = []
                    # 重置节拍追踪
                    bgm_start_ticks = pygame.time.get_ticks()
                    last_beat_int = -1
                    beat_flash = 0.0
                    sfx_channel.play(snd_restart)
                    bgm_channel.play(snd_bgm, loops=-1)
                    bgm_channel.set_volume(0.7)
        
        if not game_over:
            # 篮子跟随鼠标
            mouse_x, _ = pygame.mouse.get_pos()
            # 平滑移动
            basket_x += (mouse_x - basket_x) * 0.15
            basket_x = max(basket_width // 2, min(WIDTH - basket_width // 2, basket_x))
            
            # ===== 节拍同步生成星星 =====
            elapsed_ms = pygame.time.get_ticks() - bgm_start_ticks
            current_beat = elapsed_ms / (BEAT_DUR * 1000)
            current_beat_int = int(current_beat)
            
            if current_beat_int > last_beat_int:
                last_beat_int = current_beat_int
                beat_flash = 1.0  # 触发节拍视觉脉冲
                
                # 在这一拍生成星星？
                # 随分数提高，生成概率增大（更多星星，更热闹）
                spawn_chance = min(0.80, 0.40 + score * 0.008)
                # 前6拍保证生成（开局不冷场）
                if current_beat_int <= 6 or random.random() < spawn_chance:
                    # 星星将在 travel_beats 拍后到达篮子（整数拍 → 到达必在拍上！）
                    # travel_beats = random.randint(12, 24)
                    travel_beats = random.randint(22, 24)
                    # 难度提升：分数越高，飞行时间越短（速度越快）
                    travel_beats = max(8, travel_beats - score // 12)
                    
                    spawn_y = random.randint(-100, -20)
                    distance = CATCH_Y - spawn_y
                    travel_frames = travel_beats * BEAT_DUR * FPS
                    speed = distance / travel_frames
                    
                    star = Star(speed=speed)
                    star.y = spawn_y
                    stars.append(star)
            
            # 更新星星
            for star in stars[:]:
                star.update()
                
                # 检查是否被接住
                if (star.y + star.size >= basket_y and 
                    star.y <= basket_y + basket_height and
                    abs(star.x - basket_x) < basket_width // 2 + star.size // 2):
                    score += 1
                    # 音效！
                    sfx_channel.play(snd_catch)
                    # 粒子效果！
                    for _ in range(15):
                        particles.append(Particle(star.x, star.y, star.color))
                    # 得分弹出
                    score_popups.append(("+1 ⭐", star.x, star.y, 40, star.color))
                    stars.remove(star)
                    continue
                
                # 掉出屏幕
                if star.y > HEIGHT + 20:
                    missed += 1
                    sfx_channel2.play(snd_miss)
                    stars.remove(star)
                    if missed >= max_missed:
                        game_over = True
                        bgm_channel.fadeout(500)
                        sfx_channel.play(snd_gameover)
            
            # 更新粒子
            for p in particles[:]:
                p.update()
                if p.life <= 0:
                    particles.remove(p)
            
            # 更新得分弹出
            for i, (text, x, y, timer, color) in enumerate(score_popups):
                score_popups[i] = (text, x, y - 1.5, timer - 1, color)
            score_popups = [(t, x, y, timer, c) for t, x, y, timer, c in score_popups if timer > 0]
        
        # 节拍脉冲衰减（game over 时也要衰减，否则最后一帧冻住）
        beat_flash = max(0.0, beat_flash - 0.06)
        
        # ===== 绘制 =====
        # 渐变背景（深蓝到深紫）
        for y in range(HEIGHT):
            ratio = y / HEIGHT
            r = int(10 + 15 * ratio)
            g = int(5 + 10 * ratio)
            b = int(40 + 30 * (1 - ratio))
            pygame.draw.line(screen, (r, g, b), (0, y), (WIDTH, y))
        
        # 背景星星
        for bs in bg_stars:
            bs.update()
            bs.draw(screen)
        
        # 游戏中的星星
        for star in stars:
            star.draw(screen)
        
        # 粒子
        for p in particles:
            p.draw(screen)
        
        # 节拍脉冲光效（接收区闪光线）
        if beat_flash > 0:
            glow_surf = pygame.Surface((WIDTH, 16), pygame.SRCALPHA)
            alpha = int(beat_flash * 130)
            glow_surf.fill((255, 255, 200, alpha))
            screen.blit(glow_surf, (0, basket_y - 8))
        
        # 篮子（节拍弹跳）
        basket_draw_y = basket_y - int(beat_flash * 5)
        draw_basket(screen, int(basket_x), basket_draw_y, basket_width, basket_height)
        
        # 得分弹出
        for text, x, y, timer, color in score_popups:
            alpha = min(255, timer * 8)
            popup_surface = font_small.render(text, True, color)
            screen.blit(popup_surface, (int(x) - popup_surface.get_width() // 2, int(y)))
        
        # 分数 UI
        score_text = font_med.render(f"⭐ {score}", True, YELLOW)
        screen.blit(score_text, (20, 15))
        
        # 剩余生命（用心形表示）
        lives_left = max_missed - missed
        lives_text = font_small.render(f"❤ x {lives_left}", True, (255, 100, 100))
        screen.blit(lives_text, (WIDTH - 130, 20))
        
        # Game Over
        if game_over:
            # 半透明遮罩
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 150))
            screen.blit(overlay, (0, 0))
            
            go_text = font_big.render("游戏结束！", True, YELLOW)
            screen.blit(go_text, (WIDTH // 2 - go_text.get_width() // 2, HEIGHT // 2 - 80))
            
            final_text = font_med.render(f"你接住了 {score} 颗星星！", True, WHITE)
            screen.blit(final_text, (WIDTH // 2 - final_text.get_width() // 2, HEIGHT // 2 - 10))
            
            if score >= 30:
                msg = "🏆 超级厉害！你是接星星冠军！"
                msg_color = YELLOW
            elif score >= 15:
                msg = "👍 太棒了！继续加油！"
                msg_color = (85, 239, 196)
            else:
                msg = "😊 不错哦！再来一次吧！"
                msg_color = (116, 185, 255)
            
            msg_text = font_small.render(msg, True, msg_color)
            screen.blit(msg_text, (WIDTH // 2 - msg_text.get_width() // 2, HEIGHT // 2 + 50))
            
            retry_text = font_small.render("按 R 重新开始 | 按 ESC 退出", True, (200, 200, 200))
            screen.blit(retry_text, (WIDTH // 2 - retry_text.get_width() // 2, HEIGHT // 2 + 110))
        
        pygame.display.flip()
        clock.tick(60)
    
    pygame.event.set_grab(False)
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()

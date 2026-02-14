"""
🐢 超酷海龟画图表演！
给小朋友看的彩色几何图形大秀~
"""
import turtle
import random
import colorsys

def setup_screen():
    screen = turtle.Screen()
    screen.setup(900, 700)
    screen.bgcolor("black")
    screen.title("🐢 海龟画图魔法秀！")
    screen.tracer(0)  # 手动刷新，更流畅
    return screen

def create_turtle(speed_val=0):
    t = turtle.Turtle()
    t.speed(0)
    t.hideturtle()
    t.pensize(2)
    return t

# ===== 第1幕：彩虹螺旋 =====
def rainbow_spiral(t, screen):
    t.clear()
    t.penup()
    t.goto(0, 0)
    t.pendown()
    
    for i in range(360):
        # 用 HSV 色彩空间生成彩虹色
        color = colorsys.hsv_to_rgb(i / 360, 1.0, 1.0)
        t.pencolor(color)
        t.pensize(2)
        t.forward(i * 0.5)
        t.left(59)  # 不是60度，所以会形成螺旋
        
        if i % 5 == 0:
            screen.update()
            import time; time.sleep(0.01)
    
    screen.update()

# ===== 第2幕：万花筒花朵 =====
def kaleidoscope_flower(t, screen):
    t.clear()
    t.penup()
    t.goto(0, 0)
    t.pendown()
    
    colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", 
              "#FFEAA7", "#DDA0DD", "#FF69B4", "#00CED1",
              "#FFD700", "#7B68EE", "#FF4500", "#32CD32"]
    
    for i in range(36):
        t.pencolor(colors[i % len(colors)])
        t.pensize(2)
        # 画一个花瓣
        for _ in range(2):
            t.circle(80, 60)
            t.circle(20, 60)
            t.circle(80, 60)
            t.circle(20, 60)
        t.left(10)
        
        if i % 2 == 0:
            screen.update()
            import time; time.sleep(0.05)
    
    screen.update()

# ===== 第3幕：彩色星星阵 =====
def star_field(t, screen):
    t.clear()
    
    def draw_star(t, x, y, size, color, points=5):
        t.penup()
        t.goto(x, y)
        t.pendown()
        t.pencolor(color)
        t.fillcolor(color)
        t.begin_fill()
        angle = 180 - 180 / points
        for _ in range(points):
            t.forward(size)
            t.right(angle)
        t.end_fill()
    
    star_colors = ["#FFD700", "#FF69B4", "#00BFFF", "#7CFC00", 
                   "#FF6347", "#EE82EE", "#FFA500", "#00FA9A",
                   "#FF1493", "#1E90FF", "#FFFF00", "#FF4500"]
    
    stars = []
    for _ in range(25):
        x = random.randint(-380, 380)
        y = random.randint(-280, 280)
        size = random.randint(15, 60)
        color = random.choice(star_colors)
        points = random.choice([5, 6, 8])
        stars.append((x, y, size, color, points))
    
    for i, (x, y, size, color, points) in enumerate(stars):
        draw_star(t, x, y, size, color, points)
        if i % 3 == 0:
            screen.update()
            import time; time.sleep(0.08)
    
    screen.update()

# ===== 第4幕：同心圆彩虹 =====
def rainbow_circles(t, screen):
    t.clear()
    
    for i in range(50, 0, -1):
        t.penup()
        t.goto(0, -i * 5)
        t.pendown()
        
        color = colorsys.hsv_to_rgb(i / 50, 0.8, 1.0)
        t.pencolor(color)
        t.fillcolor(color)
        t.begin_fill()
        t.circle(i * 5)
        t.end_fill()
        
        if i % 3 == 0:
            screen.update()
            import time; time.sleep(0.05)
    
    screen.update()

# ===== 第5幕：旋转正方形隧道 =====
def spinning_squares(t, screen):
    t.clear()
    t.penup()
    t.goto(0, 0)
    t.pendown()
    
    for i in range(80):
        color = colorsys.hsv_to_rgb(i / 80, 1.0, 1.0)
        t.pencolor(color)
        t.pensize(2)
        
        # 画正方形
        for _ in range(4):
            t.forward(i * 3)
            t.right(90)
        t.right(5)  # 每次旋转一点
        
        if i % 3 == 0:
            screen.update()
            import time; time.sleep(0.03)
    
    screen.update()

# ===== 第6幕：烟花！=====
def fireworks(t, screen):
    t.clear()
    
    firework_colors = [
        ["#FF0000", "#FF4500", "#FF6347", "#FF7F50", "#FFA07A"],
        ["#00FF00", "#32CD32", "#7CFC00", "#ADFF2F", "#98FB98"],
        ["#0000FF", "#1E90FF", "#00BFFF", "#87CEEB", "#ADD8E6"],
        ["#FFD700", "#FFA500", "#FFFF00", "#FFFACD", "#FAFAD2"],
        ["#FF00FF", "#FF69B4", "#DDA0DD", "#EE82EE", "#DA70D6"],
    ]
    
    positions = [(-200, 100), (200, 50), (0, 150), (-150, -50), (180, -80)]
    
    for pos_idx, (cx, cy) in enumerate(positions):
        colors = firework_colors[pos_idx]
        for ring in range(5):
            for angle in range(0, 360, 10):
                t.penup()
                t.goto(cx, cy)
                t.setheading(angle)
                t.pendown()
                t.pencolor(colors[ring])
                t.pensize(3 - ring * 0.4 if ring < 4 else 1)
                length = 30 + ring * 25
                t.forward(length)
                # 在末端画个小圆点
                t.dot(4, colors[ring])
        
        screen.update()
        import time; time.sleep(0.3)
    
    screen.update()

# ===== 显示标题文字 =====
def show_title(t, screen, text, y=0):
    t.clear()
    t.penup()
    t.goto(0, y)
    t.pencolor("white")
    t.write(text, align="center", font=("Arial", 28, "bold"))
    screen.update()
    import time; time.sleep(1.5)
    t.clear()

# ===== 主程序 =====
def main():
    screen = setup_screen()
    artist = create_turtle()
    title_turtle = create_turtle()
    
    import time
    
    shows = [
        ("🌈 彩虹螺旋！", rainbow_spiral),
        ("🌸 万花筒花朵！", kaleidoscope_flower),
        ("⭐ 满天星星！", star_field),
        ("🎯 彩虹同心圆！", rainbow_circles),
        ("🌀 旋转方块隧道！", spinning_squares),
        ("🎆 烟花！", fireworks),
    ]
    
    # 开场
    title_turtle.penup()
    title_turtle.goto(0, 50)
    title_turtle.pencolor("#FFD700")
    title_turtle.write("🐢 海龟画图魔法秀 🐢", align="center", font=("Arial", 36, "bold"))
    title_turtle.goto(0, -20)
    title_turtle.pencolor("#87CEEB")
    title_turtle.write("准备好了吗？开始啦！", align="center", font=("Arial", 20, "bold"))
    screen.update()
    time.sleep(2)
    title_turtle.clear()
    
    for title, show_func in shows:
        show_title(title_turtle, screen, title, y=300)
        show_func(artist, screen)
        time.sleep(2)
    
    # 结尾
    artist.clear()
    title_turtle.penup()
    title_turtle.goto(0, 50)
    title_turtle.pencolor("#FF69B4")
    title_turtle.write("✨ 表演结束！✨", align="center", font=("Arial", 36, "bold"))
    title_turtle.goto(0, -20)
    title_turtle.pencolor("#87CEEB")
    title_turtle.write("点击窗口关闭~", align="center", font=("Arial", 18, "normal"))
    screen.update()
    
    screen.exitonclick()

if __name__ == "__main__":
    main()

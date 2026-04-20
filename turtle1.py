import turtle as t
import colorsys

# t.speed(0)
t.bgcolor('black')
t.pensize(2)

a = 80
for i in range(500):
    # input()
    print(1+i)

    # 色相从0~1循环，产生彩虹渐变
    color = colorsys.hsv_to_rgb(i / 120, 1, 1)
    t.pencolor(color)

    t.forward(a)
    t.right(180-37)
    
    a += 1

t.done()
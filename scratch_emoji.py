from PIL import Image, ImageDraw, ImageFont
import sys

def test_emoji():
    img = Image.new("RGB", (400, 200), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("seguiemj.ttf", 60)
        draw.text((50, 50), "🍎 + 🍌 = 10", font=font, fill=(0, 0, 0))
        img.save("emoji_test.png")
        print("Success! Saved emoji_test.png")
    except Exception as e:
        print("Error:", e)

test_emoji()

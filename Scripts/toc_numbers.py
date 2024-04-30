from PIL import Image, ImageDraw, ImageFont

# TEMPORARY
numbers = [5, 15, 69, 121, 165]


padded_numbers = [str(num).zfill(3) for num in numbers]

image = Image.open("toc.jpg")

draw = ImageDraw.Draw(image)
font = ImageFont.truetype("HomepageBaukasten-Book.ttf", size=42)

text_color = (255, 0, 0)  # Normally (0, 0, 0)

offshift_x = 1301
offshift_y = 246


position_x = 0
position_y = 0

for number in padded_numbers:
    text = "P . " + number

    text_position = (
        59.52 + offshift_x * position_x,
        521.82 + offshift_y * position_y,
    )

    position_y += 1
    if position_y == 3:
        position_y = -1
        position_x = 1

    draw.text(text_position, text, fill=text_color, font=font)

image.save("output_image.jpg")

image.close()

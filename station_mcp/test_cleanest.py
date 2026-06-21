"""Test _cleanest_frame: among a burst of near-identical frames + one glitch, reject the glitch."""
import io
from PIL import Image, ImageDraw
from backend import _cleanest_frame


def jpeg(img):
    b = io.BytesIO()
    img.save(b, format="JPEG", quality=85)
    return b.getvalue()


# 4 near-identical "clean" frames (a box on a table), tiny per-frame variation
clean = Image.new("RGB", (160, 120), (120, 100, 80))
ImageDraw.Draw(clean).rectangle([60, 50, 90, 80], fill=(20, 20, 40))


def noisy(seed):
    im = clean.copy()
    ImageDraw.Draw(im).point([(seed % 160, (seed * 7) % 120)], fill=(255, 255, 255))
    return jpeg(im)


# 1 badly "glitched" frame (very different)
glitch = Image.new("RGB", (160, 120), (0, 255, 0))
ImageDraw.Draw(glitch).rectangle([0, 0, 160, 60], fill=(255, 0, 255))
glitch_jpg = jpeg(glitch)

clean_frames = [noisy(1), noisy(2), noisy(3), noisy(4)]
frames = clean_frames + [glitch_jpg]

chosen = _cleanest_frame(frames)
assert chosen != glitch_jpg, "should NOT pick the glitch frame"
assert chosen in clean_frames, "should pick one of the clean frames"

# with <3 frames it falls back to the latest
assert _cleanest_frame([glitch_jpg]) == glitch_jpg

print("cleanest-frame test passed: clean consensus chosen, glitch rejected")

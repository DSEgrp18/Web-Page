"""Build Swara's brand assets from the logo, and the web copies of the photographs.

    python docs/brand/build-assets.py                    # the logo, the lockups, the icons
    python docs/brand/build-assets.py --photos DIR       # and the photographs, from DIR

Needs Pillow, NumPy and OpenCV (opencv-python). Writes into apps/web/public.

The logo (logo-source.png) is drawn in two flat colours on white. Each pixel
is un-blended from the white ("colour to alpha") against whichever of the two
colours it belongs to, so the cut-out has clean, anti-aliased edges on any
background. The dark-theme copy lifts the blue, which is too dark to see on
the night palette, and keeps the orange.

The photographs are not in the repository at full size (they are several
megabytes each); README.md lists where each came from. Put the originals in a
folder and pass it with --photos to rebuild the web copies.
"""

import argparse
import os

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.normpath(os.path.join(HERE, "..", "..", "apps", "web", "public"))
BRAND, IMAGES = os.path.join(PUBLIC, "brand"), os.path.join(PUBLIC, "images")

BLUE = np.array([47, 83, 170], float)  # #2f53aa, sampled from the logo
ORANGE = np.array([253, 149, 32], float)  # #fd9520
BLUE_ON_DARK = np.array([168, 189, 255], float)  # the blue, lifted for a dark page

# The mark (roof and book) sits above the word, in this box of the source.
MARK_BOX = (1000, 0, 1720, 895)  # x0, y0, x1, y1

# name: (source file, crop as fractions x0, y0, x1, y1, output widths)
PHOTOS = {
    "reading-desk": ("pexels-yaroslav-shuraev-9489804.jpg", (0, 0, 1, 1), (1600, 800)),
    "study-notebook": ("pexels-annpoan-5797900.jpg", (0, 0.08, 1, 1), (900, 540)),
    "student-laptop": ("pexels-katerina-holmes-5905969.jpg", (0.05, 0, 1, 1), (1400, 700)),
    "student-tablet": ("pexels-kseniachernaya-7694941.jpg", (0, 0.06, 1, 1), (1000, 560)),
    "colour-book": ("pexels-polina-zimmerman-3747300.jpg", (0, 0.1, 1, 1), (900, 540)),
    "classroom": ("pexels-yankrukov-8617767.jpg", (0, 0, 1, 1), (1600, 800)),
}


def cut_out(rgb):
    """Alpha and colour membership of every pixel of a two-colour logo on white."""
    h, w, _ = rgb.shape

    def alpha_for(colour):
        depth = 255 - colour
        alpha = np.zeros((h, w))
        for channel in range(3):
            if depth[channel] > 20:  # a channel the colour barely darkens says nothing
                alpha = np.maximum(alpha, (255 - rgb[:, :, channel]) / depth[channel])
        return np.clip(alpha, 0, 1)

    # Orange darkens the blue channel most; blue darkens the red channel most.
    is_orange = (255 - rgb[:, :, 2]) > (255 - rgb[:, :, 0]) * 1.2
    alpha = np.where(is_orange, alpha_for(ORANGE), alpha_for(BLUE))
    alpha[alpha < 0.03] = 0
    return alpha, is_orange


def logo(alpha, is_orange, blue):
    h, w = alpha.shape
    out = np.zeros((h, w, 4), np.uint8)
    out[..., :3] = np.where(is_orange[..., None], ORANGE, blue).astype(np.uint8)
    out[..., 3] = (alpha * 255).round().astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def trim(image):
    return image.crop(image.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox())


def split(image):
    """The mark, and the word without it."""
    pixels = np.asarray(image)
    region = np.zeros(pixels.shape[:2], bool)
    x0, y0, x1, y1 = MARK_BOX
    region[y0:y1, x0:x1] = True
    mark, word = pixels.copy(), pixels.copy()
    mark[~region] = 0
    word[region] = 0
    return trim(Image.fromarray(mark, "RGBA")), trim(Image.fromarray(word, "RGBA"))


def lockup(mark, word, height=140, gap=26):
    """The mark beside the word: the masthead's shape."""
    word_h = int(height * 0.86)
    word = word.resize((round(word.width * word_h / word.height), word_h), Image.LANCZOS)
    mark = mark.resize((round(mark.width * height / mark.height), height), Image.LANCZOS)
    out = Image.new("RGBA", (mark.width + gap + word.width, height), (0, 0, 0, 0))
    out.alpha_composite(mark, (0, 0))
    out.alpha_composite(word, (mark.width + gap, height - word_h))
    return out


def square(mark, size, background=None, scale=0.78):
    mode, fill = ("RGBA", (0, 0, 0, 0)) if background is None else ("RGB", background)
    out = Image.new(mode, (size, size), fill)
    m = mark.copy()
    m.thumbnail((int(size * scale), int(size * scale)), Image.LANCZOS)
    at = ((size - m.width) // 2, (size - m.height) // 2)
    if background is None:
        out.alpha_composite(m, at)
    else:
        out.paste(m, at, m)
    return out


def traced_svg(mark):
    """The mark as vector paths, for the SVG icon: one path per colour."""
    pixels = np.asarray(square(mark, 512, scale=0.84))
    paths = []
    for colour, fill in ((BLUE, "#2f53aa"), (ORANGE, "#fd9520")):
        near = np.linalg.norm(pixels[..., :3].astype(float) - colour, axis=2) < 60
        mask = (((pixels[..., 3] > 127) & near) * 255).astype(np.uint8)
        contours, _ = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
        d = []
        for contour in contours:
            if cv2.contourArea(contour) < 6:
                continue
            points = cv2.approxPolyDP(contour, 0.6, True).reshape(-1, 2)
            d.append("M" + " L".join(f"{x} {y}" for x, y in points) + "Z")
        paths.append(f'<path fill="{fill}" fill-rule="evenodd" d="{" ".join(d)}"/>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">' + "".join(paths) + "</svg>\n"


def save_webp(image, path, quality=90):
    image.save(path, "WEBP", quality=quality, method=6)
    print(f"{os.path.relpath(path, PUBLIC)}  {image.size[0]}x{image.size[1]}  {os.path.getsize(path) // 1024} KiB")


def build_logo():
    rgb = np.asarray(Image.open(os.path.join(HERE, "logo-source.png")).convert("RGB")).astype(float)
    alpha, is_orange = cut_out(rgb)
    for suffix, blue in (("", BLUE), ("-dark", BLUE_ON_DARK)):
        mark, word = split(logo(alpha, is_orange, blue))
        save_webp(lockup(mark, word), os.path.join(BRAND, f"swara-lockup{suffix}.webp"))
        if not suffix:
            light_mark = mark

    for size in (16, 32):
        square(light_mark, size, scale=0.98).save(os.path.join(BRAND, f"icon-{size}.png"))
    for size in (192, 512):
        square(light_mark, size, (255, 255, 255), 0.62).save(os.path.join(BRAND, f"icon-{size}.png"))
    # iOS: square and opaque (RGB), since it fills transparency with black.
    square(light_mark, 180, (255, 255, 255), 0.66).save(os.path.join(BRAND, "apple-icon.png"))
    # LF on every platform, so the file is the same wherever it is rebuilt.
    with open(os.path.join(BRAND, "icon.svg"), "w", encoding="utf-8", newline="\n") as f:
        f.write(traced_svg(light_mark))
    print("icons: icon.svg, icon-16/32/192/512.png, apple-icon.png")


def build_photos(folder):
    os.makedirs(IMAGES, exist_ok=True)
    for name, (source, (fx0, fy0, fx1, fy1), widths) in PHOTOS.items():
        image = Image.open(os.path.join(folder, source)).convert("RGB")
        w, h = image.size
        image = image.crop((int(fx0 * w), int(fy0 * h), int(fx1 * w), int(fy1 * h)))
        for width in widths:
            copy = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
            save_webp(copy, os.path.join(IMAGES, f"{name}-{width}.webp"), quality=72)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--photos", help="folder holding the original photographs")
    args = parser.parse_args()
    build_logo()
    if args.photos:
        build_photos(args.photos)

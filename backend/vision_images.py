"""Conservative source-image preparation, without OCR or reference labels."""
from PIL import Image, ImageOps


def crop_white_margins(image):
    """Remove only outer pure-white pixels, retaining every non-white pixel.

    Returns the original object when unchanged, otherwise a new RGB image.
    No near-white threshold is used: even a 254-valued mark is retained.
    Padding keeps content away from the model image boundary. Photographs with
    non-white edges and white-only pages remain unchanged.
    """
    if image.mode != "RGB":
        raise ValueError("Margin preparation requires an RGB image.")
    with ImageOps.invert(image) as inverted:
        bounds = inverted.getbbox()
    if bounds is None:
        return image
    padding = max(16, round(max(image.size) * 0.015))
    left, top, right, bottom = bounds
    crop = (max(0, left - padding), max(0, top - padding),
            min(image.width, right + padding), min(image.height, bottom + padding))
    return image if crop == (0, 0, image.width, image.height) else image.crop(crop)


def tile_tall_page(image, max_pixels, edge=1280):
    """Keep narrow receipt text readable without removing blank or faint regions.

    Consecutive upper/lower halves are placed side by side, without overlap.
    Every source pixel is copied exactly; the caller tells the model the order.
    Returns the original image when no tiling is needed or would exceed limits.
    """
    if image.height <= edge or image.height <= image.width * 2.5:
        return image
    middle = (image.height + 1) // 2
    gutter = min(16, max(1, image.width // 40))
    width = image.width * 2 + gutter
    if width * middle > max_pixels:
        return image
    # Prefer a nearby low-ink gap to avoid splitting a printed row. This only
    # chooses the seam: even faint pixels excluded from the score are copied.
    radius = min(80, image.height // 20)
    candidates = []
    for row in range(max(1, middle - radius), min(image.height, middle + radius + 1)):
        with image.crop((0, row, image.width, row + 1)) as line:
            with line.convert("L") as gray:
                ink = sum(gray.histogram()[:240])
        candidates.append((ink, abs(row - middle), row))
    seam = min(candidates)[2]
    height = max(seam, image.height - seam)
    if width * height > max_pixels:
        return image
    tiled = Image.new("RGB", (width, height), "white")
    with image.crop((0, 0, image.width, seam)) as top:
        tiled.paste(top, (0, 0))
    with image.crop((0, seam, image.width, image.height)) as bottom:
        tiled.paste(bottom, (image.width + gutter, 0))
    return tiled

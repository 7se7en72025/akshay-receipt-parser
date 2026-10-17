"""Conservative source-image preparation, without OCR or reference labels."""
from PIL import ImageOps


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

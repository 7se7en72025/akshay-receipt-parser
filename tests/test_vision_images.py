import unittest
from collections import Counter

from PIL import Image, ImageDraw

from backend.vision_images import crop_white_margins


class ImageMarginTests(unittest.TestCase):
    def test_preserves_every_non_white_pixel_including_faint_colored_marks(self):
        with Image.new("RGB", (400, 600), "white") as image:
            ImageDraw.Draw(image).rectangle((100, 100, 300, 350), fill="black")
            image.putpixel((40, 450), (254, 254, 254))
            image.putpixel((50, 460), (255, 255, 254))
            before = Counter(pixel for pixel in image.get_flattened_data() if pixel != (255, 255, 255))
            cropped = crop_white_margins(image)
            try:
                self.assertLess(cropped.width, image.width)
                self.assertLess(cropped.height, image.height)
                after = Counter(pixel for pixel in cropped.get_flattened_data() if pixel != (255, 255, 255))
                self.assertEqual(before, after)
                self.assertEqual(image.size, (400, 600))
            finally:
                if cropped is not image:
                    cropped.close()

    def test_blank_and_non_white_edges_remain_unchanged(self):
        for color in ("white", "black", (250, 250, 250)):
            with self.subTest(color=color), Image.new("RGB", (200, 300), color) as image:
                self.assertIs(crop_white_margins(image), image)
                self.assertEqual(image.getpixel((0, 0)), Image.new("RGB", (1, 1), color).getpixel((0, 0)))

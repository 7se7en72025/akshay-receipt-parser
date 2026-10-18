import unittest
from collections import Counter

from PIL import Image, ImageDraw

from backend.vision_images import crop_white_margins, tile_tall_page


class ImageMarginTests(unittest.TestCase):
    def test_tall_page_tiles_copy_all_source_pixels_in_order(self):
        with Image.new("RGB", (40, 201), (250, 250, 250)) as image:
            for row in range(image.height):
                image.putpixel((5, row), (row, 1, 2))
            tiled = tile_tall_page(image, 10000, edge=128)
            try:
                self.assertEqual(tiled.size, (81, 101))
                for row in range(image.height):
                    x, y = (5, row) if row < 101 else (46, row - 101)
                    self.assertEqual(tiled.getpixel((x, y)), image.getpixel((5, row)))
            finally:
                if tiled is not image:
                    tiled.close()

    def test_tiling_never_exceeds_pixel_budget_or_changes_short_pages(self):
        with Image.new("RGB", (40, 201), "white") as tall:
            self.assertIs(tile_tall_page(tall, 8040, edge=128), tall)
        with Image.new("RGB", (40, 100), "white") as short:
            self.assertIs(tile_tall_page(short, 10000, edge=128), short)

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
                self.assertIsNotNone(image.load())

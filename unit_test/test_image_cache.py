"""What the image cache promises, checked without `assets/` and without a network.

    python -m unittest unit_test.test_image_cache

Three things are pinned here, because all three are invisible from the game -
the picture looks the same either way, and only the memory graph, the CPU time
and the response header say otherwise:

* the memory cache holds the images served most recently and no more than
  `image_cache_mb` of them;
* an image that is already portrait is served as it is stored, with no decode
  and no re-encode, and a landscape one is rotated once and the result kept;
* what goes out on the wire is called what it is.

Everything here builds its own images in a temp folder, so it runs on a plain
checkout in well under a second.
"""

import io
import os
import tempfile
import unittest

from PIL import Image

from engine.file.cache import (Cache, CachedImage, ImageMemory,
                               CACHE_FOLDER, IMAGE_CACHE_MB, IMAGE_FOLDERS)
from engine.lib.image_creator import ImageCreator, ImageLib

def setUpModule() -> None:
    # The stand-in drawn when nothing else answers needs its font picked.
    ImageCreator.Initialize()

def MakeImage(width: int, height: int, format: str, color: str="red") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), color).save(out, format=format)
    return out.getvalue()

KB = b'x' * 1024

class TestImageMemory(unittest.TestCase):
    """The budget, and what falls out of it first."""

    def setUp(self) -> None:
        self.budget_was = IMAGE_CACHE_MB.value
        IMAGE_CACHE_MB.SetValueInternal(1)
        self.memory = ImageMemory()

    def tearDown(self) -> None:
        IMAGE_CACHE_MB.SetValueInternal(self.budget_was)

    def Fill(self, count: int) -> None:
        for index in range(count):
            self.memory.Put(f"card{index}", CachedImage(KB))

    def test_stays_inside_the_budget(self) -> None:
        self.Fill(4096)
        count, size = self.memory.Stats()
        self.assertLessEqual(size, 1024 * 1024)
        self.assertEqual(count, 1024)

    def test_the_oldest_goes_first(self) -> None:
        self.Fill(1024)
        self.memory.Put("new", CachedImage(KB))
        self.assertIsNone(self.memory.Get("card0"))
        self.assertIsNotNone(self.memory.Get("new"))

    def test_serving_an_image_keeps_it(self) -> None:
        self.Fill(1024)
        self.memory.Get("card0")            # the oldest, until now
        self.memory.Put("new", CachedImage(KB))
        self.assertIsNotNone(self.memory.Get("card0"))
        self.assertIsNone(self.memory.Get("card1"))

    def test_an_oversized_image_is_still_served(self) -> None:
        # It was just asked for, so it goes in; it is simply first out next time.
        self.memory.Put("big", CachedImage(b'y' * 3 * 1024 * 1024))
        self.assertIsNotNone(self.memory.Get("big"))
        self.memory.Put("small", CachedImage(KB))
        self.assertIsNone(self.memory.Get("big"))

    def test_zero_means_unlimited(self) -> None:
        IMAGE_CACHE_MB.SetValueInternal(0)
        self.Fill(2000)
        count, size = self.memory.Stats()
        self.assertEqual(count, 2000)
        self.assertGreater(size, 1024 * 1024)

class TestRotation(unittest.TestCase):
    """Which images are opened at all."""

    def test_a_portrait_image_is_handed_back_untouched(self) -> None:
        data = MakeImage(200, 300, "WEBP")
        out, rotated = ImageLib.RotateIfNeeded(data)
        self.assertFalse(rotated)
        self.assertIs(out, data)

    def test_a_landscape_image_is_stood_up(self) -> None:
        data = MakeImage(300, 200, "PNG")
        out, rotated = ImageLib.RotateIfNeeded(data)
        self.assertTrue(rotated)
        self.assertEqual(Image.open(io.BytesIO(out)).size, (200, 300))
        self.assertEqual(ImageLib.ContentTypeOf(out), 'image/jpeg')

    def test_a_quarter_turn_in_the_exif_counts(self) -> None:
        # Stored landscape but tagged "turn me", so a browser shows it portrait
        # and there is nothing for us to do.
        image = Image.new("RGB", (300, 200), "red")
        exif = image.getexif()
        exif[ImageLib.EXIF_ORIENTATION_TAG] = 6
        out = io.BytesIO()
        image.save(out, format="JPEG", exif=exif)
        data = out.getvalue()
        self.assertEqual(ImageLib.ImageShape(data), (200, 300))
        self.assertFalse(ImageLib.RotateIfNeeded(data)[1])

    def test_something_that_is_not_an_image_is_left_alone(self) -> None:
        self.assertIsNone(ImageLib.ImageShape(b'not a picture'))
        self.assertEqual(ImageLib.RotateIfNeeded(b'not a picture'), (b'not a picture', False))

class TestContentType(unittest.TestCase):
    """What the bytes are called on the wire."""

    def test_formats_are_read_from_the_bytes(self) -> None:
        self.assertEqual(ImageLib.ContentTypeOf(MakeImage(10, 20, "JPEG")), 'image/jpeg')
        self.assertEqual(ImageLib.ContentTypeOf(MakeImage(10, 20, "PNG")), 'image/png')
        self.assertEqual(ImageLib.ContentTypeOf(MakeImage(10, 20, "WEBP")), 'image/webp')
        self.assertEqual(ImageLib.ContentTypeOf(MakeImage(10, 20, "GIF")), 'image/gif')

    def test_anything_unrecognised_is_a_jpeg(self) -> None:
        # Everything the cache makes itself - a rotation, a stand-in - is one.
        self.assertEqual(ImageLib.ContentTypeOf(b'\0\0\0\0'), 'image/jpeg')

class TestReadImageFile(unittest.TestCase):
    """One image off the disk, and the rotation kept beside it."""

    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.image_folders_were = IMAGE_FOLDERS.value
        self.cache_folder_was = CACHE_FOLDER.value
        IMAGE_FOLDERS.SetValueInternal([self.folder.name])
        CACHE_FOLDER.SetValueInternal(os.path.join(self.folder.name, "cache"))
        Cache.memory.Clear()

    def tearDown(self) -> None:
        IMAGE_FOLDERS.SetValueInternal(self.image_folders_were)
        CACHE_FOLDER.SetValueInternal(self.cache_folder_was)
        Cache.memory.Clear()
        Cache.placeholders.clear()
        self.folder.cleanup()

    def Write(self, name: str, data: bytes) -> str:
        path = os.path.join(self.folder.name, name)
        with open(path, "wb") as file:
            file.write(data)
        return path

    def test_a_portrait_webp_stays_a_webp(self) -> None:
        data = MakeImage(179, 300, "WEBP")
        self.Write("tile.webp", data)
        entry = Cache.LoadImageData("tile")
        self.assertEqual(entry.content_type, 'image/webp')
        self.assertEqual(entry.data, data)

    def test_a_rotation_is_saved_and_reused(self) -> None:
        path = self.Write("token.webp", MakeImage(300, 179, "WEBP"))
        first = Cache.LoadImageData("token")
        self.assertEqual(first.content_type, 'image/jpeg')
        self.assertTrue(os.path.exists(Cache.RotatedPath("token")))

        # Replace the source with a different picture, but leave it looking older
        # than the rotation: a second read must come off the saved file, which is
        # the whole point - no decode, and the same bytes as before.
        source_time = os.path.getmtime(path)
        self.Write("token.webp", MakeImage(300, 179, "WEBP", color="blue"))
        os.utime(path, (source_time, source_time))
        Cache.memory.Clear()
        self.assertEqual(Cache.LoadImageData("token").data, first.data)

    def test_a_rotation_older_than_its_source_is_thrown_away(self) -> None:
        path = self.Write("token.webp", MakeImage(300, 179, "WEBP"))
        first = Cache.LoadImageData("token")

        # The art was replaced since - a re-download, or a player dropping a file
        # in by hand - so the saved rotation is of a picture that is not there.
        self.Write("token.webp", MakeImage(300, 179, "WEBP", color="blue"))
        os.utime(path, None)
        Cache.memory.Clear()
        self.assertNotEqual(Cache.LoadImageData("token").data, first.data)

    def test_an_empty_file_is_not_an_image(self) -> None:
        self.Write("blank.jpg", b'')
        # Nothing to load and no server configured in a test, so this is a
        # generated stand-in rather than a zero-byte response.
        self.assertTrue(len(Cache.LoadImageData("blank").data) > 0)
        self.assertTrue(Cache.IsPlaceholder("blank"))

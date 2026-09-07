from core import *
import asyncio
import threading
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
import requests
from engine.lib import ImageCreator, ImageLib
from engine.log import Log
from engine.file import FileManager
from engine.config import ConfigVariables

CATEGORY_NAME = "CACHE"

IMAGE_FOLDERS   = ConfigVariables.Folders('image_folders', ["./assets/pics/"])
TEXTURE_FOLDER  = ConfigVariables.Folder('texture_folder', "./assets/textures/")
CACHE_FOLDER    = ConfigVariables.Folder('cache_folder', "./assets/cache/")
IMAGE_SERVERS   = ConfigVariables.ListStr('image_servers', [])
IMAGE_WORKERS   = ConfigVariables.Int('image_workers', 8)
IMAGE_CACHE_MB  = ConfigVariables.Int('image_cache_mb', 64)
# `save_empty_image` is gone: generated stand-ins are no longer written to disk.
BREAK_WHEN_LOAD_ONLINE_IMAGE = ConfigVariables.Bool('break_when_load_online_image', False)

@dataclass(frozen=True)
class CachedImage:
    """One image as it will go out on the wire."""
    data: bytes
    content_type: str = 'image/jpeg'

    def __len__(self) -> int:
        return len(self.data)

class ImageMemory:
    """The images served most recently, under a budget in bytes.

    This used to be a plain dict, which meant every JPEG the server had ever
    handed out stayed resident: one pass over the New Game screen is 154 MB of
    card art, and nothing ever dropped any of it. The cache is here to save the
    second serve of the same picture, and that is what a recency ordering keeps -
    what a session is looking at now is a hand, a board and a set of tiles, not
    the whole collection. Anything evicted is re-read from `assets/`, which is
    cheap now that an image already portrait is neither decoded nor re-encoded.

    Sized in bytes rather than in entries because entries are not alike: a card
    is ~370 KB and a set tile is ~15 KB. `image_cache_mb` sets the budget and
    defaults to 64, which is ~175 cards - several times what a game has on the
    table; 0 or less means the old unlimited behaviour."""

    def __init__(self) -> None:
        self.entries: 'OrderedDict[str, CachedImage]' = OrderedDict()
        self.size: int = 0
        # Loads finish on pool threads while the event loop reads hits.
        self.lock = threading.Lock()

    @property
    def budget(self) -> int:
        """Read from config on each use, so a test can change it mid-run."""
        return IMAGE_CACHE_MB.value * 1024 * 1024

    def Get(self, card_id: str) -> 'CachedImage|None':
        with self.lock:
            entry = self.entries.get(card_id)
            if entry is not None:
                self.entries.move_to_end(card_id)
            return entry

    def Put(self, card_id: str, entry: 'CachedImage') -> None:
        with self.lock:
            old = self.entries.pop(card_id, None)
            if old is not None:
                self.size -= len(old)
            self.entries[card_id] = entry
            self.size += len(entry)
            budget = self.budget
            if budget <= 0:
                return
            # An image bigger than the whole budget still goes in - it was just
            # asked for - and is simply the first thing out next time.
            while self.size > budget and len(self.entries) > 1:
                _, dropped = self.entries.popitem(last=False)
                self.size -= len(dropped)

    def Clear(self) -> None:
        with self.lock:
            self.entries.clear()
            self.size = 0

    def Stats(self) -> Tuple[int, int]:
        """How many images are held, and how many bytes they take."""
        with self.lock:
            return len(self.entries), self.size

class Cache:

    memory = ImageMemory()
    link_pic: Dict[str, str] = {}
    # The stand-ins made this session, by id. They are held apart from the
    # recency cache above rather than in it: a stand-in means no server had the
    # card, and letting one fall out of memory would put that 3s-per-server
    # question back on the next request for it. They are ~2 KB each.
    placeholders: Dict[str, 'CachedImage'] = {}

    # Images are loaded on their own pool rather than on the executor every
    # other request handler hands its work to (`TaskManager.ToThread`). A cold
    # New Game screen is ~160 tiles, and a tile that is not on disk yet is a
    # blocking `requests.get` of up to 3s per image server: on the shared
    # executor those fill every thread it has, and the JSON the page needs to
    # finish drawing itself queues behind card art it has not asked to see yet.
    pool: 'ThreadPoolExecutor|None' = None
    # Guards `pool` and `pending` together: a caller that finds no pending load
    # creates the pool and the entry in one step.
    pool_lock = threading.RLock()
    pending: Dict[str, 'Future[CachedImage]'] = {}

    # The art pack ships separately from the repo (install guide step 6).
    # `CheckAssets` fills these in at start-up; the menu reads them back.
    assets_missing: bool = False
    assets_folder: str = ""

    ASSETS_URL = "https://irefrixs.itch.io/marvel-lcg"

    @staticmethod
    def CheckAssets() -> bool:
        """Whether the downloaded art pack is in place.

        Without it nothing fails: every card falls back to a generated stand-in,
        so an install that skipped step 6 just looks like a game whose art is
        grey, and the reason is nowhere on screen. Say it once here instead, and
        leave the answer where the main menu can repeat it."""
        Cache.assets_folder = FileManager.JoinPath(TEXTURE_FOLDER.value, "sets")
        Cache.assets_missing = not FileManager.IsDir(Cache.assets_folder)
        if Cache.assets_missing:
            Log.Warn(CATEGORY_NAME,
                     f"{Cache.assets_folder} is not there, so every card will be drawn as a "
                     f"stand-in. Download the game from {Cache.ASSETS_URL} and put its `assets` "
                     "folder in the project root - install guide step 6.")
        return not Cache.assets_missing

    @staticmethod
    def IsPlaceholder(card_id: str) -> bool:
        return card_id.lstrip("/") in Cache.placeholders

    @staticmethod
    def SetLinkPic(card_id: str, link_to_pic_id: str):
        Cache.link_pic[card_id] = link_to_pic_id

    @staticmethod
    def SetCache(card_id: str, data: bytes, content_type: str='image/jpeg'):
        Cache.memory.Put(card_id, CachedImage(data, content_type))

    @staticmethod
    def IsCardId(name: str) -> bool:
        """Whether a name is a printed card id, and so worth asking a server for.

        Everything else in the image folders - board art, tokens, set covers -
        is shipped, never downloaded."""
        import re
        # Pattern to match: five digits, optionally followed by a face letter.
        return re.match(r'^\d{5}[a-z]?$', name) is not None

    @staticmethod
    def FindImagePath(card_id: str) -> str|None:
        """The file already holding this image, if any of the image folders,
        the texture folder or the disk cache has it."""
        for folder in IMAGE_FOLDERS.value + [TEXTURE_FOLDER.value, CACHE_FOLDER.value]:
            for ext_name in [".webp", ".jpg", ".png"]:
                check_path = f"{folder}/{card_id}{ext_name}"
                if FileManager.Exists(check_path):
                    return check_path
        return None

    @staticmethod
    def DownloadImage(card_id: str) -> bytes|None:
        """Ask each image server in turn for one card and write the first answer
        to the disk cache.

        Returns the bytes as the server sent them - the caller decides whether to
        rotate them or hold them in memory - or None when no server has the card.
        Safe to call from a worker thread: it touches the disk cache and nothing
        the rest of the process shares."""
        if not IMAGE_SERVERS.value or not Cache.IsCardId(card_id):
            return None

        skip_break = not BREAK_WHEN_LOAD_ONLINE_IMAGE.value
        if not skip_break:
            Debug.DebugBreak()

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        }

        # "https://cerebrodatastorage.blob.core.windows.net/cerebro-cards/official/${card_id}.jpg",
        # "https://marvelcdb.com/bundles/cards/${card_id}.jpg",
        # "https://marvelcdb.com/bundles/cards/${card_id}.png",

        for site in IMAGE_SERVERS.value:
            full_url = site
            full_url = full_url.replace('{card_id}', card_id)
            full_url = full_url.replace('{card_id:U}', card_id.upper())

            try:
                Log.DebugInfo(CATEGORY_NAME, f"Downloading from {full_url}")

                response = requests.get(full_url, headers=headers, timeout=3)
                response.raise_for_status()

                content_type = response.headers.get('Content-Type')

                ext_name = "bmp"
                if content_type:
                    # Determine the image format based on the Content-Type
                    if 'image/jpeg' in content_type:
                        ext_name = "jpg"
                    elif 'image/png' in content_type:
                        ext_name = "png"
                    elif 'image/webp' in content_type:
                        ext_name = "webp"

                Log.DebugInfo(CATEGORY_NAME, f"Downloaded: {card_id}")
                data = response.content
                # Save the image to the cache
                file_path = FileManager.JoinPath(CACHE_FOLDER.value, f"{card_id}.{ext_name}")
                FileManager.MakeDir(FileManager.GetDirName(file_path))
                with FileManager.OpenFile(file_path, write=True, bin=True) as file:
                    file.Write(data)
                return data
            except requests.exceptions.Timeout:
                Log.Warn(CATEGORY_NAME, f"Timeout occurred while downloading {card_id}")
            except requests.exceptions.RequestException as e:
                Log.Warn(CATEGORY_NAME, f"Request failed with error: {e}")
        return None

    @staticmethod
    def Pool() -> 'ThreadPoolExecutor':
        """The image pool, made on first use.

        Nothing creates it at start-up: a run that serves no images - a replay
        check, `-rehash`, the scripted tests - never makes a thread."""
        with Cache.pool_lock:
            if Cache.pool is None:
                Cache.pool = ThreadPoolExecutor(max_workers=max(1, IMAGE_WORKERS.value),
                                                thread_name_prefix="image")
            return Cache.pool

    @staticmethod
    def Shutdown() -> None:
        """Drop the pool. Loads still queued are abandoned - they are pictures,
        and the process is on its way out."""
        with Cache.pool_lock:
            pool, Cache.pool = Cache.pool, None
            Cache.pending.clear()
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def ForgetPending(card_id: str) -> None:
        with Cache.pool_lock:
            Cache.pending.pop(card_id, None)

    @staticmethod
    def RotatedPath(card_id: str) -> str:
        """Where the stood-up copy of a landscape image is kept.

        Its own folder under the disk cache, not beside the original: the loader
        looks in the image folders first, so a rotated file sharing the
        original's name would either be found instead of it or never be found at
        all, depending on which folder each landed in."""
        return FileManager.JoinPath(FileManager.JoinPath(CACHE_FOLDER.value, "rotated"),
                                    f"{card_id}.jpg")

    @staticmethod
    def ReadRotated(card_id: str, source_path: str) -> bytes|None:
        """The saved rotation of this file, if it is there and not stale.

        Stale means the original has been written since - a re-download, or a
        player replacing the art by hand - in which case the rotation is of the
        picture that used to be there and is thrown away."""
        rotated_path = Cache.RotatedPath(card_id)
        if not FileManager.Exists(rotated_path):
            return None
        if FileManager.ModifiedTime(rotated_path) < FileManager.ModifiedTime(source_path):
            return None
        with FileManager.OpenFile(rotated_path, read=True, bin=True) as file:
            return file.Read()

    @staticmethod
    def WriteRotated(card_id: str, data: bytes) -> None:
        """Keep a rotation so no later run has to decode the original again.

        Rotating is the one path here that costs a decode and a re-encode, and
        about one image in ten needs it. Failing to write is not worth reporting:
        the game has the image it wanted, and the only loss is doing this again
        next time."""
        rotated_path = Cache.RotatedPath(card_id)
        try:
            FileManager.MakeDir(FileManager.GetDirName(rotated_path))
            with FileManager.OpenFile(rotated_path, write=True, bin=True) as file:
                file.Write(data)
        except OSError as e:
            Log.DebugInfo(CATEGORY_NAME, f"Could not save the rotated {card_id}: {e}")

    @staticmethod
    def ReadImageFile(card_id: str, file_path: str) -> 'CachedImage|None':
        """One image off the disk, standing it up if it is lying down.

        The common case never opens the file with Pillow at all: it is already
        portrait, so its own bytes are served in their own format - a set tile
        stays the `.webp` it is stored as, instead of being decoded on every cold
        load and then called a JPEG on the way out."""
        rotated = Cache.ReadRotated(card_id, file_path)
        if rotated:
            return CachedImage(rotated, 'image/jpeg')

        with FileManager.OpenFile(file_path, read=True, bin=True) as file:
            data = file.Read()
        # An empty file is not an image; the caller falls through to the link and
        # the servers rather than serving nothing.
        if not data:
            return None

        image_data, was_rotated = ImageLib.RotateIfNeeded(data)
        if was_rotated:
            Cache.WriteRotated(card_id, image_data)
            return CachedImage(image_data, 'image/jpeg')
        return CachedImage(data, ImageLib.ContentTypeOf(data))

    @staticmethod
    def LoadImageFuture(card_id: str) -> 'Future[CachedImage]':
        """One in-flight load per card, however many callers ask for it at once.

        The board asks for the same art from several places in the same frame,
        and a reload asks for all of it again before the first answers. Without
        this each of those is its own download of the same card, and each one
        holds a pool thread for the 3s the server takes to answer."""
        with Cache.pool_lock:
            pending = Cache.pending.get(card_id)
            if pending is not None:
                return pending
            future = Cache.Pool().submit(Cache.LoadImageData, card_id)
            Cache.pending[card_id] = future
            # A future that finished before this line runs the callback here, on
            # this thread, while the lock is still held - hence the RLock.
            future.add_done_callback(lambda _: Cache.ForgetPending(card_id))
            return future

    @staticmethod
    async def LoadImageAsync(card_id: str) -> 'CachedImage':
        """`LoadImageData` without holding a request thread while it works.

        An image still in memory - which is every image asked for twice inside
        the cache budget - answers from here, with no thread hop at all."""
        card_id = card_id.lstrip("/")
        entry = Cache.memory.Get(card_id)
        if entry is not None:
            return entry
        return await asyncio.wrap_future(Cache.LoadImageFuture(card_id))

    @staticmethod
    def LoadImageData(card_id: str) -> 'CachedImage':
        # if url in ['enthralled_minion', 'minion', 'ultron_facedown_drone']:
        #     url = 'player'
        card_id = card_id.lstrip("/")

        entry = Cache.memory.Get(card_id)
        if entry is not None:
            return entry

        assert card_id != "", f"{card_id=}"
        file_name = card_id

        stand_in = Cache.placeholders.get(file_name)
        if stand_in is not None:
            return stand_in

        file_path = Cache.FindImagePath(file_name)
        if file_path:
            entry = Cache.ReadImageFile(file_name, file_path)
            if entry is not None:
                Cache.SetCache(file_name, entry.data, entry.content_type)
                return entry

        if file_name in Cache.link_pic:
            entry = Cache.LoadImageData(Cache.link_pic[file_name])
            if entry.data:
                return entry

        data = Cache.DownloadImage(card_id)
        if data:
            image_data, was_rotated = ImageLib.RotateIfNeeded(data)
            if was_rotated:
                # The download is on disk under its own name; keep the rotation
                # beside it so the next run reads it back instead of decoding.
                Cache.WriteRotated(file_name, image_data)
                content_type = 'image/jpeg'
            else:
                content_type = ImageLib.ContentTypeOf(image_data)
            Cache.SetCache(file_name, image_data, content_type)
            return CachedImage(image_data, content_type)

        # raise Exception(f"Failed to load {file_name} from the internet")
        # A stand-in is never written to the image cache. On disk it is
        # indistinguishable from real art, so one failed download would mask the
        # real image for good - including after the asset pack is installed or
        # the card appears on the image server. Holding it in memory is enough to
        # stop the same request hitting the network again this session.
        image_data = ImageCreator.CreateNoImage(card_id)
        stand_in = CachedImage(image_data)
        Cache.placeholders[file_name] = stand_in
        return stand_in


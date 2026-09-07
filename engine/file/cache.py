from core import *
import asyncio
import threading
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
# `save_empty_image` is gone: generated stand-ins are no longer written to disk.
BREAK_WHEN_LOAD_ONLINE_IMAGE = ConfigVariables.Bool('break_when_load_online_image', False)

class Cache:

    cache: Dict[str, bytes] = {}
    link_pic: Dict[str, str] = {}
    # Ids currently served by a generated stand-in rather than real art.
    placeholders: Set[str] = set()

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
    pending: Dict[str, 'Future[bytes]'] = {}

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
    def SetCache(card_id: str, data: bytes):
        Cache.cache[card_id] = data

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
    def LoadImageFuture(card_id: str) -> 'Future[bytes]':
        """One in-flight load per card, however many callers ask for it at once.

        The board asks for the same art from several places in the same frame,
        and a reload asks for all of it again before the first answers. Without
        this each of those is its own download of the same card, and each one
        holds a pool thread for the 3s the server takes to answer."""
        with Cache.pool_lock:
            pending = Cache.pending.get(card_id)
            if pending is not None:
                return pending
            future = Cache.Pool().submit(Cache.LoadImage, card_id)
            Cache.pending[card_id] = future
            # A future that finished before this line runs the callback here, on
            # this thread, while the lock is still held - hence the RLock.
            future.add_done_callback(lambda _: Cache.ForgetPending(card_id))
            return future

    @staticmethod
    async def LoadImageAsync(card_id: str) -> bytes:
        """`LoadImage` without holding a request thread while it works.

        An image already in memory - which is every image after the first time
        it is served - answers from here, with no thread hop at all."""
        card_id = card_id.lstrip("/")
        data = Cache.cache.get(card_id)
        if data is not None:
            return data
        return await asyncio.wrap_future(Cache.LoadImageFuture(card_id))

    @staticmethod
    def LoadImage(card_id: str) -> bytes:
        # if url in ['enthralled_minion', 'minion', 'ultron_facedown_drone']:
        #     url = 'player'
        card_id = card_id.lstrip("/")

        if card_id in Cache.cache:
            return Cache.cache[card_id]

        assert card_id != "", f"{card_id=}"
        file_name = card_id

        file_path = Cache.FindImagePath(file_name)
        if file_path:
            with FileManager.OpenFile(file_path, read=True, bin=True) as file:
                image_data = ImageLib.TryRotateImage(file.Read())
            # An empty file is not an image; fall through to the link and the
            # servers below rather than serving nothing.
            if image_data:
                Cache.SetCache(file_name, image_data)
                return image_data

        if file_name in Cache.link_pic:
            image_data = Cache.LoadImage(Cache.link_pic[file_name])
            if image_data:
                return image_data

        data = Cache.DownloadImage(card_id)
        if data:
            image_data = ImageLib.TryRotateImage(data)
            Cache.SetCache(file_name, image_data)
            return image_data

        # raise Exception(f"Failed to load {file_name} from the internet")
        # A stand-in is never written to the image cache. On disk it is
        # indistinguishable from real art, so one failed download would mask the
        # real image for good - including after the asset pack is installed or
        # the card appears on the image server. Holding it in memory is enough to
        # stop the same request hitting the network again this session.
        image_data = ImageCreator.CreateNoImage(card_id)
        Cache.placeholders.add(file_name)
        Cache.SetCache(file_name, image_data)
        return image_data


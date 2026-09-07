from core import *
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
# `save_empty_image` is gone: generated stand-ins are no longer written to disk.
BREAK_WHEN_LOAD_ONLINE_IMAGE = ConfigVariables.Bool('break_when_load_online_image', False)

class Cache:

    cache: Dict[str, bytes] = {}
    link_pic: Dict[str, str] = {}
    # Ids currently served by a generated stand-in rather than real art.
    placeholders: Set[str] = set()

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


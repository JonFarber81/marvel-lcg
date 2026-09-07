from core import *
from engine.config import ConfigVariables
from engine.file.cache import Cache
from engine.file.manager import FileManager
from engine.lib import Json
from engine.log import Log

CATEGORY_NAME = "CACHE"

PREFETCH_WORKERS = ConfigVariables.Int('prefetch_workers', 8)

class ImagePrefetch:
    """Fill `assets/cache` before the first session instead of during it.

    Every card the game draws is fetched from an image server the first time it
    is shown, one blocking request at a time, so a cold cache turns the New Game
    screen and the first few turns into a wait on cerebro. This walks the data
    files the same way the New Game screen does - `sets_info.json` names the
    scenarios and heroes, each of those names its cards - and downloads what is
    missing up front, several at a time."""

    @staticmethod
    def CardIds(data: Any) -> Set[str]:
        """Every card id anywhere in one data file.

        Ids sit under a dozen different keys (`villain`, `encounters`,
        `player_deck`, `nemesis_set`, ...) and a two-faced card is written as one
        "front,back" string, so read the shape rather than a list of key names:
        anything that looks like a printed id is one."""
        ids: Set[str] = set()

        def walk(node: Any) -> None:
            if isinstance(node, str):
                for part in node.split(","):
                    part = part.strip()
                    if Cache.IsCardId(part):
                        ids.add(part)
            elif isinstance(node, list):
                for item in cast(List[Any], node):
                    walk(item)
            elif isinstance(node, dict):
                for item in cast(Dict[Any, Any], node).values():
                    walk(item)

        walk(data)
        return ids

    @staticmethod
    def LoadJson(load_type: 'FileManager.JsonType', name: str) -> Dict[str, Any]|None:
        """One data file by name, or None when it is not there.

        Scenarios listed in `sets_info.json` whose file has not been written yet
        are a known gap (improvements 4.7), and a missing encounter set must not
        stop the walk either."""
        file_path = FileManager.FindJsonPath(load_type, name, nullable=True)
        if not file_path:
            return None
        try:
            return Json.Load(file_path)
        except Exception as exc:
            Log.Warn(CATEGORY_NAME, f"Could not read {file_path}: {exc}")
            return None

    @staticmethod
    def Collect() -> Set[str]:
        """The card ids of every scenario and hero the New Game screen offers."""
        sets_info = ImagePrefetch.LoadJson('SetInfo', "sets_info.json")
        if not sets_info:
            Log.Warn(CATEGORY_NAME, "sets_info.json is not there, so there is nothing to prefetch.")
            return set()

        ids: Set[str] = set()
        seen_encounter_sets: Set[str] = set()

        def add_encounter_set(name: str) -> None:
            if name in seen_encounter_sets:
                return
            seen_encounter_sets.add(name)
            data = ImagePrefetch.LoadJson('EncounterSet', name)
            if data:
                ids.update(ImagePrefetch.CardIds(data))

        def add_scenario(name: str) -> None:
            data = ImagePrefetch.LoadJson('Campaign', name)
            if not data:
                return
            ids.update(ImagePrefetch.CardIds(data))
            # The scenario names its sets rather than repeating their cards, and
            # the New Game screen ticks them on by default, so they are part of
            # the first session too.
            for key in ['encounter_sets', 'modular_sets']:
                for set_name in data.get(key, []):
                    add_encounter_set(set_name)

        for key, info in sets_info.items():
            if not isinstance(info, dict):
                # `sets_info.json` carries its checksum beside the sets.
                continue
            # Weekly challenges have no expert deck, and the New Game screen
            # draws no expert tile for them; asking for one is 30 warnings about
            # files that were never meant to exist.
            has_expert = key != "Weekly Challenges"
            for name in info.get('scenarios', []):
                add_scenario(name)
                if has_expert:
                    # The expert deck swaps in different encounter cards, and it
                    # is the tile right beside the standard one.
                    add_scenario(f"{name}_expert")
            for name in info.get('heroes', []):
                data = ImagePrefetch.LoadJson('Hero', name)
                if data:
                    ids.update(ImagePrefetch.CardIds(data))

        return ids

    @staticmethod
    def Run() -> None:
        from concurrent.futures import ThreadPoolExecutor

        ids = ImagePrefetch.Collect()
        if not ids:
            return

        missing = sorted(card_id for card_id in ids if not Cache.FindImagePath(card_id))
        have = len(ids) - len(missing)
        Log.Info(CATEGORY_NAME, f"Prefetching card images: {len(ids)} cards, {have} already here, "
                                f"{len(missing)} to download.")
        if not missing:
            return

        workers = max(1, PREFETCH_WORKERS.value)
        done = 0
        failed: List[str] = []

        # `DownloadImage` writes straight to the disk cache and shares nothing
        # else, so the only state the pool touches is this counter, and only from
        # the loop below - the workers hand their answer back.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for card_id, data in zip(missing, pool.map(Cache.DownloadImage, missing)):
                done += 1
                if not data:
                    failed.append(card_id)
                if done % 50 == 0 or done == len(missing):
                    Log.Info(CATEGORY_NAME, f"Prefetched {done}/{len(missing)}")

        if failed:
            Log.Warn(CATEGORY_NAME, f"{len(failed)} cards are on no image server and will be drawn "
                                    f"as stand-ins: {', '.join(failed[:10])}"
                                    f"{' ...' if len(failed) > 10 else ''}")
        Log.Info(CATEGORY_NAME, f"Prefetch finished: {len(missing) - len(failed)} images downloaded.")

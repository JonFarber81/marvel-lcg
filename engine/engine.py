from core import *
from engine.device.manager import DeviceManager

from game import *
from game.statistics.game_statistics import GameStatistics
from build import Build
from engine.log import Log
from engine.lib import TransText, ImageCreator, Ver
from engine.user.user_info import UserInfo
from engine.task import TaskManager
from engine.job import JobManager
from engine.device.manager.base import DeviceManager
from engine.lib.check_new_version import CheckForNewVersion
from engine.config import ConfigVariables
from engine.startup_error import StartupError

CATEGORY_NAME = "ENGINE"

CHECK_FOR_NEW_VERSION_ON_STARTUP    = ConfigVariables.Bool('check_for_new_version_on_startup', False)
PRINT_MY_USER_FINGERPRINT           = ConfigVariables.Bool('print_my_user_fingerprint', False)

DEVICE              = ConfigVariables.Str('device', "web")
REHASH              = ConfigVariables.Bool('rehash', False)
PREFETCH_IMAGES     = ConfigVariables.Bool('prefetch_images', False)

PROFILE_FOLDER      = ConfigVariables.Folder('profile_folder')
TEST_ALL            = ConfigVariables.Bool('test_all', False)
EDITOR              = ConfigVariables.Bool('editor', True)

ConfigVariables.SetGroupArgs('test', "-device -no_editor -no_statistics -test_result_file test_results.txt -hidden_log_categories CONTROLLER WEB VERSION STATISTICS")

class Engine:

    device_manager: 'DeviceManager'

    game: 'Game'
    statistics: 'GameStatistics'

    has_crashed = False
    in_unit_test = False

    @staticmethod
    def Initialize() -> bool:
        Ver.Initialize()
        game_name = f'Marvel LCG {Ver.ui_version_str}'
        System.SetTitle(game_name)

        # ConfigVariables.Test()

        def initialize() -> bool:
            Log.Info(CATEGORY_NAME, game_name)

            ConfigVariables.Initialize()

            if REHASH.value:
                # Nothing is running yet: write the card data's checksums back and stop,
                # so an edited data file stops warning on every start.
                from cards.database import CardsDB
                CardsDB.Rehash()
                return False

            from engine.file import Cache
            Cache.CheckAssets()

            if PREFETCH_IMAGES.value:
                # Fill the image cache and stop. Nothing else has to be running
                # for it, and a first session then opens on art it already has
                # instead of waiting on a card server a request at a time.
                from engine.file import ImagePrefetch
                ImagePrefetch.Run()
                return False

            JobManager.Initialize()
            TaskManager.Initialize()

            if CHECK_FOR_NEW_VERSION_ON_STARTUP.value:
                async def check_new_version() -> None:
                    CheckForNewVersion.Check()

                job = JobManager.AddJob(check_new_version, name="Check Version")

                if CHECK_FOR_NEW_VERSION_ON_STARTUP.is_from_command_line:
                    JobManager.WaitForAllJobsToComplete(job)
                    return False

            UserInfo.Initialize()
            if PRINT_MY_USER_FINGERPRINT.value:
                Log.Info(CATEGORY_NAME, f"{UserInfo.fingerprint=}")
                if PRINT_MY_USER_FINGERPRINT.is_from_command_line:
                    return False

            TransText.Initialize()
            ImageCreator.Initialize()

            from cards.database import CardsDB
            CardsDB.Initialize()

            if Build.release:
                EDITOR.value = False

            if EDITOR.value:
                from editor.editor import Editor
                Editor.Initialize()

            # for x in range(50020, 50033):
            #     y = CardsDB.papers[str(x)]
            #     text = y.text
            #     text = text.replace("\r", "")
            #     text = text.replace("\n", "\\n")
            #     text = text.replace('"', '\\"')
            #     print(f'"{x}": "{text}",')

            Engine.statistics = GameStatistics()
            Engine.statistics.Load()

            device = DeviceManager
            if DEVICE.value == "web":
                from engine.device.manager.web.manager import WebDeviceManager
                device = WebDeviceManager
            elif DEVICE.value == "scripted":
                from engine.device.manager.scripted.manager import ScriptedDeviceManager
                device = ScriptedDeviceManager
            else:
                from engine.device.manager.key.manager import KeyDeviceManager
                device = KeyDeviceManager

            Engine.device_manager = device()
            Engine.game = Game(Engine.statistics, Engine.device_manager)
            return True

        try:
            return initialize()
        except StartupError as exc:
            # Something the player can fix, named in the message: a port already
            # in use, a folder that is not there. One line is the whole story.
            Log.Assert(CATEGORY_NAME, str(exc))
            return False
        except Exception as exc:
            if not Build.release:
                raise
            Log.OnCrash(CATEGORY_NAME, exc, "", None)
            return False

    @staticmethod
    def EngineRun() -> None:
        if Build.release:
            try:
                Engine.game.GameRun()
            except Exception as exc:
                Log.OnCrash(CATEGORY_NAME, exc, "", None)
                Log.SaveCrashLog()
        else:
            if TEST_ALL.value:
                from unit_test.entry import TestEntry
                from unit_test.runner import TestRunner
                TestRunner.Execute(TestEntry.Test, True)
                return
            elif PROFILE_FOLDER.is_initialized and PROFILE_FOLDER.value:
                from unit_test.entry import TestEntry
                from unit_test.runner import TestRunner
                TestRunner.Execute(TestEntry.Test, PROFILE_FOLDER.value, True)
                return

            if EDITOR.value:
                from editor.editor import Editor
                Editor.EditorRun()
            Engine.game.GameRun()

    @staticmethod
    def Shutdown():
        Log.Print("\n--- Engine Shutdown ---")
        Engine.game.Shutdown()

        if EDITOR.value:
            from editor.editor import Editor
            Editor.Shutdown()

        JobManager.Shutdown()
        TaskManager.Shutdown()

        # System.Pause()
        return

    ################################################################################
    #
    @staticmethod
    def SaveCrash():
        if not Engine.has_crashed:
            # A crash during start-up gets here before `Engine.game` is assigned.
            # There is no scene to save then, and reaching for one turns one
            # traceback into two, hiding the first - which is the real one.
            game = getattr(Engine, 'game', None)
            if game is not None:
                game.session.SaveScene(f'./crash.json', delete_old=False)
            Engine.has_crashed = True
        if Engine.in_unit_test:
            exit(-1)

import builtins
setattr(builtins, "DebugBreak", lambda: Debug.DebugBreak(True))
# You can call `DebugBreak()` any where without import


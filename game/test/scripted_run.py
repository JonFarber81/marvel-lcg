from core import *
from engine.file import FileManager
from engine.lib import Json
from engine.log import Log
from game import *
from game.scene.scene import Scene
from game.scene.loader import SceneLoader
from game.test.auto_player import POLICY, AutoPlayer

CATEGORY_NAME = "SCRIPTED"

@dataclass
class ScriptedExpect:
    """The end state a case is expected to reach.

    Everything here is a line of text on purpose: a failing case then reads as a
    diff a person can act on ("threat 12/12" vs "threat 10/12") instead of a
    changed hash.
    """
    result: str = field(default="")
    players_won: bool = field(default=False)
    rounds: int = field(default=0)
    inputs: int = field(default=0)
    schemes: List[str] = field(default_factory=lambda: [])
    villains: List[str] = field(default_factory=lambda: [])
    players: List[str] = field(default_factory=lambda: [])

@dataclass
class ScriptedCase:
    """A scripted scenario: what to play, how to play it, and where it ends up.

    The inputs themselves are not in here - they live in the replay file beside
    this one, in the game's own replay format, recorded by playing the recipe
    with `policy`. So a case is a seed plus an input list plus an end state, and
    the replay is a real replay: copy it into "./replays/" and the app's replay
    viewer opens it like any other game.
    """
    comment: str = field(default="")
    scenario: str = field(default="")
    heroes: List[str] = field(default_factory=lambda: [])
    seed: int = field(default=0)
    rules: List[str] = field(default_factory=lambda: [])
    policy: 'POLICY' = field(default="pass")
    max_prompts: int = field(default=20000)
    expect: ScriptedExpect = field(default_factory=lambda: ScriptedExpect())

class ScriptedRun:

    REPLAY_SUFFIX = ".replay.json"

    ################################################################################
    # Reading the end state
    @staticmethod
    def Summarize(game: 'Game') -> 'ScriptedExpect':
        from game.card.face.base import Scheme2
        from game.card.face.card_type.identity import Hero
        from game.operate.worlds import Worlds

        world = game.world
        assert world

        def card_id(face: Any) -> str:
            return str(face.paper.card_id)

        def scheme_text(scheme: 'Scheme2') -> str:
            target = getattr(scheme, 'target_threat', None)
            target_text = str(target) if target != None else "-"
            return f"{card_id(scheme)} threat {scheme.threat}/{target_text}"

        def villain_text(villain: Any) -> str:
            return f"{card_id(villain)} hp {villain.health}"

        def player_text(player: Any) -> str:
            identity = player.GetIdentity()
            form = "hero" if Hero.IsType(identity) else "alter_ego"
            state = " eliminated" if player.is_eliminated else ""
            return (f"{player.name} {card_id(identity)} {form}"
                    f" hp {identity.health}"
                    f" hand {len(player.hand_cards.GetAll())}"
                    f" deck {len(player.player_deck.GetAll())}"
                    f" discard {len(player.discard_pile.GetAll())}"
                    f"{state}")

        return ScriptedExpect(
            result=str(world.game_over.reason),
            players_won=bool(getattr(world.game_over, 'players_won', False)),
            rounds=world.round_id,
            inputs=len(game.controller_manager.replay.history_inputs),
            schemes=[scheme_text(x) for x in Worlds.GetAllMainSchemes(world)],
            villains=[villain_text(x) for x in Worlds.GetAllVillains(world)],
            players=[player_text(x) for x in world.const_players],
        )

    @staticmethod
    def Diff(expect: 'ScriptedExpect', got: 'ScriptedExpect') -> List[str]:
        """Field-by-field differences, as lines to print."""
        from dataclasses import asdict
        differences: List[str] = []
        a = asdict(expect)
        b = asdict(got)
        for key in a:
            if a[key] != b[key]:
                differences.append(f"  {key}:\n    expected: {a[key]}\n    got:      {b[key]}")
        return differences

    ################################################################################
    # Running
    @staticmethod
    def RunScene(game: 'Game', scene: 'Scene') -> None:
        """Set a scene up and play it to game over, the same way `TestRun` does."""
        if game.session.scene:
            del game.session.scene
        game.session.SetScene(scene, 'InTesting')
        game.GameSetup()
        game.GameLoop()

    @staticmethod
    def NewScene(case: 'ScriptedCase') -> 'Scene':
        def read(json_type: 'FileManager.JsonType', name: str) -> str:
            file_path = FileManager.FindJsonPath(json_type, name)
            assert file_path, f"{json_type} not found: {name}"
            with FileManager.OpenFile(file_path, read=True) as file:
                return file.Read()

        return SceneLoader.NewFromJson(
            read('Campaign', case.scenario),
            None,
            [read('Hero', x) for x in case.heroes],
            case.seed,
            case.rules[:],
            {})

    @staticmethod
    def Play(game: 'Game', case: 'ScriptedCase') -> 'Tuple[Scene, ScriptedExpect]':
        """Play the recipe with its policy. Used to record a case."""
        from engine.device.manager.scripted.manager import ScriptedDeviceManager

        player = AutoPlayer(case.policy, max_prompts=case.max_prompts)
        ScriptedDeviceManager.answer_input = player.Answer
        try:
            scene = ScriptedRun.NewScene(case)
            ScriptedRun.RunScene(game, scene)
        finally:
            ScriptedDeviceManager.answer_input = None
        return scene, ScriptedRun.Summarize(game)

    @staticmethod
    def Replay(game: 'Game', replay_path: str) -> 'ScriptedExpect':
        """Replay a recorded case. Every input carries the board CRC it was made
        against, so the engine reports where behaviour first diverged."""
        scene = SceneLoader.Load(replay_path)
        assert scene, f"Replay not found: {replay_path}"
        scene.HackTestRule()
        ScriptedRun.RunScene(game, scene)
        return ScriptedRun.Summarize(game)

    ################################################################################
    # Case files
    @staticmethod
    def GetReplayPath(case_path: str) -> str:
        return case_path[:-len(".json")] + ScriptedRun.REPLAY_SUFFIX

    @staticmethod
    def Load(case_path: str) -> 'ScriptedCase':
        return Json.LoadAs(case_path, ScriptedCase)

    @staticmethod
    def SaveCase(case: 'ScriptedCase', case_path: str) -> None:
        Json.Save(case, case_path, ignore_check_sum=True)
        Log.Info(CATEGORY_NAME, f"Saved: {case_path}")

    @staticmethod
    def SaveReplay(scene: 'Scene', game: 'Game', case_name: str, replay_path: str) -> None:
        scene.PrepareSave(game, playtime=None)
        # Recorded, not played: no author to sign it and no clock to stamp it,
        # so the file stays the same from one recording to the next.
        scene.SetMetadataStr("sign", "")
        scene.SetMetadataStr("time", "")
        scene.SetMetadataStr("comment", case_name)
        scene.metadata.pop("path", None) # type: ignore
        Json.Save(scene, replay_path, ignore_check_sum=False)
        Log.Info(CATEGORY_NAME, f"Saved: {replay_path}")

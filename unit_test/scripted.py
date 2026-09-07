"""Scripted scenario regression cases.

A case is a recipe - scenario, heroes, seed, rules - plus the policy that played
it, plus the end state it reached. Beside each case file is the replay the
recipe recorded, in the game's own replay format, so checking a case replays a
fixed list of inputs and compares where the game ended up.

Two things have to hold for a case to pass:

  * the replay runs clean. Every recorded input carries the board CRC it was
    made against, so a card that behaves differently now is reported at the step
    where it first diverged, card by card.
  * the end state still matches, so a change that the CRC happens not to catch
    (a different winner, an extra round, threat left on the scheme) still fails.

    python -m unit_test.scripted                    # check every case
    python -m unit_test.scripted check <name>...    # check some of them
    python -m unit_test.scripted record [<name>...] # re-record after an intended change

Recording replaces both the replay and the expected end state, so read the diff
before committing it: that diff is the rules change under review.
"""

import os
import sys
import io
import contextlib

# A breakpoint from deep in the engine would hang a CI run forever.
os.environ.setdefault("PYTHONBREAKPOINT", "0")

from build import Build
# Log statistics - the only record of what went wrong - are not collected in a
# release build, and they are how a case knows it failed.
Build.release = False

from typing import Callable, List, Sequence, Tuple

CASES_FOLDER = "./unit_test/cases/"
LOG_TAIL_LINES = 80

class ScriptedTest:

    started = False

    ################################################################################
    #
    @staticmethod
    def Startup() -> None:
        """Bring up one engine for the whole run; cases share it, as replays do."""
        if ScriptedTest.started:
            return

        sys.argv += [
            '-device', 'scripted',
            '-no_editor',
            '-no_statistics',
            '-hidden_log_categories', 'CONTROLLER', 'WEB', 'VERSION', 'STATISTICS',
        ]

        from engine import Engine
        assert Engine.Initialize(), "Engine failed to initialize"

        from game.test import Test
        Test.is_in_test = True

        ScriptedTest.started = True

    ################################################################################
    #
    @staticmethod
    def GetCasePaths(names: Sequence[str]=()) -> List[str]:
        from engine.file import FileManager
        from game.test.scripted_run import ScriptedRun

        paths = sorted(
            x for x in FileManager.ListFiles(CASES_FOLDER, ext=".json")
            if not x.endswith(ScriptedRun.REPLAY_SUFFIX))

        if names:
            wanted = [x.replace(".json", "") for x in names]
            paths = [x for x in paths if ScriptedTest.GetCaseName(x) in wanted]
            missing = [x for x in wanted if x not in [ScriptedTest.GetCaseName(y) for y in paths]]
            assert not missing, f"No such case: {missing}"
        return paths

    @staticmethod
    def GetCaseName(case_path: str) -> str:
        from engine.file import FileManager
        return FileManager.GetBaseName(case_path)[:-len(".json")]

    ################################################################################
    #
    @staticmethod
    def Quietly(func: Callable[[], List[str]]) -> Tuple[List[str], str]:
        """Run a case with its log held back, so a passing run stays quiet and a
        failing one can show the tail of what the engine printed."""
        buffer = io.StringIO()
        try:
            with contextlib.redirect_stdout(buffer):
                result = func()
        except Exception as exc:
            import traceback
            traceback.print_exc(file=buffer)
            result = [f"  raised {type(exc).__name__}: {exc}"]
        return result, buffer.getvalue()

    @staticmethod
    def GetLogTail(log_text: str) -> str:
        import re
        lines = log_text.replace("\r", "\n").splitlines()
        # Drop the blank lines and the "12 / 20" step counter the replay prints
        # over itself, so the tail is the part worth reading.
        lines = [x for x in lines if x.strip() and not re.fullmatch(r"\d+ / \d+", x.strip())]
        return "\n".join(lines[-LOG_TAIL_LINES:])

    ################################################################################
    #
    @staticmethod
    def Check(case_path: str) -> List[str]:
        """Replay the case and compare the end state. Returns what went wrong."""
        from engine import Engine
        from engine.file import FileManager
        from engine.log import Log
        from game.test.scripted_run import ScriptedRun

        ScriptedTest.Startup()

        case = ScriptedRun.Load(case_path)
        replay_path = ScriptedRun.GetReplayPath(case_path)
        if not FileManager.Exists(replay_path):
            return [f"  no replay recorded: run `python -m unit_test.scripted record {ScriptedTest.GetCaseName(case_path)}`"]

        got = ScriptedRun.Replay(Engine.game, replay_path)

        failures: List[str] = []
        if Log.HasError(error=True):
            failures.append("  the engine reported an error while replaying (see the log below)")
        failures += ScriptedRun.Diff(case.expect, got)
        return failures

    @staticmethod
    def Record(case_path: str) -> List[str]:
        """Play the recipe and write both the replay and the end state."""
        from engine import Engine
        from engine.log import Log
        from game.test.scripted_run import ScriptedRun

        ScriptedTest.Startup()

        case = ScriptedRun.Load(case_path)
        scene, got = ScriptedRun.Play(Engine.game, case)

        case.expect = got
        ScriptedRun.SaveCase(case, case_path)
        ScriptedRun.SaveReplay(scene, Engine.game, ScriptedTest.GetCaseName(case_path),
                                ScriptedRun.GetReplayPath(case_path))

        if Log.HasError(error=True):
            return ["  the engine reported an error while recording (see the log below)"]
        return []

################################################################################
#
def main(argv: Sequence[str]|None=None) -> int:
    args = [x for x in (argv if argv != None else sys.argv[1:]) if not x.startswith('-')]
    command = args[0] if args and args[0] in ("check", "record") else "check"
    names = args[1:] if args and args[0] in ("check", "record") else args

    ScriptedTest.Startup()
    try:
        paths = ScriptedTest.GetCasePaths(names)
    except AssertionError as exc:
        print(exc)
        return 1
    if not paths:
        print(f"No cases in {CASES_FOLDER}")
        return 1

    run = ScriptedTest.Record if command == "record" else ScriptedTest.Check

    failed = 0
    for case_path in paths:
        name = ScriptedTest.GetCaseName(case_path)
        failures, log_text = ScriptedTest.Quietly(lambda path=case_path: run(path))
        if failures:
            failed += 1
            print(f"FAIL {name}")
            print("\n".join(failures))
            print(f"--- last {LOG_TAIL_LINES} log lines ---")
            print(ScriptedTest.GetLogTail(log_text))
            print("--- end of log ---")
        else:
            print(f"ok   {name} ({command})")

    print(f"\n{len(paths) - failed}/{len(paths)} cases {'recorded' if command == 'record' else 'passed'}")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())

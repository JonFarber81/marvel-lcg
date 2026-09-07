"""`unittest` front end for the scripted regression cases.

    python -m unittest unit_test.test_scripted

One test per case file, so a failure names the case that broke. The cases
themselves, and how to re-record them, are described in `unit_test/scripted.py`.
"""

import unittest

from unit_test.scripted import ScriptedTest

def setUpModule() -> None:
    # One engine for the whole module: cases share it the way replays do.
    ScriptedTest.Startup()

class TestScripted(unittest.TestCase):
    pass

def AddCase(case_path: str) -> None:
    name = ScriptedTest.GetCaseName(case_path)

    def run(self: 'TestScripted') -> None:
        failures, log_text = ScriptedTest.Quietly(lambda: ScriptedTest.Check(case_path))
        if failures:
            self.fail("\n".join([
                f"{name} no longer plays out the same way:",
                *failures,
                "--- log ---",
                ScriptedTest.GetLogTail(log_text),
            ]))

    run.__name__ = f"test_{name}"
    setattr(TestScripted, run.__name__, run)

for path in ScriptedTest.GetCasePaths():
    AddCase(path)

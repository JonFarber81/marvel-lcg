from core import *
from engine.device import *
from engine.controller import *

class ScriptedDevice(OutputDevice, InputDevice):
    """A device with no client behind it.

    Prompts are answered by the manager's `answer_input` callback, so a game can
    be played from start to game over inside one process. Used by the scripted
    regression harness (`game/test/scripted_run.py`) to record a replay; while a
    recorded replay is being checked the inputs come from the replay itself and
    this device is only asked if the replay runs out.
    """

    @override
    def __init__(self, controller: 'Controller', manager: 'ScriptedDeviceManager') -> None:
        self.manager_scripted = manager
        super().__init__(controller, manager)

    ################################################################################
    #
    @override
    def IsConnect(self) -> bool:
        return True

    @override
    def IsSyncReady(self) -> bool:
        return True

    @override
    def IsInputReady(self) -> bool:
        payload = self.manager.ask_options[self.player_id]
        answer = self.manager_scripted.Answer(payload, self.player_id)
        self.manager.WhenInput(answer, self.player_id)
        return True

    ################################################################################
    #
    @override
    def Render(self) -> None:
        pass

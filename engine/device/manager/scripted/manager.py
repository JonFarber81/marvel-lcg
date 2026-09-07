from core import *
from engine.controller import *
from engine.device import *
from engine.device.manager.base import AskOptionPayload
from engine.device.scripted.scripted_device import ScriptedDevice
from engine.log import Log

CATEGORY_NAME = "SCRIPTED"

class ScriptedDeviceManager(DeviceManager):
    """Device manager for headless runs (`-device scripted`).

    The harness installs an answer callback before `Engine.Initialize()`; it is
    given the prompt and the player it is meant for, and returns the same input
    JSON a client would post. Without one, every prompt is declined, which is
    enough to finish a replay that has run out of inputs instead of hanging.
    """

    # (payload, player_id) -> input json
    answer_input: 'Callable[[AskOptionPayload, int], str]|None' = None

    def __init__(self) -> None:
        super().__init__()
        Log.Print(f"Using scripted device")

    @override
    def CreateDevices(self, controller: 'Controller') -> Tuple['OutputDevice', 'InputDevice']:
        device = ScriptedDevice(controller, self)
        return device, device

    def Answer(self, payload: 'AskOptionPayload', player_id: int) -> str:
        if ScriptedDeviceManager.answer_input:
            return ScriptedDeviceManager.answer_input(payload, player_id)
        return '{"id": "", "targets": [], "resources": []}'

from core import *

class StartupError(Exception):
    """A start-up problem the player can fix themselves.

    A port already in use, a folder that is not there: the cause is named in the
    message and a traceback adds nothing to it. `Engine.Initialize` catches this
    and prints the one line, where any other exception is still a crash.
    """

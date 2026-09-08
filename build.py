import os

def EnvFlag(name: str) -> bool:
    """True when the environment sets `name` to anything but an off value."""
    return os.environ.get(name, "").strip().lower() not in ("", "0", "false", "off", "no")

class Build:
    # A plain `py main.py` is a release build - that is what ships, and the debug
    # build pays for its extra work: the call and instance trackers, coverage, and
    # every assert guarded by `if not Build.release`. `DEBUG=1` opts into it, and
    # `RELEASE=1` wins over `DEBUG`, so a shell that exports one can still start
    # the other. The tests set this directly and are not affected either way.
    release = EnvFlag("RELEASE") or not EnvFlag("DEBUG")

    # Version
    MAJOR = 0
    MINOR = 5
    PATCH = 9
    BUILD = 202

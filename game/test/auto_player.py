from core import *
from engine.device.manager.base import AskOptionPayload
from engine.lib import Json

POLICY = Literal["pass", "attack", "thwart"]

# What each policy reaches for on its turn, best first. The names are the ones
# `Effect.GetDisplayName(remove_space=True)` produces - the same text a replay
# records for its inputs. Heroes start in alter-ego, so both acting policies
# have to flip form before a basic action is on offer at all.
POLICY_ORDER: Dict['POLICY', List[str]] = {
    "pass":   [],
    "attack": ["Basic_Attack", "Change_Form"],
    "thwart": ["Basic_Thwart", "Change_Form"],
}

class AutoPlayTooLong(Exception):
    """The policy answered `max_prompts` prompts and the game still had not ended."""

class AutoPlayer:
    """A deterministic stand-in for a person at the keyboard.

    Every answer comes from the prompt itself - the option list, whether the
    prompt can be declined - and never from the board or the clock, so the same
    seed always plays the same game. That is what lets the harness record a
    replay once and check it forever after.

    `pass`   declines everything optional and takes the first legal option when
             the game forces a choice. The heroes never act, so the villain wins
             on schedule: a short game that still walks setup, every step of the
             villain phase, and defeat.
    `attack` flips to hero form and spends each turn attacking.
    `thwart` flips to hero form and spends each turn thwarting, which holds the
             main scheme back and so plays a longer game than the other two.

    Cards are never played: the acting policies pay no resources, so they only
    take abilities that cost none.

    A prompt that comes back unchanged means the answer was rejected, so the
    next answer for it is a different one and, once the options run out, a
    decline. Nothing can spin on one prompt.
    """

    DECLINE = '{"id": "", "targets": [], "resources": []}'

    def __init__(self, policy: 'POLICY'="pass", *, max_prompts: int=20000) -> None:
        self.policy = policy
        self.max_prompts = max_prompts

        self.prompts = 0
        self.last_key = ""
        self.repeat = 0

    ################################################################################
    #
    def Answer(self, payload: 'AskOptionPayload', player_id: int) -> str:
        self.prompts += 1
        if self.prompts > self.max_prompts:
            raise AutoPlayTooLong(
                f"No game over after {self.max_prompts} prompts (last: {payload.event_name})")

        key = f"{payload.event_name}|{payload.options_json}"
        if key == self.last_key:
            self.repeat += 1
        else:
            self.last_key = key
            self.repeat = 0

        answers = self.Plan(payload)
        if self.repeat >= len(answers):
            return AutoPlayer.DECLINE
        return answers[self.repeat]

    ################################################################################
    #
    def Plan(self, payload: 'AskOptionPayload') -> List[str]:
        """Answers to try for this prompt, in order."""
        options = self.GetOptions(payload)

        preferred: List[Dict[str, Any]] = []
        for name in POLICY_ORDER[self.policy]:
            preferred += [x for x in options if x.get("name") == name]

        answers = [self.Choose(x) for x in preferred]
        if payload.show_cancel:
            answers.append(AutoPlayer.DECLINE)
        answers += [self.Choose(x) for x in options if x not in preferred]
        answers.append(AutoPlayer.DECLINE)
        return answers

    def GetOptions(self, payload: 'AskOptionPayload') -> List[Dict[str, Any]]:
        if not payload.options_json:
            return []
        options: List[Dict[str, Any]] = Json.LoadAsList(payload.options_json)
        # An option with a failure reason is shown greyed out; it cannot be taken.
        options = [x for x in options if not x.get("failure_reason")]
        # Nothing here pays for anything, so an ability that costs resources
        # would just fail its cost check and be reported as an engine error.
        return [x for x in options if AutoPlayer.IsFree(x)]

    @staticmethod
    def IsFree(option: Dict[str, Any]) -> bool:
        payments: Dict[str, Any] = option.get("target_payment", {})
        for target in payments:
            if str(payments[target].get("cost", "")) not in ("", "0", "*"):
                return False
        return True

    def Choose(self, option: Dict[str, Any]) -> str:
        """The input a client would post for this option, with the fewest targets
        the effect will accept and no resources spent."""
        legal_targets: List[int] = option.get("all_legal_targets", [])
        target_range: List[int] = option.get("target_num_range", [0, 0])
        need = target_range[0] if target_range else 0

        return Json.Dumps({
            "id": str(option.get("id", "")),
            "targets": [str(x) for x in legal_targets[:need]],
            "resources": [],
        })

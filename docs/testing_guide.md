# Testing Guide

The rules live in ~2,000 card scripts. Nothing in a card script is typed against
the rest of the game, so a change to one card - or to the message pipeline every
card sits on - can quietly change how a different card behaves. The scripted
regression cases are the net for that: fixed games that must keep playing out
exactly as they did.

---

## Running the cases

```sh
python -m unittest unit_test.test_scripted -v     # one test per case
python -m unit_test.scripted                      # the same run, as a script
python -m unit_test.scripted check core_rhino_solo_pass
```

They need no `assets/` folder, no browser and no network - the whole game runs
in-process against a scripted device - and the current set finishes in a couple
of seconds. CI runs them on every push and pull request that touches `cards/`,
`game/`, `engine/`, `core/` or `data/`
(`.github/workflows/rules_regression.yml`).

---

## What a case is

Each case is two files in `unit_test/cases/`:

| File | What it holds |
| --- | --- |
| `<name>.json` | the recipe - scenario, heroes, seed, rules, the policy that played it - and the end state it reached |
| `<name>.replay.json` | the inputs, in the game's own replay format |

```jsonc
{
    "comment": "Rhino vs a Spider-Man who never acts: setup, the villain phase end to end, and losing to the scheme clock.",
    "scenario": "rhino",
    "heroes": ["spider_man"],
    "seed": 12345,
    "rules": ["v16_all", "no_crisis_of_infinite_deadpools", "no_encounter_cards_ignore_crisis"],
    "policy": "pass",
    "max_prompts": 20000,
    "expect": {
        "result": "The Main Scheme was Completed",
        "players_won": false,
        "rounds": 3,
        "inputs": 7,
        "schemes":  ["01097b threat 8/7"],
        "villains": ["01094 hp 14"],
        "players":  ["Spider-Man 01001b alter_ego hp 10 hand 6 deck 34 discard 0"]
    }
}
```

The replay file is an ordinary replay: drop it in `./replays/` and the app's
replay viewer will open it like any other game.

A case passes when two things hold:

1. **The replay runs clean.** Every recorded input carries the CRC of the whole
   board at the moment it was made, so a card that behaves differently now is
   reported at the step where it first diverged, card by card.
2. **The end state still matches** the `expect` block, which catches the changes
   a CRC comparison can miss - a different winner, an extra round, threat left
   on the scheme.

---

## Reading a failure

```
FAIL core_rhino_expert_solo_thwart
  the engine reported an error while replaying (see the log below)
  inputs:
    expected: 20
    got:      18
  players:
    expected: ['Spider-Man 01001a hero hp 2 hand 5 deck 33 discard 2']
    got:      ['Spider-Man 01001b alter_ego hp 2 hand 6 deck 33 discard 1']
--- last 80 log lines ---
[REP] 0.107 |  Key | Read | Curr | (#16 / 20)
[REP] 0.107 | c78  | 6    | 7    | +1
```

The table is the useful part: at input 16 of 20, card object `c78` was recorded
with 6 and now has 7. Track that object id back through the log above it (each
line names the cards it touched) to find which card changed. Everything after
the first divergence is downstream of it, so fix the earliest one first.

---

## Adding a case

1. Write the recipe. Copy an existing case file, change the scenario, heroes,
   seed and policy, and leave `expect` empty:

   ```sh
   cp unit_test/cases/core_rhino_solo_pass.json unit_test/cases/my_case.json
   ```

2. Record it:

   ```sh
   python -m unit_test.scripted record my_case
   ```

   Recording plays the recipe with its policy and writes both the replay and the
   `expect` block. It fails if the engine logs an error along the way, so a case
   never gets recorded against a broken run.

3. Read what it recorded - the `expect` block says how that game ended - then
   commit both files.

Scenario and hero names are the file names under `data/scenarios/` and
`deck/starter/`. Rules are the ones `game/world/world_rule.py` defines; the list
above is what the New Game screen sends by default.

### The policies

A case is played by `game/test/auto_player.py`, which answers prompts from the
option list alone - never from the board or the clock - so a seed always plays
the same game.

| Policy | What it does |
| --- | --- |
| `pass` | declines everything optional, takes the first legal option when forced. The heroes never act, so the villain wins on schedule. |
| `attack` | flips to hero form and attacks every turn. |
| `thwart` | flips to hero form and thwarts every turn, which holds the scheme back and plays a longer game. |

No policy plays cards: they pay no resources, so they only take abilities that
cost none. That keeps recording deterministic and free of "could not pay"
failures; the price is that card-play interactions are not covered by the
policies themselves. To cover a specific card, record a case whose scenario and
deck force that card into play.

---

## After an intended rules change

A case that fails because you *meant* to change the rules is re-recorded:

```sh
python -m unit_test.scripted record            # every case
python -m unit_test.scripted record core_rhino_solo_pass
```

Read the diff before committing it. The `expect` block is the reviewable part -
"threat 8/7" becoming "threat 10/7" is the rules change, stated in one line. If
a diff shows something you did not intend, that is the regression the case
exists to catch. Never re-record just to get a green run.

---

## The other test entry points

| Entry | What it covers |
| --- | --- |
| `unit_test/test_scripted.py` | the scripted cases described here |
| `unit_test/test_image_cache.py` | the image cache: its memory budget, which images get decoded, and what each is called on the wire - it builds its own pictures, so it needs no `assets/` and no network, and CI runs it beside the cases |
| `unit_test/test_all.py` | replays the games saved under `./replays/`, the same way, for whatever you have recorded locally |
| `unit_test/test_task.py` | build chores (version bump, card zip), not tests of the rules |
| `puzzle/test/` | hand-built board states for the puzzle mode |

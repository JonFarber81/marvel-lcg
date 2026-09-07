# Potential Improvements

Suggestions gathered from a code read-through and a live run of v0.5.9.201r on macOS
(2026-09-06). Each item names the file it touches so it can be picked up directly.

Priority: **P1** = players hit it in a normal session · **P2** = noticeable friction ·
**P3** = polish. Effort: **S** < 1 day · **M** 1–3 days · **L** a week or more.

---

## 1. UI

| # | Item | Pri | Eff |
|---|------|-----|-----|
| 1.1 | **Set tiles show only a number.** `scene.html:415` derives the label with `key.match(/^([\w\d]+)\./)`, so "1. Core Set" renders as `1`. Show the full name on hover (`title=` attribute) and as a caption under the art. | P2 | S |
| 1.2 | **DONE** - Placeholder images were blank: `ImageCreatorHelper.DrawText` never drew, because its word-wrap loop was commented out (it used `draw.textsize()`, removed in Pillow 10). Rewritten with `draw.textlength()`, plus a macOS/Linux monospace font fallback so `cour.ttf` missing no longer silently shrinks the text. | P1 | S |
| 1.3 | **DONE** - The New Game screen reports its own load. `LoadProgress` (`public/scene.html`) drives a banner across the top of the page: each phase names what it is fetching and the bar counts the fetches as they settle ("Loading scenarios 120/164"), through scenarios, encounter sets and the hero gallery. A phase that throws now leaves the banner up in red instead of silently abandoning a half-built page. | P1 | S |
| 1.4 | **DONE** - The four raw file inputs are gone. Each hero slot is a portrait button that opens a gallery built from `/list_starter_deck` and `/list_deck` (every starter deck, plus anything in "./deck" under "My Deck"), sorted by name, with a filter that matches hero, file and set names, decks that share a hero name told apart by their file name ("Black Panther (shuri)"), and Escape or a backdrop click to dismiss. Slots show the hero name and a clear button; the file picker stays behind "Import…", next to the clipboard import. | P1 | M |
| 1.5 | **Orange counters like `(2/4)` are unexplained.** Sets 55, 56 and Weekly Challenges are missing scenario files (see §5.3). Add a tooltip listing which scenarios are unavailable and why. | P2 | S |
| 1.6 | **DONE** - The Modular Sets legend says what is selected. `#modular-summary` (`public/scene.html`) reads "(3) Bomb Scare, Masters of Evil, Under Attack" beside the legend, whether the list is expanded or not; past four names it counts the rest ("and 5 more") and the full list is the `title`. Buttons carry the set's real name in `data-label` (from the set JSON's `name`) rather than its file name. Four places toggle a set - the button, Random, the scenario's own defaults, the restored form - so the summary is driven by a `MutationObserver` on the `click` class instead of a call bolted onto each of them. | P2 | S |
| 1.7 | **DONE** - A stale page is told so in its own language. `WebServer.VersionMismatchResponse` answers `409 {"error": "version_mismatch", "version": ...}` when the caller sent `Accept: application/json` or any `X-Requested-With`, and the mismatch page otherwise, so the address bar still gets the page that explains itself. `public/js/version_guard.js` supplies the header on every same-origin `fetch` and, on that 409, reloads the page - the reload is a navigation, so it lands on the mismatch page. Loaded first by every page that talks to the server. | P2 | S |
| 1.8 | **No accessibility attributes anywhere** (zero `aria-` / `role=` hits in `public/`). Tiles and card buttons are `<div>`/`<button>` with images and no text alternative. Add `alt` (card name) and `aria-label`; make tiles keyboard-focusable. | P3 | M |
| 1.9 | **DONE** - The zoom lock is scoped to the board. `marvel.html` still ships `user-scalable=0, maximum-scale=1` so a two-finger gesture on the scene stays a camera drag, but `js/marvel/viewport.ts` rewrites the meta to a zoomable one while a panel of text is up — the menu/log (`HistoryLog.toggle`) and the game-over statistics (`Game.setGameOver`) — and restores the lock when the board is back in front. Panels are reference-counted, so closing one does not re-lock while the other is still open. | P3 | S |
| 1.10 | **Main menu has no "Continue".** `AUTO_SAVE_AFTER_GAME_OVER` exists but there is no resume path from `main.html`. Pair with §4.2. | P2 | M |

## 2. Usability

| # | Item | Pri | Eff |
|---|------|-----|-----|
| 2.1 | **DONE** - Stale placeholders were cached for a year. `Cache` now tracks which ids are generated stand-ins (`Cache.IsPlaceholder`) and `server_files.ImageHeaders` serves those with `no-store`, so real art appears on the next load instead of needing a hard refresh. | P1 | S |
| 2.2 | **DONE** - A 404 no longer poisons the disk cache. Generated stand-ins are never written to `assets/cache` (they are indistinguishable from real art there); they are held in memory for the session only. The dead `is_time_out` flag and the `save_empty_image` option are gone. | P1 | S |
| 2.3 | **Missing `assets/` fails silently.** Detect the absence of `assets/textures/sets/` at startup and log a `<W>` plus a banner on `main.html` pointing at install-guide step 6. | P1 | S |
| 2.4 | **Port-in-use crashes with two tracebacks.** `manager.py:44` asserts, then `Engine.SaveCrash` (`engine.py:161`) throws again because `Engine.game` doesn't exist yet. Print a one-line message, guard `SaveCrash` on `Engine.game is None`, and optionally try the next port. | P2 | S |
| 2.5 | **DONE** - A checksum mismatch now says what it means and how to clear it. The first warning of a run carries the explanation (a checksum records what a file held when the game wrote it, so data edited since is reported rather than silently changing every game built from it; nothing is blocked, and editing is supported), and later files just name themselves. `py main.py -rehash` writes the checksums of `sets_info.json`, `cards.json` and any custom card file back. `Json.Rehash` patches only the checksum value into the text the file already has - `Json.Save` would reflow `sets_info.json`, which is hand-formatted, a third bigger. | P3 | S |
| 2.6 | **DONE** - The replay test runner falls back to the config that ships. `unit_test/test_all.py` passes `-config_files launch-debug.json launch.json`, and `FileManager.FindJsonPath` takes the first that exists, so a plain checkout no longer opens with `File ('launch-debug.json',) not found`; a maintainer's own `launch-debug.json` still wins, and it is now in `.gitignore` so it stays personal. These tests still need a `./replays/` corpus, which is not in the repo - the checked-in regression net is `unit_test/cases` (§5.6). | P2 | S |
| 2.7 | **DONE** - The environment switch is live and the shipped default is unchanged. `Build.release` is `EnvFlag("RELEASE") or not EnvFlag("DEBUG")`: a plain `py main.py` is still a release build, `DEBUG=1` opts into the debug build (call and instance trackers, coverage, every assert behind `if not Build.release`), and `RELEASE=1` wins over `DEBUG` so a shell exporting one can still start the other. `0`, `false`, `off`, `no` and empty all read as off. The version banner says which you got (`0.5.9.201r` / `...d`). | P3 | S |
| 2.8 | **DONE** - `.gitignore` carries `/venv/` and `/.venv/` (commit `897098b`), anchored at the repo root, so a local virtualenv no longer shows up in `git status`. Nothing under either path is tracked. §2.6 added `/launch-debug.json` beside them, for the same reason. | P3 | S |
| 2.9 | **Deck picker has no "recent decks".** The New Game form already persists checkboxes in `localStorage` (`CACHE_KEY`); extend that to the last-used scenario and hero files. | P2 | S |
| 2.10 | **Image prefetch command.** Offer `py main.py --prefetch-images` (or a menu button) that walks `sets_info.json` → scenario JSON → villain/hero IDs and fills `assets/cache` with a concurrency limit, so the first session isn't spent waiting on cerebro. | P2 | M |

## 3. Performance

| # | Item | Pri | Eff |
|---|------|-----|-----|
| 3.1 | **DONE** - Serial fetches on the New Game screen. `createScenarios()` and `createSets()` awaited one request per button, ~278 round-trips back to back. Both now warm a memo in a single `Promise.all` burst; measured 658ms -> 89ms on loopback, and the gain scales with latency. Also fixed the load-order race this exposed (see 3.1a). | P1 | S |
| 3.1a | **DONE** - Latent load-order race, exposed by 3.1. The Weekly Challenges tile reveals checkbox labels built by a deferred `<script type="module">`; nothing ordered the two, and the tile only worked because it was blocked behind ~160 serial fetches. Once those went parallel it hit `getElementById(...).parentElement` on `null`, killing tile construction and `createSets()` entirely. Replaced with an explicit `challenge_ui_ready` promise handshake plus a null guard. | P1 | S |
| 3.2 | **Image downloads block request handlers.** `Cache.LoadImage` calls `requests.get` with a 3 s timeout per server, inside `TaskManager.ToThread`; on a cold cache each tile image is a synchronous remote fetch. Combine with §2.10 and add a small thread pool so misses are fetched in parallel. | P1 | M |
| 3.3 | **Unbounded in-memory image cache.** `Cache.cache` is a plain dict holding every JPEG served (154 MB on disk after one New Game screen load, all of it also resident in RAM). Replace with an LRU (`functools.lru_cache` sized by bytes, or `cachetools.LRUCache`) or serve files via `web.FileResponse` and let the OS page cache do the work. | P2 | S |
| 3.4 | **Every first load decodes through PIL.** `TryRotateImage` opens each image with Pillow just to check orientation, even when no rotation is needed. Persist the already-rotated result to `assets/cache` once and skip PIL on later loads. | P3 | S |
| 3.5 | **Set tile art is re-encoded to JPEG** from `.webp` on the fly (same path as 3.4). Serve `.webp` bytes with the correct `Content-Type` when no rotation is required. | P3 | S |

## 4. Playability

| # | Item | Pri | Eff |
|---|------|-----|-----|
| 4.1 | **Random hero / random scenario.** `random_modular()` exists for modulars; add "Random hero" and "Random scenario" buttons for quick solo games. The gallery half of this item shipped with §1.4, so the buttons now have a list to pick from. | P2 | S |
| 4.2 | **Autosave & resume.** `GameSession.SaveScene` and `LoadScene` (`game_run/game_session.py`) already exist; autosave at each villain-phase end and expose "Continue last game" on the main menu. | P1 | M |
| 4.3 | **Surface undo depth.** `GameSession.Undo(n)` (`game_session.py:194`) is implemented server-side. If the client only exposes single-step undo, add an undo-N control with a short history list. | P2 | S |
| 4.4 | **Campaign mode beyond Red Skull.** `mode_campaign` is gated to "The Rise of Red Skull". The Galaxy's Most Wanted, Mad Titan's Shadow, Sinister Motives, Mutant Genesis, NeXt Evolution, Age of Apocalypse and Civil War sets are all present; extend the campaign log to them one box at a time. | P2 | L |
| 4.5 | **Per-scenario win record on tiles.** `/get_completion_rate` and `game/rule/statistics.py` exist; show wins/plays and best hero on each scenario button. | P3 | S |
| 4.6 | **DONE** - A **How to Play** page now ships in the app (`public/tutorial.html`, routed at `/tutorial`, linked from the main menu): rules primer, the round structure, and this build's actual controls. Its **Start the guided game** button builds the same payload the New Game screen posts, pre-filled with Core Set Rhino + the Spider-Man starter deck, and opens the board with `?tutorial`. There, `public/js/marvel/tutorial.ts` watches each world render and shows 14 contextual hints — mulligan, alter-ego vs hero form, paying costs, the threat clock (with live numbers), the four villain-phase steps, engaged minions, Rhino advancing, and a closing hint that explains the win or loss — each fired by game state rather than a fixed script, so the player is never blocked or led. | P2 | L |
| 4.7 | **Fill the scenario gaps.** Missing files: `god_of_lies` (+ expert), `iron_man_expert`, `captain_marvel_expert`, `captain_america_expert`, `spider_woman_expert` (Civil War), `2425_boss_rush`, and `age_of_apocalypse_WIP.json` is still WIP. | P2 | M |
| 4.8 | **Timeout slider defaults to disabled** with no explanation of when it applies (online only). Add helper text. | P3 | S |

## 5. Rules fidelity

| # | Item | Pri | Eff |
|---|------|-----|-----|
| 5.1 | **RRG version selector instead of seven checkboxes.** The `v16_*` toggles (`scene.html:803-810`) are correct but unfamiliar to new players. Offer a single "Rules: RRG 1.6 (current) / 1.5" selector that sets them as a group, with the checkboxes under an "Advanced" disclosure. Default to 1.6. | P2 | S |
| 5.2 | **"Pre message" hooks are missing across the message senders.** Fourteen `# TODO: Pre message` markers in `game/message/sender/sender_{card,player,scheme,damage,deck}.py` mean there is no "would" event before those actions, so cancel/replace/prevent effects can't intercept them. This is the single largest source of subtle card-interaction bugs. | P1 | L |
| 5.3 | **Known rule gaps flagged in card scripts** (search `TODO` under `cards/pack/`): Klaw *Sonic Boom* must-choose-a-fulfillable-option (`core/klaw/01123.py`), Kang stage completes when all players at a stage are defeated (`toafk/kang/__init__.py:146`), Doctor Strange 09020 "take no damage" timing, Mojo *Magog* win-condition (`mojo/magog/39002b.py`), Civil War enemy-team choice and "your leader" (`cw/hells_kitchen/56191.py`, `cw/dangerous_recruits/56090.py`), *Return the Favor* cancel interaction (`ability/cost_func.py:1035`), Angel 42008 reuse after gaining 28012. | P2 | M each |
| 5.4 | **Obligation ownership isn't enforced.** `game/card/face/card_type/obligation.py:9` notes that only the player holding an obligation may trigger its abilities or pay its costs; that restriction isn't implemented yet, so other players can currently interact with it. | P2 | S |
| 5.5 | **Face-up cards in the encounter deck** aren't included by `Find` (`operate/find.py:134` is a commented-out `faces=` parameter), so any effect that searches or counts face-up encounter cards misses them. | P3 | M |
| 5.6 | **DONE** - Scripted regression cases now exist. A case (`unit_test/cases/`) is a recipe - scenario, heroes, seed, rules - plus the replay it recorded (the game's own format, openable in the replay viewer) plus the end state it reached; checking one replays the fixed input list, which validates the board CRC carried by every input, and then compares the end state. Recording is done by an auto-player (`game/test/auto_player.py`) driving a new headless device (`-device scripted`), so cases are generated rather than hand-written. Seven Core Set cases ship, they run in ~2s with no `assets/` folder, and `.github/workflows/rules_regression.yml` runs them on every push and PR touching `cards/`, `game/`, `engine/`, `core/` or `data/`. See `docs/testing_guide.md`. | P1 | M |

## 6. Suggested order

1. ~~§2.1, §2.2, §1.2, §3.1~~ — **done** (plus §3.1a, a latent race the speedup uncovered).
2. ~~§1.3, §1.4~~ — **done** (progress bar, hero gallery); §4.2 — resume.
3. ~~§5.6~~ — **done** (the regression net); §5.2 is now safe to start, and every step of it should be run against `python -m unittest unit_test.test_scripted`.
4. §4.4 — the remaining large playability investment (~~§4.6~~ **done**).

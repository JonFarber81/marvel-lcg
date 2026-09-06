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
| 1.3 | **No loading state on the New Game screen.** `createScenarios()` populates tiles as ~164 sequential fetches complete; on a cold cache the page sits mostly empty for tens of seconds with no spinner. Add a progress bar keyed off the fetch count. | P1 | S |
| 1.4 | **Hero slots are raw `<input type="file">` controls** ("No file chosen" ×4). Replace with a portrait gallery populated from the existing `/list_starter_deck` and `/list_deck` endpoints; keep the file picker as an "Import…" fallback. | P1 | M |
| 1.5 | **Orange counters like `(2/4)` are unexplained.** Sets 55, 56 and Weekly Challenges are missing scenario files (see §5.3). Add a tooltip listing which scenarios are unavailable and why. | P2 | S |
| 1.6 | **Modular sets are hidden behind "Expand"** with no summary of what's currently selected. Show the selected count and names inline in the fieldset legend. | P2 | S |
| 1.7 | **Version-mismatch page is returned to `fetch()` callers.** `web_server.py:IsVersionMatch` returns HTML for every route, so an API call fails with `JSON.parse` errors in the console instead of a clear message. Return `409 {"error": "version_mismatch"}` when `Accept: application/json` or `X-Requested-With` is present and let the page reload itself. | P2 | S |
| 1.8 | **No accessibility attributes anywhere** (zero `aria-` / `role=` hits in `public/`). Tiles and card buttons are `<div>`/`<button>` with images and no text alternative. Add `alt` (card name) and `aria-label`; make tiles keyboard-focusable. | P3 | M |
| 1.9 | **Viewport locks zoom** (`marvel.html:64` `user-scalable=0, maximum-scale=1`). Fine for the board, but it also applies to menus. Scope it to the game page only. | P3 | S |
| 1.10 | **Main menu has no "Continue".** `AUTO_SAVE_AFTER_GAME_OVER` exists but there is no resume path from `main.html`. Pair with §4.2. | P2 | M |

## 2. Usability

| # | Item | Pri | Eff |
|---|------|-----|-----|
| 2.1 | **DONE** - Stale placeholders were cached for a year. `Cache` now tracks which ids are generated stand-ins (`Cache.IsPlaceholder`) and `server_files.ImageHeaders` serves those with `no-store`, so real art appears on the next load instead of needing a hard refresh. | P1 | S |
| 2.2 | **DONE** - A 404 no longer poisons the disk cache. Generated stand-ins are never written to `assets/cache` (they are indistinguishable from real art there); they are held in memory for the session only. The dead `is_time_out` flag and the `save_empty_image` option are gone. | P1 | S |
| 2.3 | **Missing `assets/` fails silently.** Detect the absence of `assets/textures/sets/` at startup and log a `<W>` plus a banner on `main.html` pointing at install-guide step 6. | P1 | S |
| 2.4 | **Port-in-use crashes with two tracebacks.** `manager.py:44` asserts, then `Engine.SaveCrash` (`engine.py:161`) throws again because `Engine.game` doesn't exist yet. Print a one-line message, guard `SaveCrash` on `Engine.game is None`, and optionally try the next port. | P2 | S |
| 2.5 | **`Checksum mismatch` warnings on `cards.json` / `sets_info.json`** appear on every start. Explain in the log what the checksum protects and provide a `--rehash` flag (or a build step) that regenerates it. | P3 | S |
| 2.6 | **Test runner references `launch-debug.json`** (`unit_test/test_all.py`) which is not in the repo. Add it, or fall back to `launch.json`. | P2 | S |
| 2.7 | **`Build.release` is hard-coded `True`** right after the `"RELEASE" in os.environ` check (`build.py`), so the env switch is dead code. | P3 | S |
| 2.8 | **`venv/` is untracked but not ignored.** Add `venv/` and `.venv/` to `.gitignore`. | P3 | S |
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
| 4.1 | **Hero gallery + random hero.** `random_modular()` exists for modulars; add "Random hero" and "Random scenario" buttons for quick solo games. | P2 | S |
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
| 5.6 | **Automated rules regression.** Only four files under `unit_test/`. Add a scripted-scenario harness (seed + input list → expected end state) using the existing replay format, and run it in CI on every card-pack change. | P1 | M |

## 6. Suggested order

1. ~~§2.1, §2.2, §1.2, §3.1~~ — **done** (plus §3.1a, a latent race the speedup uncovered).
2. §1.3, §1.4, §4.2 — first-session experience: progress, hero gallery, resume.
3. §5.6 then §5.2 — get a regression net in place before touching the message pipeline.
4. §4.4 — the remaining large playability investment (~~§4.6~~ **done**).

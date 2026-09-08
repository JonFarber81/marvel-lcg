/* ═══════════════════════════════════════════════════════════════════════════
   view.ts — the gameplay screen's presentation layer.

   The existing client keeps its state in the DOM: `Effect` and `SelectStep`
   read selections back out of `.card` classes, `Button.doPost` reads the
   cost step out of `dataset.pay_effect_id`, `Replay` reads the OK button's
   own `disabled` flag. So this module does not replace any of that. It:

     · lays the client's own card containers out as a board — one lane per
       zone, one seat per hero, in normal flow instead of absolute transforms;
     · reads `Game.world_descriptor` after each render and paints the things
       the old screen never showed at all: the round, the phase, each hero's
       health and hand, and the two clocks the game is actually a race
       between;
     · mirrors the legacy chrome — `#prompt-text`, `#btn-ok`, `#btn-end` —
       into the dock, and forwards clicks back to it.

   Everything the engine drives (highlighting, animation, the cost solver,
   the ask flow) is untouched and keeps working.
   ═══════════════════════════════════════════════════════════════════════ */

import { Game } from './game.js'
import { Cards } from './cards.js'
import { Effect } from './effect.js'
import { Button } from './buttons.js'
import { UI } from './ui.js'
import { Setting } from './settings.js'
import { HistoryLog } from './history.js'

type Card = any

const SEAT_COLOURS = ['var(--s0)', 'var(--s1)', 'var(--s2)', 'var(--s3)']

function el(tag: string, cls?: string): HTMLElement {
    const n = document.createElement(tag)
    if (cls) n.className = cls
    return n
}
function q<T extends HTMLElement>(sel: string): T | null {
    return document.querySelector<T>(sel)
}

export class View {
    static built_seats = -1
    /* `info.health` is the health a card has left; the printed maximum is not
       always sent. It is however always what the card had the first time we
       saw it, so the high-water mark is the max. */
    static max_health: { [object_id: number]: number } = {}
    static max_threat: { [object_id: number]: number } = {}

    // ── Setup ───────────────────────────────────────────────────────────
    static init() {
        // The client hard-binds to `#option-buttons` at module load, so it is
        // moved into the dock rather than rebuilt there.
        const opts = q('#option-buttons')
        const slot = q('#opts-slot')
        if (opts && slot) slot.appendChild(opts)

        View.wireActs()
        View.wireTools()
        View.wireSheet()
        View.observeLegacy()
        ;(window as any).PlayView = View
    }

    /* Runs before each render so the containers the client is about to query
       exist. Player count is only known once a world has arrived. */
    static beforeRender() {
        const world = Game.world_descriptor as any
        if (!world || !world.players) return
        if (world.players.length !== View.built_seats) View.buildSeats(world.players.length)
    }

    static buildSeats(n: number) {
        View.built_seats = n
        document.documentElement.dataset.seats = String(n)

        // Engaged enemies, grouped by the hero they are engaged with. One
        // small lane per seat under that hero's name, in that hero's colour,
        // so the row needs no arrows and no second row.
        const engaged = q('#engaged')!
        engaged.textContent = ''
        for (let i = 0; i < n; i++) {
            const cell = el('div', 'engaged-seat')
            cell.style.setProperty('--s', SEAT_COLOURS[i])
            const name = el('span', 'engaged-name')
            name.id = `engaged-name-${i}`
            cell.appendChild(name)
            const lane = el('div', 'lane sm area area-center')
            lane.id = `player-${i}-engaged-minions`
            lane.dataset.empty = 'None'
            cell.appendChild(lane)
            engaged.appendChild(cell)
        }

        const mine = q('#mine')!
        mine.textContent = ''
        const piles = q('#piles')!
        piles.textContent = ''
        const hands = q('#hands')!
        hands.textContent = ''

        for (let i = 0; i < n; i++) {
            // ── The seat's board ──
            const seat = el('section', 'seat')
            seat.id = `seat-${i}`
            seat.dataset.seat = String(i)
            seat.style.setProperty('--s', SEAT_COLOURS[i])

            const lanes = el('div', 'seat-lanes')
            lanes.appendChild(View.zone('Identity', `player-${i}-area-hero`, 'attached', '—'))
            lanes.appendChild(View.zone('Allies', `player-${i}-allies`, '', 'No allies'))
            const sup = View.zone('Supports', `player-${i}-supports`, '', 'None in play')
            sup.classList.add('grow')
            lanes.appendChild(sup)
            seat.appendChild(lanes)

            // ── The nameplate ──
            const plate = el('div', 'plate')
            plate.innerHTML =
                `<span class="plate-name" id="plate-name-${i}"></span>` +
                `<span class="plate-form" id="plate-form-${i}"></span>` +
                `<span class="plate-hp mono" id="plate-hp-${i}"></span>` +
                `<span class="plate-meta" id="plate-meta-${i}"></span>` +
                `<span class="plate-first" id="plate-first-${i}" hidden>First</span>` +
                `<span class="plate-res" id="plate-res-${i}"></span>`
            seat.appendChild(plate)
            mine.appendChild(seat)

            // ── That seat's piles and hand, in the dock ──
            const pile = el('div', 'seat-piles')
            pile.dataset.seat = String(i)
            pile.appendChild(View.stack(`player-${i}-player-deck`, 'Deck', false))
            pile.appendChild(View.stack(`player-${i}-player-discard-pile`, 'Discard', false))
            piles.appendChild(pile)

            const hand = el('div', 'hand-slot')
            hand.dataset.seat = String(i)
            const lane = el('div', 'area area-center')
            lane.id = `player-${i}-hand-cards`
            hand.appendChild(lane)
            hands.appendChild(hand)
        }
    }

    static zone(label: string, id: string, laneClass: string, empty: string): HTMLElement {
        const z = el('div', 'zone')
        const head = el('div', 'zone-head')
        const e = el('span', 'eyebrow')
        e.textContent = label
        head.appendChild(e)
        z.appendChild(head)
        const lane = el('div', 'lane area area-center' + (laneClass ? ' ' + laneClass : ''))
        lane.id = id
        lane.dataset.empty = empty
        z.appendChild(lane)
        return z
    }

    /* A pile is one box with a count. The client keeps putting real card divs
       inside it; CSS shows only the top one, dimmed, behind the number — so
       "what just hit me" needs no click. */
    static stack(id: string, label: string, encounter: boolean): HTMLElement {
        const s = el('button', 'stack' + (encounter ? ' enc' : ''))
        s.id = `stack-${id}`
        const deck = el('div', 'deck')
        deck.id = id
        s.appendChild(deck)
        const lab = el('div', 'stack-label')
        lab.innerHTML = `<span class="stack-n mono" id="n-${id}">0</span>` +
                        `<span class="stack-l">${label}</span>`
        s.appendChild(lab)
        return s
    }

    // ── Chrome that proxies the client's own buttons ─────────────────────
    static wireActs() {
        q('#a-go')!.addEventListener('click', () => {
            // "Pause on reveal" stops the game to show you the encounter card
            // it just turned over, and the only way on was the Escape key.
            // The button is the way on.
            if ((Game as any).is_pause) { Button.togglePause(); return }
            const ok = q<HTMLButtonElement>('#btn-ok')!
            const end = q<HTMLButtonElement>('#btn-end')!
            if (!ok.disabled) Button.doBtnOk()
            else if (!end.disabled) Button.doBtnCancel()
        })
        q('#a-cancel')!.addEventListener('click', () => Button.doBtnCancel())
    }

    static wireTools() {
        q('#t-log')!.addEventListener('click', () => View.toggleSheet('log'))
        q('#t-set')!.addEventListener('click', () => View.toggleSheet('set'))
        q('#t-undo')!.addEventListener('click', () => Button.doUndo())
        q('#sheet-x')!.addEventListener('click', () => View.closeSheet())
        q('#scrim')!.addEventListener('click', () => View.closeSheet())
        q('#tab-log')!.addEventListener('click', () => View.openSheet('log'))
        q('#tab-set')!.addEventListener('click', () => View.openSheet('set'))
    }

    /* The log used to be on Tab, which costs you keyboard navigation for the
       whole board. It is on L instead; the client's own Tab handler is left
       alone but lands on a panel that is already there. */
    static wireSheet() {
        document.addEventListener('keydown', (e) => {
            if (e.metaKey || e.ctrlKey || e.altKey) return
            if (e.key === 'Enter' && (Game as any).is_pause) {
                e.preventDefault(); Button.togglePause(); return
            }
            if (e.key === 'l' || e.key === 'L') {
                const t = e.target as HTMLElement
                if (t && /^(INPUT|TEXTAREA)$/.test(t.tagName)) return
                View.toggleSheet('log')
            }
        })
    }
    static openSheet(which: string) {
        q('#tab-log')!.setAttribute('aria-selected', String(which === 'log'))
        q('#tab-set')!.setAttribute('aria-selected', String(which === 'set'))
        q('#pane-log')!.hidden = which !== 'log'
        q('#pane-set')!.hidden = which !== 'set'
        q('#sheet')!.classList.add('on')
        q('#scrim')!.classList.add('on')
        if (which === 'log') {
            const t = q('#history-text')
            if (t) t.scrollTop = t.scrollHeight
        }
    }
    static closeSheet() {
        q('#sheet')!.classList.remove('on')
        q('#scrim')!.classList.remove('on')
    }
    static toggleSheet(which: string) {
        const open = q('#sheet')!.classList.contains('on')
        const cur = q('#tab-log')!.getAttribute('aria-selected') === 'true' ? 'log' : 'set'
        if (open && cur === which) View.closeSheet()
        else View.openSheet(which)
    }

    /* The client rewrites `#prompt-text` and the two buttons whenever the
       selection step changes, which is not always on a render. Watching them
       keeps the dock in step without touching their code. */
    static observeLegacy() {
        const sync = () => View.syncAsk()
        const obs = new MutationObserver(sync)
        for (const sel of ['#prompt-text', '#btn-ok', '#btn-end']) {
            const n = q(sel)
            if (n) obs.observe(n, { attributes: true, childList: true, subtree: true, characterData: true })
        }
    }

    // ── Painting ────────────────────────────────────────────────────────
    static update() {
        const world = Game.world_descriptor as any
        if (!world || !world.players) return
        // The client calls this from inside its render. Anything that throws
        // here would abort that render and leave the board frozen, so the
        // view fails quietly and the game carries on without it.
        try {
            View.paintFront(world)
            View.paintSeats(world)
            View.paintStacks(world)
            View.decorate()
            View.syncAsk()
        } catch (err) {
            console.error('play view: update failed', err)
        }
    }

    static beforeRenderSafe() {
        try { View.beforeRender() } catch (err) { console.error('play view: build failed', err) }
    }

    static activeSeat(): number {
        // Clamped against the world in hand, not against however many seats
        // were built last time: `focusOnPlayer` can render while the two
        // disagree, and reading past the end of `players` threw out of the
        // whole render.
        const world = Game.world_descriptor as any
        const total = world && world.players ? world.players.length : 0
        const p = (Game as any).forced_on_player
        if (typeof p === 'number' && p >= 0 && p < total) return p
        return 0
    }

    /* The identity card is the one card in a player's hero area that is a
       Hero or an AlterEgo; everything else there is an upgrade, a status
       card or a dealt encounter card. */
    static identity(player: any): Card | null {
        if (!player) return null
        for (const c of player.area_hero || []) {
            if (c.card_type === 'Hero' || c.card_type === 'AlterEgo') return c
        }
        return null
    }

    static info(card: Card): { [k: string]: number } {
        return (card && card.info) || {}
    }

    static maxOf(store: { [id: number]: number }, card: Card, key: string, printed?: string): number {
        const info = View.info(card)
        const cur = Number(info[key] || 0)
        if (printed && info[printed]) return Number(info[printed])
        const id = card.object_id != null ? card.object_id : card.id
        const seen = store[id] || 0
        const max = Math.max(seen, cur)
        store[id] = max
        return max
    }

    /* ── The front line ──────────────────────────────────────────────────
       The two clocks the game is a race between, drawn as the divider
       itself: the table's damage running in from the left, the scheme's
       threat running in from the right, and the centre as the finish. */
    static paintFront(world: any) {
        const front = q('#front')!
        const villain = (world.area_villain || [])[0]
        const scheme = (world.area_schemes_main || [])[0]

        // ── Left: the villain ──
        if (villain) {
            const info = View.info(villain)
            const left = Number(info.health || 0)
            const max = View.maxOf(View.max_health, villain, 'health', 'k_health')
            const stage = Number(info.printed_stage || 1)
            const remaining = (world.villain_deck || []).length
            const stages = stage + remaining

            q('#f-vname')!.textContent = villain.name + (stages > 1 ? ' ' + roman(stage) : '')
            q('#f-vnum')!.textContent = left + ' HP left'
            const bits = []
            if (info.attack != null) bits.push('ATK ' + info.attack)
            if (info.scheme != null) bits.push('SCH ' + info.scheme)
            if (stages > 1) bits.push('STAGE ' + stage + ' OF ' + stages)
            q('#f-vsub')!.textContent = bits.join(' · ')

            // Stages already broken through stay behind you, spent, so the
            // bar says "second of three" without a caption.
            const track = q('#f-vtrack')!
            track.textContent = ''
            const per = 100 / stages
            const done = el('i')
            done.className = 'done'
            done.style.setProperty('--p', (per * (stage - 1)) + '%')
            track.appendChild(done)
            const now = el('i')
            now.className = 'now'
            now.style.setProperty('--from', (per * (stage - 1)) + '%')
            now.style.setProperty('--w', (max ? per * (max - left) / max : 0) + '%')
            track.appendChild(now)
            for (let i = 1; i < stages; i++) {
                const b = el('b')
                b.style.setProperty('--at', (per * i) + '%')
                track.appendChild(b)
            }
        }

        // ── Right: the scheme ──
        if (scheme) {
            const info = View.info(scheme)
            const threat = Number(info.threat != null ? info.threat : info.k_threat || 0)
            const target = Number(info.target_threat || 0)
            const accel = Number(info.escalation_threat || 0)

            q('#f-sname')!.textContent = scheme.name
            q('#f-snum')!.textContent = target ? threat + ' of ' + target : String(threat)
            q('#f-ssub')!.textContent = accel
                ? 'Accelerates +' + accel + ' each round'
                : ''

            const track = q('#f-strack')!
            track.textContent = ''
            const p = target ? Math.min(100, threat / target * 100) : 0
            const f = el('i')
            f.style.setProperty('--p', p + '%')
            track.appendChild(f)
            if (target && accel) {
                // Threat that is coming whatever you do next round.
                const g = el('u')
                g.style.setProperty('--from', p + '%')
                g.style.setProperty('--w', Math.max(0, Math.min(100 - p, accel / target * 100)) + '%')
                track.appendChild(g)
            }
        }

        // ── Centre: the round, and whose turn ──
        q('#f-round')!.textContent = String(world.round_id != null ? world.round_id : 0)
        const phase = String(world.phase || '')
        const villainPhase = /Enemy Activation|Main Scheme Place Threat|Encounter Cards|End Phase|Start Round|End Round/.test(phase)
        let label = PHASE_NAMES[phase] || phase
        const m = phase.match(/^Player (\d+) Turn$/)
        if (m) {
            const seat = Number(m[1]) - 1
            const player = world.players[seat]
            const id = player && View.identity(player)
            label = id ? id.name + "'s turn" : phase
        }
        q('#f-phase')!.textContent = label
        front.classList.toggle('villain-turn', villainPhase)
    }

    /* ── The seats ───────────────────────────────────────────────────── */
    static paintSeats(world: any) {
        const active = View.activeSeat()
        document.documentElement.style.setProperty('--seat', SEAT_COLOURS[active])

        for (let i = 0; i < world.players.length; i++) {
            const player = world.players[i]
            const seat = q(`#seat-${i}`)
            if (!seat) continue
            const id = View.identity(player)
            const info = id ? View.info(id) : {}

            // Lit means "this seat is the one being asked" - on its own turn,
            // and equally when the villain phase stops to ask it something.
            seat.classList.toggle('on', i === active)
            seat.classList.toggle('eliminated', !!player.is_eliminated)

            q(`#plate-name-${i}`)!.textContent = id ? id.name : 'Player ' + (i + 1)
            // Which side is face up decides what the villain does to you, and
            // it is also why the name on the plate is not the name the log
            // uses. Saying so settles both questions at once.
            q(`#plate-form-${i}`)!.textContent =
                id ? (id.card_type === 'AlterEgo' ? 'Alter-ego' : 'Hero') : ''
            const hp = Number(info.health || 0)
            q(`#plate-hp-${i}`)!.textContent = id ? hp + ' HP' : ''
            const size = Number(info.hand_size || 0)
            q(`#plate-meta-${i}`)!.textContent =
                'Hand ' + (player.hand_cards || []).length + (size ? ' of ' + size : '')
            q(`#plate-first-${i}`)!.hidden = Number(info.k_first_player_token || 0) !== 1

            // The pool this hero has already put down, while paying.
            const res = q(`#plate-res-${i}`)!
            res.textContent = ''
            for (const c of String(player.resources || '')) {
                const d = el('div', 'res-' + c.toLowerCase())
                res.appendChild(d)
            }

            const name = q(`#engaged-name-${i}`)
            if (name) name.textContent = id ? shortName(id.name) : 'P' + (i + 1)
        }

        // The dock wears the acting hero's colour, and says whose hand it is.
        const active_id = View.identity(world.players[active])
        const who = q('#hand-who')
        if (who) who.textContent = active_id ? active_id.name : 'Player ' + (active + 1)
        const count = q('#n-hand')
        if (count) {
            const p = world.players[active]
            const size = active_id ? Number(View.info(active_id).hand_size || 0) : 0
            count.textContent = (p.hand_cards || []).length + (size ? ' of ' + size : '')
        }

        View.paintReady(world, active)
    }

    /* Forgetting a character who had not acted yet is the commonest way to
       lose, and twice as easy with two hands. */
    static paintReady(world: any, active: number) {
        const row = q('#ready')!
        row.textContent = ''
        row.className = 'ready'
        row.hidden = !/^Player \d+ Turn$/.test(String(world.phase || ''))
        const player = world.players[active]
        if (!player || row.hidden) return
        const names: string[] = []
        const CAN_ACT = /^(Hero|AlterEgo|Ally|Support)$/
        const consider = (list: Card[]) => {
            for (const c of list || []) {
                // Attachments and status cards are not people; upgrades are
                // read off whoever they are attached to.
                if (c.bind_object_id) continue
                if (!CAN_ACT.test(c.card_type)) continue
                if (c.is_ready === false) continue
                names.push(c.name)
            }
        }
        consider(player.area_hero)
        consider(player.allies)
        consider(player.supports)
        if (!names.length) {
            row.classList.add('none')
            row.textContent = 'Everything has acted this turn.'
            return
        }
        const b = el('b')
        b.textContent = 'Ready'
        row.appendChild(b)
        for (const n of names) {
            const s = el('span')
            s.textContent = n
            row.appendChild(s)
        }
    }

    /* ── The piles ───────────────────────────────────────────────────── */
    static paintStacks(world: any) {
        const set = (id: string, n: number) => {
            const t = q(`#n-${id}`)
            if (t) t.textContent = String(n)
            const s = q(`#stack-${id}`)
            if (s) s.classList.toggle('out', !n)
        }
        set('encounter-deck-0', (world.encounter_deck || []).length)
        set('encounter-discard-pile-0', (world.encounter_discard_pile || []).length)
        for (let i = 0; i < world.players.length; i++) {
            set(`player-${i}-player-deck`, (world.players[i].player_deck || []).length)
            set(`player-${i}-player-discard-pile`, (world.players[i].player_discard_pile || []).length)
        }
        // A deck is face down; a discard shows its top card.
        const deckStack = q('#stack-encounter-deck-0')
        if (deckStack) deckStack.classList.add('facedown')
        for (let i = 0; i < world.players.length; i++) {
            const s = q(`#stack-player-${i}-player-deck`)
            if (s) s.classList.add('facedown')
        }
    }

    /* ── The card edges ─────────────────────────────────────────────────
       The client draws every number across the face of the card. Those are
       hidden by the stylesheet; the same numbers are read back off the
       descriptor and put on the edges instead — what a card can still take
       along the bottom, what has been done to it along the top. */
    static decorate() {
        const cards = document.querySelectorAll<HTMLElement>('.card')
        for (const div of cards) {
            const id = Number(div.dataset.id)
            const card: Card = Cards.getCard(id)
            if (!card) continue
            const info = View.info(card)
            const inPlay = Object.keys(info).length > 0

            div.classList.toggle('is-new', !!card.is_new)
            // Upgrades, attachments and status cards are tucked under their
            // host, so they are drawn a size down from it.
            div.classList.toggle('bound', !!card.bind_object_id)

            const inHand = !!div.closest('.hand-slot')
            if (inHand && card.cost != null) {
                let bind = div.querySelector<HTMLElement>('.bind-image-info')
                if (!bind) {
                    bind = el('div', 'bind-image-info')
                    const image = div.querySelector('.image')
                    if (image) image.appendChild(bind)
                    else div.appendChild(bind)
                }
                bind.dataset.cost = String(card.cost)
            }

            // Health, for anything that has any.
            let tag = div.querySelector<HTMLElement>('.edge-tag')
            let meter = div.querySelector<HTMLElement>('.edge-meter')
            const isUnit = card.card_type_base === 'Unit' ||
                /^(Hero|AlterEgo|Ally|Minion|EncounterVillain|Leader)$/.test(card.card_type)
            const isScheme = card.card_type_base === 'Scheme' ||
                /Scheme$/.test(card.card_type)

            let value = ''
            let pct = -1
            let mine = false
            if (inPlay && isUnit && info.health != null && !info.is_infinite_health) {
                const max = View.maxOf(View.max_health, card, 'health', 'k_health')
                value = `${info.health}<em>HP</em>`
                pct = max ? Number(info.health) / max * 100 : 100
                mine = card.card_type === 'Hero' || card.card_type === 'AlterEgo' || card.card_type === 'Ally'
            } else if (inPlay && isScheme) {
                const threat = Number(info.threat != null ? info.threat : info.k_threat || 0)
                const target = Number(info.target_threat || 0)
                value = target ? `${threat}<em>/${target}</em>` : `${threat}<em>THR</em>`
                pct = target ? Math.min(100, threat / target * 100) : 0
            }

            if (value) {
                if (!tag) {
                    tag = el('span', 'edge-tag mono')
                    div.appendChild(tag)
                }
                tag.className = 'edge-tag mono ' + (isScheme ? 'thr' : mine ? 'mine' : 'hp')
                tag.innerHTML = value
                if (!meter) {
                    meter = el('div', 'edge-meter')
                    meter.appendChild(el('i'))
                    div.appendChild(meter)
                }
                const fill = meter.firstElementChild as HTMLElement
                fill.style.setProperty('--p', Math.max(0, pct) + '%')
                fill.style.setProperty('--mc', isScheme ? 'var(--threat)'
                    : mine ? 'var(--s, var(--seat))' : 'var(--threat)')
            } else {
                if (tag) tag.remove()
                if (meter) meter.remove()
            }

            // What has been done to it, above the card, never on it.
            const pips: string[] = []
            if (inPlay) {
                if (info.stunned) pips.push('stunned')
                if (info.confused) pips.push('confused')
                if (info.toughness) pips.push('tough')
                if (info.guard) pips.push('guard')
                if (info.retaliate) pips.push('retaliate')
            }
            let row = div.querySelector<HTMLElement>('.edge-pips')
            if (pips.length) {
                if (!row) {
                    row = el('div', 'edge-pips')
                    div.appendChild(row)
                }
                if (row.dataset.k !== pips.join()) {
                    row.dataset.k = pips.join()
                    row.textContent = ''
                    for (const p of pips) {
                        const s = el('span', 'edge-pip ' + p)
                        s.textContent = p === 'tough' ? 'Tough' : p[0].toUpperCase() + p.slice(1)
                        row.appendChild(s)
                    }
                }
            } else if (row) row.remove()
        }
    }

    /* ── The dock's ask ──────────────────────────────────────────────────
       The prompt and the two buttons are the client's; this only shows them
       where your hands already are, and in words that say what will happen. */
    static syncAsk() {
        const prompt = q('#prompt-text')
        const ok = q<HTMLButtonElement>('#btn-ok')
        const end = q<HTMLButtonElement>('#btn-end')
        const go = q<HTMLButtonElement>('#a-go')
        const cancel = q<HTMLButtonElement>('#a-cancel')
        if (!ok || !end || !go || !cancel) return

        const text = q('#ask-text')!
        text.innerHTML = '<span>' + (prompt ? prompt.innerHTML : '') + '</span>'

        const world = Game.world_descriptor as any
        const villainPhase = world && /Enemy Activation|Main Scheme Place Threat|Encounter Cards/
            .test(String(world.phase || ''))
        q('#ask')!.classList.toggle('enemy', !!villainPhase)

        const endText = clean(end.innerHTML)
        const endHidden = end.classList.contains('forced_action') || end.disabled

        // Paused holding a revealed card in front of you: nothing else on
        // screen can be pressed, so the button offers the only move there is.
        if ((Game as any).is_pause) {
            go.disabled = false
            go.innerHTML = label('Continue') + '<kbd>Enter</kbd>'
            cancel.hidden = true
            q('#pay')!.hidden = true
            return
        }

        // Paying a cost is counting to a number, so the dock counts it out.
        // The client's own readout writes the paid resources as icon glyphs;
        // these pips say the same thing in a form that survives at a glance.
        const cost = View.costState()
        const pay = q('#pay')!
        pay.hidden = !cost
        if (cost) {
            q('#pay-l')!.textContent = 'Pay ' + cost.need
            const pips = q('#pay-pips')!
            pips.textContent = ''
            for (let i = 0; i < cost.need; i++) {
                const p = el('i')
                if (i < cost.paid) p.className = 'on'
                pips.appendChild(p)
            }
        }

        // The affirmative action, in the words of the thing it will do.
        if (!ok.disabled) {
            go.disabled = false
            go.innerHTML = label(clean(ok.innerHTML) === 'Over Pay' ? 'Overpay' : primaryName())
                + '<kbd>Enter</kbd>'
        } else if (!end.disabled && /^End/.test(endText)) {
            go.disabled = false
            go.innerHTML = label(endText.replace(/^End\s*/, 'End ').toLowerCase()
                .replace(/^end /, 'End ')) + '<kbd>Enter</kbd>'
        } else if (cost) {
            go.disabled = true
            const left = cost.need - cost.paid
            go.innerHTML = label('Spend ' + left + ' more')
        } else {
            // Whatever the engine is waiting for, the button names it. It used
            // to say "Choose an action" for every one of these, which is true
            // of nothing in particular.
            go.disabled = true
            const need = View.targetsWanted()
            go.innerHTML = label(need
                ? (need === 1 ? 'Choose a target' : 'Choose ' + need + ' targets')
                : waitingLabel())
        }

        // Cancel is only offered when the client is actually offering it.
        const isCancel = !endHidden && /^Cancel/.test(endText)
        cancel.hidden = !isCancel
        if (isCancel) cancel.innerHTML = label('Cancel') + '<kbd>Esc</kbd>'
    }

    /* How many more targets this ask still wants, or 0 when it is not asking
       for any. */
    static targetsWanted(): number {
        if (!document.querySelector('.card.highlight-targets')) return 0
        const obj: any = (Effect as any).select_effect_obj
        if (!obj || !obj.target_num_range) return 1
        const min = Number(obj.target_num_range[0] || 0)
        const have = (obj.selected_targets || []).length
        return Math.max(0, min - have) || (have ? 0 : 1)
    }

    /* How much this costs and how much is down, or null when nothing is being
       paid for. A digit in the cost string is that many generic resources; a
       letter is one of that type. */
    static costState(): { need: number, paid: number } | null {
        const obj: any = (Effect as any).select_effect_obj
        if (!obj || typeof obj.getCost !== 'function') return null
        const end = q<HTMLButtonElement>('#btn-end')
        if (!end || !/Cancel\s*Pay/i.test(clean(end.innerHTML))) return null
        let need = 0
        for (const ch of String(obj.getCost() || '')) {
            if (ch >= '0' && ch <= '9') need += Number(ch)
            else if (/[RBYG]/.test(ch)) need += 1
        }
        if (!need) return null
        return { need, paid: (obj.resources || []).length }
    }
}

// ── helpers ─────────────────────────────────────────────────────────────
function clean(html: string): string {
    return html.replace(/<br\s*\/?>/gi, ' ').replace(/\s+/g, ' ').trim()
}
function label(t: string): string {
    return t.replace(/[<>]/g, '')
}
/* While a target or a cost is being chosen, the button says the name of the
   ability it will resolve — "Attack", "Thwart", "Play" — rather than "OK". */
function primaryName(): string {
    const obj: any = (Effect as any).select_effect_obj
    const name = obj && obj.name_with_space ? String(obj.name_with_space) : ''
    if (!name || name === 'undefined') return 'Confirm'
    if (/^p_/.test(name) || /</.test(name)) return 'Confirm'
    return name
}
function waitingLabel(): string {
    const world = Game.world_descriptor as any
    if (!world) return 'Waiting'
    if (/Enemy Activation|Main Scheme Place Threat|Encounter Cards/.test(String(world.phase || '')))
        return 'Villain is acting'
    return 'Choose an action'
}
/* The engine names its phases after its own state machine. These are the
   same moments in the language of the game being played. */
const PHASE_NAMES: { [k: string]: string } = {
    'Initialize':               'Setting up',
    'Scenario Setup':           'Setting up',
    'Init Finished':            'Setting up',
    'Resolve Mulligans':        'Mulligans',
    'Player Turn End':          'End of turn',
    'Main Scheme Place Threat': 'The scheme advances',
    'Enemy Activation':         'The enemies act',
    'Deal Encounter Cards':     'Dealing encounter cards',
    'Reveal Encounter Cards':   'Revealing encounter cards',
    'End Phase':                'End of round',
    'End Round':                'End of round',
    'Start Round':              'Start of round',
}

function shortName(n: string): string {
    if (n === 'Captain America') return 'Cap'
    return n.split(' ')[0]
}
function roman(n: number): string {
    return ['', 'I', 'II', 'III', 'IV', 'V'][n] || String(n)
}

;(window as any).View = View

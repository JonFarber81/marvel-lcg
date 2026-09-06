import { Game } from './game.js'
import { Lib } from './lib.js'
import { Setting } from './settings.js'
import { WorldDescriptor } from './descriptor.js'

// The guided first game (Spider-Man vs Rhino, started from `/tutorial`).
//
// The coach is a passive observer: it never sends anything to the server and
// never takes a turn for the player. Every render it looks at the world the
// client already has and shows the first hint whose trigger has become true.
// Nothing here may throw into the render path, hence the try/catch in
// `onWorldUpdate`.

type PlayerView = WorldDescriptor['players'][number]
type CardView = WorldDescriptor['area_villain'][number]

const STORAGE_SEEN = 'tutorial_seen_hints'

interface Context {
    game_over       : boolean
    players_won     : boolean
    round           : number
    phase           : string
    is_my_turn      : boolean
    me              : PlayerView | undefined
    identity        : CardView | undefined
    villain         : CardView | undefined
    main_scheme     : CardView | undefined
    minions         : CardView[]
    threat          : number
    target_threat   : number
    escalation      : number
}

interface Hint {
    id      : string
    title   : string
    when    : (c: Context) => boolean
    body    : (c: Context) => string
}

function isHeroForm(c: Context): boolean {
    return c.identity?.card_type == 'Hero'
}

// Ordered: the first unseen hint whose trigger is true wins, so an early hint
// can never be buried by a later one that happens to fire at the same time.
const HINTS: Hint[] = [
    {
        // First in the list so a mid-game trigger that is still true cannot bury it.
        id: 'game_over',
        title: 'That is the game',
        when: (c) => c.game_over,
        body: (c) => c.players_won ? `
            Rhino is down. You have played a full game of Marvel Champions.
            <br/>From here: <b>New Game</b> opens every scenario and hero, Rhino has an
            <b>expert</b> version, and the <b>Deck Editor</b> lets you build something of
            your own.` : `
            Rhino won this one — most first games go that way, and nothing is lost by
            trying again.
            <ul>
                <li>Threat filled the main scheme? Thwart earlier, and spend fewer turns
                in alter-ego form, since the villain schemes while you are down there.</li>
                <li>Spider-Man went down? Flip to Peter Parker and Recover before you are
                low, not after.</li>
            </ul>
            <b>New Game</b> deals a fresh one whenever you are ready.`,
    },
    {
        id: 'welcome',
        title: 'Welcome to Marvel Champions',
        when: (c) => c.villain != undefined && c.identity != undefined,
        body: () => `
            You are <b>Spider-Man</b>. Rhino is breaking into a lab, and
            <b>The Break-In!</b> is the scheme he is trying to complete.
            <ul>
                <li>You <b>win</b> by defeating Rhino: 14 hit points at stage 1, then 15 more at stage 2.</li>
                <li>You <b>lose</b> if The Break-In! fills up with threat, or if Spider-Man takes 10 damage.</li>
            </ul>
            Hover any card to zoom it. Press <b>F</b> or right-click to flip one over.`,
    },
    {
        id: 'mulligan',
        title: 'Your opening hand',
        when: (c) => c.phase == 'Resolve Mulligans',
        body: () => `
            Once per game you may throw back any number of your opening cards and
            draw the same number of replacements.
            <br/>Select the cards you want to replace and confirm; confirm with
            nothing selected to keep the hand you have.`,
    },
    {
        id: 'alter_ego',
        title: 'Peter Parker, your alter-ego',
        when: (c) => c.is_my_turn && c.identity?.card_type == 'AlterEgo',
        body: () => `
            You begin in <b>alter-ego</b> form. Peter Parker recovers 3 damage and
            refills to 6 cards at the end of his turn, but he cannot attack or thwart.
            <br/>Click Peter Parker to see his actions, including <b>Change Form</b>.
            You may change form once per turn.
            <br/>The catch: while you are in alter-ego form the villain <b>schemes</b>
            instead of attacking you, which puts threat on The Break-In!.`,
    },
    {
        id: 'hero_form',
        title: 'Spider-Man, your hero form',
        when: (c) => c.is_my_turn && isHeroForm(c),
        body: () => `
            Click Spider-Man to bring up his basic powers:
            <ul>
                <li><b>Attack</b> — 2 damage to an enemy.</li>
                <li><b>Thwart</b> — remove 1 threat from a scheme.</li>
                <li><b>Change Form</b> — back to Peter Parker.</li>
            </ul>
            Using a basic power <b>exhausts</b> him (turns the card sideways), so you
            get one per turn. Cards from your hand are how you do more than that.`,
    },
    {
        id: 'resources',
        title: 'Playing cards',
        when: (c) => c.is_my_turn && isHeroForm(c) && (c.me?.hand_cards.length ?? 0) > 0,
        body: () => `
            Click a card in your hand to play it. To pay its cost, click other cards
            in hand — each one is worth the resource icon printed in its corner —
            then press <b>OK</b>.
            <br/>Web-Shooter can be exhausted for a [wild] resource, and as Peter
            Parker the Scientist ability gives you one [mental] each round.
            <br/>Changed your mind? Press <b>Esc</b> or the Cancel button.`,
    },
    {
        id: 'threat',
        title: 'The threat clock',
        when: (c) => c.is_my_turn && c.threat > 0,
        body: (c) => `
            The Break-In! is at <b>${c.threat} of ${c.target_threat}</b> threat and
            gains ${c.escalation || 1} more every villain phase. Fill it and you lose
            on the spot.
            <br/>Thwarting buys you time; attacking ends the game. You cannot ignore
            either one for long — that tension is the whole game.`,
    },
    {
        id: 'exhausted',
        title: 'Ending your turn',
        when: (c) => c.is_my_turn && c.identity != undefined && !c.identity.is_ready,
        body: () => `
            Spider-Man is exhausted, so his basic power is spent for this turn. You can
            still play cards and use card abilities.
            <br/>When you are done, press the <b>End</b> button on the right edge of the
            screen. You then draw back up to your hand size and the villain phase begins.`,
    },
    {
        id: 'place_threat',
        title: 'Villain phase, step 1: threat',
        when: (c) => c.phase == 'Main Scheme Place Threat',
        body: (c) => `
            The villain phase runs in four steps, and this is the first: The Break-In!
            gains ${c.escalation || 1} threat per player, plus one for every
            acceleration icon in play.`,
    },
    {
        id: 'enemy_activation',
        title: 'Villain phase, step 2: enemies activate',
        when: (c) => c.phase == 'Enemy Activation',
        body: () => `
            Rhino activates against you. In hero form he <b>attacks</b>; in alter-ego
            form he <b>schemes</b> instead. Every minion engaged with you activates too.
            <br/>An attack flips a face-down <b>boost</b> card that can add to its
            damage, so the number on his card is a minimum, not a promise.
            <br/>When you are attacked you may <b>Defend</b> with Spider-Man (worth 3)
            or play a card such as Backflip.`,
    },
    {
        id: 'encounter',
        title: 'Villain phase, steps 3 and 4: encounter cards',
        when: (c) => c.phase == 'Reveal Encounter Cards',
        body: () => `
            You are dealt one encounter card face down, then it is revealed and resolved.
            It may be a <b>minion</b> that engages you, a <b>side scheme</b> that starts
            a second threat clock, a <b>treachery</b> that resolves and is discarded, or
            an <b>attachment</b> that sticks around.
            <br/>After that the round ends and a new player phase begins.`,
    },
    {
        id: 'minion',
        title: 'A minion is engaged with you',
        when: (c) => c.minions.length > 0,
        body: () => `
            An engaged minion attacks you every villain phase until it is defeated, so
            it usually pays to deal with it early.
            <br/>Spider-Man's basic Attack works on any enemy: click him, choose
            <b>Attack</b>, then click the minion as the target.`,
    },
    {
        id: 'stage_two',
        title: 'Rhino advances',
        when: (c) => c.villain?.card_id == '01095',
        body: () => `
            Rhino has flipped to <b>stage 2</b>: 15 hit points, a stronger attack, and
            the damage you already dealt is gone.
            <br/>He also drags the Breakin' &amp; Takin' side scheme into play. Side
            schemes hold threat of their own and have to be thwarted separately.`,
    },
    {
        id: 'tools',
        title: 'Tools worth knowing',
        when: (c) => c.round >= 3 && c.is_my_turn,
        body: () => `
            <ul>
                <li><b>Tab</b> opens the game log — every step, in order.</li>
                <li><b>Ctrl+Z</b> undoes; hold <b>Ctrl</b> to fast-forward animations.</li>
                <li><b>1</b> and <b>2</b> open your deck and discard pile; hold <b>Alt</b> to zoom.</li>
                <li>The sidebar tucked against the right edge holds Log, Pause, Undo, Redo and QSave.</li>
            </ul>
            That is everything you need. Good luck against Rhino.`,
    },
]

export class Tutorial {
    private static coach_div    : HTMLElement | null = null
    private static title_div    : HTMLElement
    private static text_div     : HTMLElement
    private static label_div    : HTMLElement
    private static seen         : Set<string> = new Set()
    private static current      : Hint | null = null
    private static stopped      = false
    private static recheck_timer: number = 0

    static init() {
        if( !Setting.is_tutorial ) {
            return
        }
        Lib.loader.loadCSS('./public/css/marvel/tutorial.css')
        Tutorial.seen = Tutorial.loadSeen()
        Tutorial.coach_div = Tutorial.createCoachDiv()
        document.body.appendChild(Tutorial.coach_div)
    }

    private static loadSeen(): Set<string> {
        // Session storage, so a mid-game refresh does not replay every hint,
        // but a fresh guided game starts from the beginning.
        try {
            const raw = sessionStorage.getItem(STORAGE_SEEN)
            return new Set<string>(raw ? JSON.parse(raw) : [])
        } catch {
            return new Set<string>()
        }
    }

    private static saveSeen() {
        try {
            sessionStorage.setItem(STORAGE_SEEN, JSON.stringify([...Tutorial.seen]))
        } catch {
        }
    }

    private static createCoachDiv(): HTMLElement {
        const coach = document.createElement('div')
        coach.id = 'tutorial-coach'
        coach.classList.add('hide')

        const head = document.createElement('div')
        head.className = 'tutorial-head'
        head.onclick = () => Tutorial.toggleCollapsed()

        Tutorial.label_div = document.createElement('div')
        Tutorial.label_div.className = 'tutorial-head-label'
        head.appendChild(Tutorial.label_div)

        const toggle = document.createElement('div')
        toggle.className = 'tutorial-head-toggle'
        head.appendChild(toggle)
        coach.appendChild(head)

        const body = document.createElement('div')
        body.className = 'tutorial-body'

        Tutorial.title_div = document.createElement('div')
        Tutorial.title_div.className = 'tutorial-title'
        body.appendChild(Tutorial.title_div)

        Tutorial.text_div = document.createElement('div')
        Tutorial.text_div.className = 'tutorial-text'
        body.appendChild(Tutorial.text_div)
        coach.appendChild(body)

        const foot = document.createElement('div')
        foot.className = 'tutorial-foot'

        const next = document.createElement('button')
        next.type = 'button'
        next.id = 'tutorial-next'
        next.textContent = 'Got it'
        next.onclick = (e) => {
            e.stopPropagation()
            Tutorial.dismiss()
        }
        foot.appendChild(next)

        const stop = document.createElement('button')
        stop.type = 'button'
        stop.id = 'tutorial-stop'
        stop.textContent = 'Stop the tutorial'
        stop.onclick = (e) => {
            e.stopPropagation()
            Tutorial.stop()
        }
        foot.appendChild(stop)
        coach.appendChild(foot)

        return coach
    }

    private static toggleCollapsed() {
        Tutorial.coach_div?.classList.toggle('collapsed')
    }

    private static dismiss() {
        Tutorial.current = null
        Tutorial.coach_div?.classList.add('hide')
        // A hint can already be due the moment this one is dismissed, and the
        // next render only arrives when the player acts. Look again shortly so
        // the tutorial does not appear to have stopped.
        clearTimeout(Tutorial.recheck_timer)
        Tutorial.recheck_timer = setTimeout(() => Tutorial.onWorldUpdate(), 800)
    }

    private static stop() {
        Tutorial.stopped = true
        Tutorial.dismiss()
        clearTimeout(Tutorial.recheck_timer)
    }

    private static buildContext(): Context | null {
        const world = Game.world_descriptor
        if( !world ) {
            return null
        }
        const me = world.players[Setting.player_id]
        const main_scheme = world.area_schemes_main[0]
        const phase = world.phase

        // "Player 1 Turn" .. "Player 4 Turn"; the seat number is 1-based.
        const turn_of = phase.match(/^Player (\d+) Turn$/)

        return {
            game_over       : Game.game_over,
            players_won     : Game.players_won,
            round           : world.round_id,
            phase           : phase,
            is_my_turn      : turn_of != null && Number(turn_of[1]) == Setting.player_id + 1,
            me              : me,
            identity        : me?.area_hero[0],
            villain         : world.area_villain.find(x => x.card_type == 'EncounterVillain'),
            main_scheme     : main_scheme,
            minions         : (me?.engaged_enemies ?? []).filter(x => x.card_type == 'Minion'),
            threat          : main_scheme?.info['k_threat'] ?? 0,
            target_threat   : main_scheme?.info['target_threat'] ?? 0,
            escalation      : main_scheme?.info['escalation_threat'] ?? 0,
        }
    }

    private static show(hint: Hint, context: Context) {
        Tutorial.current = hint
        Tutorial.seen.add(hint.id)
        Tutorial.saveSeen()

        Tutorial.label_div.textContent = `Tutorial — tip ${Tutorial.seen.size} of ${HINTS.length}`
        Tutorial.title_div.textContent = hint.title
        Tutorial.text_div.innerHTML = Lib.game.cleanResText(hint.body(context))
        Tutorial.coach_div!.classList.remove('hide')
    }

    // Called once per world render. Shows the next hint whose trigger has become
    // true, unless a hint is already on screen waiting to be read.
    static onWorldUpdate() {
        if( !Tutorial.coach_div || Tutorial.stopped || Tutorial.current ) {
            return
        }
        try {
            const context = Tutorial.buildContext()
            if( !context ) {
                return
            }
            for( const hint of HINTS ) {
                if( !Tutorial.seen.has(hint.id) && hint.when(context) ) {
                    Tutorial.show(hint, context)
                    return
                }
            }
        } catch (error) {
            // A broken hint must never take the game down with it.
            console.log('Tutorial:', error)
            Tutorial.stopped = true
        }
    }
}

(window as any).Tutorial = Tutorial;

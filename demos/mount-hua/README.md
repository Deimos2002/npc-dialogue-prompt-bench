# Mount Hua: free cultivation demo

An interactive game encounter with an original Mount Hua elder, Japanese-inspired
ink-and-parchment visuals, a Hyperframes scene, and GSAP animation.

```powershell
npm.cmd install --prefix demos/mount-hua
python demos/mount-hua/serve.py
```

Open <http://127.0.0.1:8088/>. The server binds to loopback and serves only this
demo directory. After installation, assets and dependencies are local.

## Interaction

Allocate your own points with plus/minus controls or direct number entry. Current
and projected stats are shown separately. You can leave points in reserve and
commit a partial allocation. Committing updates current stats once, subtracts only
the points spent, and clears the draft. Clearing a draft never changes current
stats. A pool smaller than an existing draft is rejected until additions are
removed. The editable pool is a demo control, not a way to earn points in the game.

Ask the elder about the chosen spread; optionally choose a fighting intent so his
comment can identify a mismatch. Examples load a draft only when clicked. Dialogue
choices and simple text patterns trigger authored replies, not a live language
model. No API calls, credentials, persistence, or Langfuse tracing are used.

Path classification uses projected totals (current stats plus draft), not just the
new points. Single-stat and pair-based tendencies include Inner flame, Mist walker,
Dancing blade, Stone guardian, Tempered flame, Wind & stone, Steady lantern, and
Fourfold foundation. These are provisional descriptive names. They confer no stat
bonuses, unlocks, damage multipliers, optimality, or guarantees. The strongest stat
is treated as dominant when at least 1.5 times the next; close totals across all four
are treated as broad. These heuristics are presentation rules, not supplied game
mechanics or validated build classifications.

The menu pins its projected path and action buttons while its editing area scrolls.
Keyboard labels, focus styles, direct inputs, and reduced-motion behavior are
provided. The journal and all character state are in memory; reloading resets them.

## Preserved version

The original game demo is saved at [snapshots/game-v1](snapshots/game-v1/index.html).
Open <http://127.0.0.1:8088/snapshots/game-v1/> or use Original demo in the HUD.
Its HTML, CSS, JS, scene, illustration, and prior screenshot are preserved. Its
outer UI loads the installed dependencies from the main demo's node_modules.

## Structure and checks

- allocation.js: pure allocation, rounding, classification, and assessment rules.
- demo.js: browser state, controls, journal, and GSAP UI transitions.
- index.html / style.css: game HUD, dialogue box, and cultivation menu.
- scene/index.html: independent, seekable 16-second Hyperframes/GSAP composition.
- scene/assets: original AI-generated portrait and GSAP distribution with license header.
- serve.py: local server limited to the demo directory.

```powershell
npm.cmd test --prefix demos/mount-hua
npm.cmd run check --prefix demos/mount-hua
```

Four meaningful rule tests cover overspending, integer rounding for every pool
0–100, projected classifications, and intent/reserve feedback. Local browser checks
cover free entry, mixed-path feedback, partial commit, disabled repeat commit,
budget protection, and the preserved version's asset routes. The scene's lint has
zero errors and warnings. Earlier runtime/layout/contrast checks passed at 0 and
8 seconds; those scene checks do not validate the full interactive UI.

Sources: [Hyperframes](https://github.com/heygen-com/hyperframes),
[player API](https://github.com/heygen-com/hyperframes/tree/main/packages/player),
[GSAP](https://github.com/greensock/GSAP). Versions are pinned in package.json and
package-lock.json. GSAP's distribution retains its copyright and license URL.

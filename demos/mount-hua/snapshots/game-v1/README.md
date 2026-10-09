# The Plum Blossom Pavilion

A small interactive Mount Hua NPC demo. The original elder and murim setting use
a Japanese-inspired ink-and-parchment visual treatment. It does not redefine the
character as Japanese. The portrait is an original AI-generated illustration.

From the repository root:

```powershell
npm.cmd install --prefix demos/mount-hua
python demos/mount-hua/serve.py
```

Open <http://127.0.0.1:8088>. The server binds to loopback and serves only the demo
directory. Node.js and Python are required. After installation, dependencies and
artwork are local; no CDN or model calls are required.

Choose a path, change the point budget, ask for guidance, and optionally apply the
allocation. Current stats and proposed additions are separate. Changing the path
or budget invalidates approval to apply; resetting restores the starting state.
The journal and character state exist only in memory. Buttons and a few text
patterns trigger authored replies: this is a presentation demo, not a live LLM,
benchmark output, talking avatar, or validated build optimizer.

`scene/index.html` is a genuine Hyperframes composition, embedded with
`@hyperframes/player`. A paused, seekable GSAP timeline animates the portrait,
mist, and petals for 16 seconds. GSAP 3.15.0 also animates HUD entrances,
dialogue changes, and allocation badges. System reduced-motion preference disables
the outer UI transitions and pauses the scene. The outer HTML owns interaction and dialogue;
the composition has no user-dependent animation or network requests. The scene
can also be previewed independently in Hyperframes Studio. Dependencies are
pinned in package.json and package-lock.json.

Validate the scene:

```powershell
npm.cmd run check --prefix demos/mount-hua
```

Framework references: [repository](https://github.com/heygen-com/hyperframes),
[player API](https://github.com/heygen-com/hyperframes/tree/main/packages/player),
[composition contract](https://github.com/heygen-com/hyperframes/blob/main/skills/hyperframes-core/SKILL.md).

Files: index.html (layout), style.css (visuals), demo.js (local interaction),
scene/index.html (animation), scene/assets/elder.png (illustration), serve.py
(local preview server). No project `.env` is read or sent to the browser.

GSAP: [official repository](https://github.com/greensock/GSAP). The shipped GSAP
distribution retains its copyright/license header and standard-license URL.

Verification: local browser checks covered guidance, hybrid selection, apply/reset,
budget changes, pause, and mobile layout. Hyperframes lint passes with zero
errors or warnings. The framework runtime/layout/contrast check also passed at
0 and 8 seconds; this checks the scene, not every outer UI state.

// Local, authored demo. No model requests, credentials, or persistence.
const stats = ["Strength", "Agility", "Vitality", "Qi"];
const effects = [
  "Physical power",
  "Speed & evasion",
  "Health & resilience",
  "Technique energy",
];
const paths = {
  assassin: {
    weights: [4, 12, 4, 0],
    reason:
      "Agility supports your quick steps; Strength lends weight to the strike. Vitality offers some resilience when evasion fails. Technique energy receives less attention.",
    openings: [
      "A shadow need not wrestle the mountain.",
      "The quick foot still needs firm ground.",
      "Leave before the dust remembers your name.",
    ],
  },
  fighter: {
    weights: [9, 2, 8, 1],
    reason:
      "Strength supports physical power, and Vitality supports resilience. You give less attention to speed and technique energy. A sturdy foundation does not make you invulnerable.",
    openings: [
      "The mountain endures without chasing the wind.",
      "A heavy branch needs deep roots.",
      "Choose what you can hold when the wind rises.",
    ],
  },
  hybrid: {
    weights: [4, 8, 7, 1],
    reason:
      "Agility and Vitality support movement and resilience. Physical power and technique energy grow more slowly. Two paths may meet, but neither receives all your effort.",
    openings: [
      "Bamboo bends; stone endures. Learn something from each.",
      "You may carry two cups, though neither will hold the whole river.",
      "A wide path is still walked one step at a time.",
    ],
  },
};
let current = [5, 5, 5, 5],
  path = "assassin",
  preview = null,
  exchange = 0;
const $ = (id) => document.getElementById(id);
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
function animate(target, from, to) {
  if (!reducedMotion.matches)
    gsap.fromTo(target, from, { ...to, overwrite: true });
}
function budget() {
  return Math.min(100, Math.max(0, Math.trunc(Number($("budget").value) || 0)));
}
function allocation() {
  const weights = paths[path].weights,
    pool = budget();
  const shares = weights.map((weight) => (weight * pool) / 20);
  const points = shares.map(Math.floor);
  const order = shares
    .map((value, i) => ({ i, remainder: value - points[i] }))
    .sort((a, b) => b.remainder - a.remainder || a.i - b.i);
  const remaining = pool - points.reduce((sum, n) => sum + n, 0);
  for (let i = 0; i < remaining; i++) points[order[i].i]++;
  return points;
}
function render() {
  const added = allocation();
  $("stats").replaceChildren(
    ...stats.map((name, i) => {
      const row = document.createElement("div");
      row.className = "stat-row";
      const label = document.createElement("div");
      label.className = "stat-name";
      label.textContent = name;
      const effect = document.createElement("small");
      effect.textContent = effects[i];
      label.append(effect);
      const now = document.createElement("span");
      now.className = "stat-current";
      now.textContent = current[i];
      const add = document.createElement("span");
      add.className = "stat-add";
      add.textContent = "+" + added[i];
      row.append(label, now, add);
      return row;
    }),
  );
  $("total").textContent =
    `${added.reduce((sum, n) => sum + n, 0)} / ${budget()}`;
  $("apply").disabled = !preview || budget() === 0;
  document.querySelectorAll("[data-path]").forEach((button) => {
    const selected = button.dataset.path === path;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
  });
}
function say(player, text) {
  $("dialogue").textContent = "“" + text + "”";
  for (const [speaker, content] of [
    ["Disciple", player],
    ["Elder", text],
  ]) {
    const item = document.createElement("li"),
      label = document.createElement("b");
    label.textContent = speaker + ": ";
    item.append(label, document.createTextNode(content));
    $("journal").append(item);
  }
  animate(
    "#dialogue",
    { opacity: 0.3, y: 6 },
    { opacity: 1, y: 0, duration: 0.35, ease: "power2.out" },
  );
  exchange++;
}
function selectPath(next) {
  path = next;
  preview = null;
  render();
  animate(
    ".stat-add",
    { opacity: 0.3, scale: 0.9 },
    { opacity: 1, scale: 1, duration: 0.3, stagger: 0.035 },
  );
  $("state-note").textContent =
    "Preview changed. Ask for guidance before applying these additions.";
}
function guide(player = "Master, how should I distribute my points?") {
  const data = paths[path];
  preview = allocation();
  const intro = data.openings[exchange % data.openings.length];
  const numbers = stats.map((name, i) => `${name} +${preview[i]}`).join(", ");
  say(
    player,
    budget()
      ? `${intro} Add ${numbers}. ${data.reason}`
      : "An empty cup cannot pour. You have no unspent points, so your stats remain as they are. Practice your chosen approach; when more points become available, we can consider where to place them.",
  );
  $("state-note").textContent = budget()
    ? "The recommendation spends " +
      budget() +
      " points. Apply it to update this local character."
    : "No points remain. Begin again or enter a new point budget.";
  render();
}
function ask(question) {
  const lower = question.toLowerCase();
  if (/tomorrow|shortcut|instant|surpass/.test(lower))
    say(
      question,
      "A tree pulled upward does not grow taller; it loses its roots. Choose one thing to practice today, and return to it tomorrow. Haste prevents you from reaching your goal.",
    );
  else if (/useless|wudang|angry|swear|insult|better than/.test(lower))
    say(
      question,
      "If another teacher helps you, listen carefully. My beard will survive the comparison. Now—do you seek power, swift movement, or the strength to remain standing?",
    );
  else if (/both|hybrid|balance|two paths/.test(lower)) {
    selectPath("hybrid");
    guide(question);
  } else if (/point|build|stat|guidance|allocate|distribute/.test(lower))
    guide(question);
  else
    say(
      question,
      "Before choosing a road, consider where you wish to arrive. Tell me whether you favor swift retreats, close fighting, or a little of each. Your present foundation is shown beside us.",
    );
}
document
  .querySelectorAll("[data-path]")
  .forEach((button) =>
    button.addEventListener("click", () => selectPath(button.dataset.path)),
  );
document
  .querySelectorAll("[data-question]")
  .forEach((button) =>
    button.addEventListener("click", () => ask(button.dataset.question)),
  );
$("budget").addEventListener("input", () => {
  preview = null;
  render();
  $("state-note").textContent =
    "Budget changed. Seek a fresh recommendation before applying points.";
});
$("budget").addEventListener("change", () => {
  $("budget").value = budget();
  render();
});
$("guidance").addEventListener("click", () => guide());
$("question-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const question = $("question").value.trim();
  if (question) {
    ask(question);
    $("question").value = "";
  }
});
$("apply").addEventListener("click", () => {
  if (!preview || !budget()) return;
  current = current.map((value, i) => value + preview[i]);
  preview = null;
  $("budget").value = 0;
  render();
  $("state-note").textContent =
    "Allocation applied locally. Current stats updated; zero unspent points remain.";
});
$("journal-toggle").addEventListener("click", () => {
  $("journal").hidden = !$("journal").hidden;
  $("journal-toggle").setAttribute(
    "aria-expanded",
    String(!$("journal").hidden),
  );
});
$("reset").addEventListener("click", () => {
  current = [5, 5, 5, 5];
  path = "assassin";
  preview = null;
  exchange = 0;
  $("budget").value = 20;
  $("question").value = "";
  $("journal").replaceChildren();
  $("journal").hidden = true;
  $("journal-toggle").setAttribute("aria-expanded", "false");
  $("dialogue").textContent =
    "“You have climbed far to stand here. Tell me—what do you wish to become when you descend?”";
  $("state-note").textContent =
    "Guidance previews additions. Your current stats stay unchanged until you apply them.";
  render();
});
const scene = $("elder-scene");
let paused = false;
$("motion").addEventListener("click", () => {
  paused = !paused;
  if (paused) scene.pause();
  else scene.play();
  $("motion").textContent = paused ? "Play scene ▷" : "Pause scene Ⅱ";
  $("motion").setAttribute("aria-pressed", String(paused));
});
if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  scene.removeAttribute("autoplay");
  paused = true;
  $("motion").textContent = "Play scene ▷";
  $("motion").setAttribute("aria-pressed", "true");
  scene.addEventListener("ready", () => scene.pause(), { once: true });
}
render();

if (!reducedMotion.matches) {
  gsap
    .timeline()
    .from("header", { opacity: 0, y: -8, duration: 0.65 }, 0.1)
    .from(".scene-heading", { opacity: 0, x: -12, duration: 0.7 }, 0.25)
    .from(".build", { opacity: 0, x: 14, duration: 0.7 }, 0.4)
    .from(".conversation", { opacity: 0, y: 18, duration: 0.7 }, 0.6);
}

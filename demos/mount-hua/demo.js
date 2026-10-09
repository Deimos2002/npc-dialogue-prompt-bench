import {
  STAT_NAMES,
  STAT_EFFECTS,
  sum,
  whole,
  setAddition,
  distribute,
  classify,
  assess,
} from "./allocation.js";
// Local authored dialogue. No network, credentials, or browser persistence.
const $ = (id) => document.getElementById(id);
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
let current = [5, 5, 5, 5],
  draft = [0, 0, 0, 0],
  pool = 20,
  exchange = 0;
const examples = {
  swift: [4, 12, 4, 0],
  fighter: [9, 2, 8, 1],
  hybrid: [4, 8, 7, 1],
  techniques: [1, 2, 3, 14],
};
function animate(target, from, to) {
  if (!reducedMotion.matches)
    gsap.fromTo(target, from, { ...to, overwrite: true });
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
function createStats() {
  STAT_NAMES.forEach((name, i) => {
    const row = document.createElement("div");
    row.className = "free-stat";
    const label = document.createElement("div");
    label.className = "free-stat-name";
    const title = document.createElement("strong");
    title.textContent = name;
    const effect = document.createElement("small");
    effect.textContent = STAT_EFFECTS[i];
    const values = document.createElement("span");
    values.id = "values-" + i;
    label.append(title, effect, values);
    const controls = document.createElement("div");
    controls.className = "point-controls";
    const minus = document.createElement("button");
    minus.id = "minus-" + i;
    minus.textContent = "−";
    minus.setAttribute("aria-label", "Remove one " + name + " point");
    const input = document.createElement("input");
    input.id = "add-" + i;
    input.type = "number";
    input.min = 0;
    input.value = 0;
    input.setAttribute("aria-label", name + " added points");
    const plus = document.createElement("button");
    plus.id = "plus-" + i;
    plus.textContent = "+";
    plus.setAttribute("aria-label", "Add one " + name + " point");
    minus.addEventListener("click", () => edit(i, draft[i] - 1));
    plus.addEventListener("click", () => edit(i, draft[i] + 1));
    input.addEventListener("input", () => edit(i, input.value));
    controls.append(minus, input, plus);
    row.append(label, controls);
    $("stats").append(row);
  });
}
function render() {
  const left = pool - sum(draft),
    path = classify(current, draft);
  $("path-name").textContent = path.name;
  $("path-detail").textContent = path.detail;
  $("remaining").textContent = left + " / " + pool;
  $("pool-fill").style.width = (pool ? (sum(draft) / pool) * 100 : 0) + "%";
  $("apply").disabled = sum(draft) === 0;
  STAT_NAMES.forEach((_, i) => {
    $("values-" + i).textContent = current[i] + " → " + (current[i] + draft[i]);
    $("add-" + i).value = draft[i];
    $("add-" + i).max = left + draft[i];
    $("minus-" + i).disabled = draft[i] === 0;
    $("plus-" + i).disabled = left === 0;
    $("values-" + i).classList.toggle("invested", draft[i] > 0);
  });
}
function edit(index, value) {
  const requested = whole(value);
  draft = setAddition(draft, index, value, pool);
  render();
  $("state-note").textContent =
    requested > draft[index]
      ? "The remaining pool cannot cover that addition. No other stat was changed."
      : "This is a preview. Current stats change only when you commit points.";
  animate("#values-" + index, { opacity: 0.5 }, { opacity: 1, duration: 0.2 });
}
function review(player = "Master, what do you think of the points I chose?") {
  const result = assess(current, draft, pool, $("intent").value, exchange);
  say(player, result.text);
  $("state-note").textContent =
    "The elder reviewed your choices. You remain free to change or commit them.";
}
function ask(question) {
  if (/tomorrow|shortcut|instant|surpass/i.test(question))
    say(
      question,
      "A tree pulled upward does not grow taller; it loses its roots. Choose one thing to practice today, and return to it tomorrow. Haste prevents you from reaching your goal.",
    );
  else if (/useless|wudang|angry|swear|insult|better than/i.test(question))
    say(
      question,
      "If another teacher helps you, listen carefully. My beard will survive the comparison. Let your purpose guide your points; wounded pride is a poor teacher.",
    );
  else if (/both|hybrid|balance|two paths/i.test(question)) {
    $("intent").value = "hybrid";
    if (sum(draft)) review(question);
    else
      say(
        question,
        "You may follow both paths. Agility supports movement, Vitality resilience. With limited points, physical power or technique energy may receive less attention. Choose your additions beside us; I will consider the compromise with you.",
      );
  } else if (
    /point|build|stat|guidance|allocate|distribute|path/i.test(question)
  )
    review(question);
  else
    say(
      question,
      "Lay out your choices and your purpose. I can comment on the foundation before me; I will not pretend to know a road you have yet to describe.",
    );
}
function updateBudget(finalize = false) {
  const next = whole($("budget").value);
  if (next < sum(draft)) {
    if (finalize) {
      $("budget").value = pool;
      $("budget").removeAttribute("aria-invalid");
      render();
    } else {
      $("budget").setAttribute("aria-invalid", "true");
      $("apply").disabled = true;
      $("guidance").disabled = true;
    }
    $("state-note").textContent =
      "Remove additions first: this preview needs " +
      sum(draft) +
      " points. The existing pool has been kept.";
    if (finalize) $("guidance").disabled = false;
    return;
  }
  pool = next;
  $("budget").removeAttribute("aria-invalid");
  $("guidance").disabled = false;
  if (finalize) $("budget").value = pool;
  render();
  $("state-note").textContent = "Point pool updated. Your additions were kept.";
}
$("budget").addEventListener("input", () => updateBudget());
$("budget").addEventListener("change", () => updateBudget(true));
$("budget").addEventListener("blur", () => updateBudget(true));
$("clear").addEventListener("click", () => {
  draft = [0, 0, 0, 0];
  render();
  $("state-note").textContent =
    "Additions cleared. Current stats are unchanged.";
});
document.querySelectorAll("[data-preset]").forEach((button) =>
  button.addEventListener("click", () => {
    draft = distribute(pool, examples[button.dataset.preset]);
    $("intent").value = button.dataset.preset;
    render();
    button.closest("details").open = false;
    $("state-note").textContent =
      "Example loaded into your preview. Change any addition freely.";
  }),
);
$("guidance").addEventListener("click", () => review());
$("apply").addEventListener("click", () => {
  const spent = sum(draft);
  if (!spent) return;
  current = current.map((value, i) => value + draft[i]);
  pool -= spent;
  draft = [0, 0, 0, 0];
  $("budget").value = pool;
  render();
  $("state-note").textContent =
    "Points committed. " +
    pool +
    " remain unspent; your current foundation is updated.";
  animate(
    ".free-stat-name span",
    { opacity: 0.4 },
    { opacity: 1, duration: 0.4, stagger: 0.05 },
  );
});
document
  .querySelectorAll("[data-question]")
  .forEach((button) =>
    button.addEventListener("click", () => ask(button.dataset.question)),
  );
$("question-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const question = $("question").value.trim();
  if (question) {
    ask(question);
    $("question").value = "";
  }
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
  draft = [0, 0, 0, 0];
  pool = 20;
  exchange = 0;
  $("budget").value = 20;
  $("budget").removeAttribute("aria-invalid");
  $("guidance").disabled = false;
  $("intent").value = "any";
  $("question").value = "";
  $("journal").replaceChildren();
  $("journal").hidden = true;
  $("journal-toggle").setAttribute("aria-expanded", "false");
  $("dialogue").textContent =
    "“You have climbed far to stand here. Place your points as you see fit; I will tell you what I see in the foundation.”";
  $("state-note").textContent =
    "Allocate freely. Unspent points may be kept in reserve.";
  render();
});
createStats();
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

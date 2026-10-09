// Blind labelling client. Every value from the server is written with textContent, never as
// markup, so reply text cannot inject HTML or script.
"use strict";

const $ = (id) => document.getElementById(id);
let rater = "";
let current = null;

function text(id, value) {
  $(id).textContent = value;
}

function listItem(value) {
  const li = document.createElement("li");
  li.textContent = value;
  return li;
}

function render(item) {
  current = item;
  text("char-name", item.character.name);
  text("char-summary", item.character.summary);
  text("char-voice", item.character.voice);
  $("char-traits").replaceChildren(
    ...item.character.traits.map((t) => listItem(`${t.description} (${t.density})`))
  );
  text("scene", `Class: ${item.scenario.class}. Story point: ${item.scenario.story_point}.`);
  $("conversation").replaceChildren(
    ...item.conversation.map((turn) => listItem(`${turn.speaker}: ${turn.text}`))
  );
  text("player", item.player);
  text("reply", item.reply);
  const fields = item.questions.map((q) => {
    const set = document.createElement("fieldset");
    const legend = document.createElement("legend");
    legend.textContent = q.text;
    set.append(legend);
    for (const answer of ["yes", "no"]) {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "radio";
      input.name = q.trait_id;
      input.value = answer;
      input.required = true;
      label.append(input, ` ${answer} `);
      set.append(label);
    }
    return set;
  });
  $("questions").replaceChildren(...fields);
  text("error", "");
}

async function next() {
  const response = await fetch(`/api/next?rater=${encodeURIComponent(rater)}`);
  if (!response.ok) {
    const invalidRater = response.status === 422;
    text(
      "error",
      invalidRater
        ? "Rater ids use letters, digits, '.', '_' or '-'."
        : "The screen could not load the next reply."
    );
    return;
  }
  const body = await response.json();
  $("item").hidden = Boolean(body.done);
  $("done").hidden = !body.done;
  if (!body.done) {
    text("progress", `${body.remaining} replies left.`);
    render(body.item);
  }
}

$("rater-form").addEventListener("submit", (event) => {
  event.preventDefault();
  rater = $("rater").value.trim();
  next();
});

$("label-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const answers = {};
  for (const q of current.questions) {
    answers[q.trait_id] = new FormData($("label-form")).get(q.trait_id);
  }
  const response = await fetch("/api/labels", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reply_id: current.reply_id, rater, answers }),
  });
  if (response.ok) {
    next();
  } else {
    text("error", "The label was not saved. Answer every question and try again.");
  }
});

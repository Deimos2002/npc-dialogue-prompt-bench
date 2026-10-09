// Pure rules for the local demo. Path names describe tendencies, not game bonuses.
export const STAT_NAMES = ["Strength", "Agility", "Vitality", "Qi"];
export const STAT_EFFECTS = [
  "Physical power",
  "Speed & evasion",
  "Health & resilience",
  "Technique energy",
];
export const sum = (values) =>
  values.reduce((total, value) => total + value, 0);
export function whole(value) {
  return Math.max(0, Math.min(100, Math.trunc(Number(value) || 0)));
}
export function setAddition(draft, index, value, pool) {
  const next = [...draft];
  const available = Math.max(0, pool - sum(draft) + draft[index]);
  next[index] = Math.min(whole(value), available);
  return next;
}
export function distribute(pool, weights) {
  const shares = weights.map((weight) => (weight * pool) / sum(weights));
  const result = shares.map(Math.floor);
  const order = shares
    .map((value, index) => ({ index, fraction: value - result[index] }))
    .sort((a, b) => b.fraction - a.fraction || a.index - b.index);
  const remainder = pool - sum(result);
  for (let i = 0; i < remainder; i++) result[order[i].index]++;
  return result;
}
export function classify(current, draft) {
  const projected = current.map((value, index) => value + draft[index]);
  const ranked = projected
    .map((value, index) => ({ value, index }))
    .sort((a, b) => b.value - a.value || a.index - b.index);
  if (ranked[0].value - ranked[3].value <= 2)
    return {
      name: "Fourfold foundation",
      detail: "A broad foundation across all four stats.",
      focus: [0, 1, 2, 3],
    };
  if (ranked[0].value >= ranked[1].value * 1.5) {
    return [
      {
        name: "Iron fist",
        detail: "Physical power leads this foundation.",
        focus: [0],
      },
      {
        name: "Swift shadow",
        detail: "Speed and evasion lead this foundation.",
        focus: [1],
      },
      {
        name: "Rooted mountain",
        detail: "Health and resilience lead this foundation.",
        focus: [2],
      },
      {
        name: "Inner flame",
        detail: "Technique energy leads this foundation.",
        focus: [3],
      },
    ][ranked[0].index];
  }
  const pair = [ranked[0].index, ranked[1].index].sort().join("");
  return {
    "01": {
      name: "Dancing blade",
      detail: "Physical power paired with movement.",
      focus: [0, 1],
    },
    "02": {
      name: "Stone guardian",
      detail: "Physical power paired with resilience.",
      focus: [0, 2],
    },
    "03": {
      name: "Tempered flame",
      detail: "Physical power paired with technique energy.",
      focus: [0, 3],
    },
    12: {
      name: "Wind & stone",
      detail: "Movement paired with resilience.",
      focus: [1, 2],
    },
    13: {
      name: "Mist walker",
      detail: "Movement paired with technique energy.",
      focus: [1, 3],
    },
    23: {
      name: "Steady lantern",
      detail: "Resilience paired with technique energy.",
      focus: [2, 3],
    },
  }[pair];
}
export function assess(current, draft, pool, intent, variation = 0) {
  const path = classify(current, draft);
  if (!sum(draft))
    return {
      path,
      text: pool
        ? "The page is still blank. Place a few points where your purpose lies; you need not spend them all at once."
        : "No points remain to place. Your foundation is unchanged. Practice your chosen approach; we may consider new points when they come.",
    };
  const openings = [
    "The branches tell me something of the roots.",
    "A path takes its shape beneath your feet.",
    "Let us see what your choices are preparing you for.",
  ];
  const order = draft
    .map((value, index) => ({ value, index }))
    .sort((a, b) => b.value - a.value || a.index - b.index);
  const neglected = draft
    .map((value, index) => ({ value, index }))
    .sort((a, b) => a.value - b.value || a.index - b.index);
  let caution = `You give less attention to ${STAT_NAMES[neglected[0].index]}, which supports ${STAT_EFFECTS[neglected[0].index].toLowerCase()}. Weigh that compromise against your purpose.`;
  if (Math.max(...draft) - Math.min(...draft) <= 1)
    caution =
      "You spread your effort broadly; none of these additions receives the whole of your attention.";
  if (intent === "swift" && draft[1] < Math.max(...draft))
    caution =
      "You seek swift retreats, yet Agility receives less than your largest investment. It supports speed and evasion; consider whether this spread serves that aim.";
  if (intent === "fighter" && draft[0] + draft[2] < draft[1] + draft[3])
    caution =
      "You seek physical power and resilience, yet more of these points go elsewhere. Strength and Vitality support that purpose.";
  if (intent === "techniques" && draft[3] < Math.max(...draft))
    caution =
      "You seek technique energy, yet Qi receives less than your largest investment. Qi supports that energy; it does not promise mastery.";
  if (intent === "hybrid" && (draft[1] === 0 || draft[2] === 0))
    caution =
      "You seek movement and resilience together. One receives no new points here. Your existing foundation remains, but consider what you wish to develop.";
  const remaining = pool - sum(draft);
  const reserve = remaining
    ? `You may keep the ${remaining} remaining points unspent.`
    : "Practice will show you where this foundation needs care.";
  return {
    path,
    text: `${openings[variation % openings.length]} This leans toward ${path.name.toLowerCase()}: ${path.detail.toLowerCase()} ${caution} ${reserve}`,
  };
}

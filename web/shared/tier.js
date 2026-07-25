// Shared tier vocabulary.
//
// NFR-07: tier is never conveyed by colour alone. Every tier carries text, a
// shape and a colour, and every surface renders it through this module rather
// than reimplementing a CSS class. Colour-blindness, greyscale printing and
// glare on a phone in a sunny kitchen all defeat colour on its own.

export const TIERS = {
  LOW: {
    label: "Low",
    shape: "circle",
    colour: "#0B7B77",
    action: "No action beyond routine",
  },
  ELEVATED: {
    label: "Elevated",
    shape: "square",
    colour: "#A85D18",
    action: "Check in today",
  },
  HIGH: {
    label: "High",
    shape: "triangle",
    colour: "#C05A2E",
    action: "Act before this evening",
  },
  SEVERE: {
    label: "Severe",
    shape: "diamond",
    colour: "#B03A2C",
    action: "Act now — do not leave alone overnight",
  },
};

export function renderTier(tier) {
  const spec = TIERS[tier];
  if (!spec) throw new Error(`unknown tier: ${tier}`);
  const el = document.createElement("span");
  el.className = `tier tier-${tier.toLowerCase()} shape-${spec.shape}`;
  el.textContent = spec.label;
  el.setAttribute("role", "status");
  el.setAttribute("aria-label", `${spec.label} risk. ${spec.action}.`);
  return el;
}

// SC-5. Modelled values are labelled at every point of display, so the label
// travels with the number rather than being remembered by each caller.
export function renderModelled(value, unit = "°C") {
  const el = document.createElement("span");
  el.className = "modelled";
  el.textContent = `${value.toFixed(1)}${unit}`;
  el.title = "Modelled estimate, not a measurement";
  el.setAttribute("aria-label", `${value.toFixed(1)} ${unit}, modelled estimate`);
  return el;
}

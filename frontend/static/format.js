function formatShortDate(value, empty = "\u2014") {
  if (!value) {
    return empty;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return empty;
  }
  return parsed.toLocaleDateString("en-GB", {
    year: "2-digit",
    month: "2-digit",
    day: "2-digit",
  });
}

function scoreDisplayPercent(finalScore) {
  const raw = Number(finalScore);
  const score = Number.isFinite(raw) ? raw : 0;
  return Math.max(0, Math.min(100, Math.round(score * 100)));
}

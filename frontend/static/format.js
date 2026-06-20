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

function ordinalSuffix(day) {
  if (day >= 11 && day <= 13) {
    return "th";
  }
  switch (day % 10) {
    case 1:
      return "st";
    case 2:
      return "nd";
    case 3:
      return "rd";
    default:
      return "th";
  }
}

function formatDigestHeaderDate(value, empty = "") {
  if (!value) {
    return empty;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return empty;
  }
  const day = parsed.getDate();
  const weekday = parsed.toLocaleDateString("en-GB", { weekday: "long" });
  const month = parsed.toLocaleDateString("en-GB", { month: "long" });
  const year = parsed.getFullYear();
  return weekday + " " + day + ordinalSuffix(day) + " " + month + " " + year;
}

function scoreDisplayPercent(finalScore) {
  const raw = Number(finalScore);
  const score = Number.isFinite(raw) ? raw : 0;
  return Math.max(0, Math.min(100, Math.round(score * 100)));
}

// Show every author up to maxNamed; beyond that, collapse to "First author et al.".
function formatAuthors(authors, maxNamed = 3) {
  if (!Array.isArray(authors) || authors.length === 0) {
    return "";
  }
  const names = authors.map((name) => String(name || "").trim()).filter(Boolean);
  if (names.length === 0) {
    return "";
  }
  if (names.length > maxNamed) {
    return names[0] + " et al.";
  }
  return names.join(", ");
}

function createPaperByline(authors, publishedAt, className) {
  const authorsText = formatAuthors(authors);
  const dateText = formatShortDate(publishedAt, "");
  if (!authorsText && !dateText) {
    return null;
  }

  const byline = document.createElement("div");
  byline.className = className;

  if (authorsText) {
    byline.append(authorsText);
  }

  if (dateText) {
    if (authorsText) {
      byline.append(" (");
    }
    const time = document.createElement("time");
    if (publishedAt) {
      time.dateTime = String(publishedAt);
    }
    time.textContent = dateText;
    byline.appendChild(time);
    if (authorsText) {
      byline.append(")");
    }
  }

  return byline;
}

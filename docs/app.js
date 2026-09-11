(() => {
  const $ = (sel, el = document) => el.querySelector(sel);
  const cardsEl = $("#cards");
  const statusEl = $("#status");
  const emptyEl = $("#empty");
  const qEl = $("#q");
  const generatedEl = $("#generated");
  const playlistLink = $("#playlistLink");

  let data = null;

  function fmtDuration(sec) {
    if (!sec && sec !== 0) return "—";
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m`;
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function highlight(text, query) {
    const safe = escapeHtml(text);
    if (!query) return safe;
    const terms = query.trim().split(/\s+/).filter(Boolean);
    if (!terms.length) return safe;
    const re = new RegExp(
      `(${terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`,
      "gi"
    );
    return safe.replace(re, "<mark>$1</mark>");
  }

  function blurb(summary) {
    const one = summary.replace(/\s+/g, " ").trim();
    return one.length > 220 ? one.slice(0, 217) + "…" : one;
  }

  function termsOf(query) {
    return (query || "").toLowerCase().split(/\s+/).filter(Boolean);
  }

  function matches(ep, query) {
    if (!query) return true;
    const hay = [
      ep.title,
      ep.summary,
      ep.transcript || "",
      ...(ep.quotes || []).map((q) => q.text),
      ...(ep.quotes || []).map((q) => q.speaker || ""),
    ]
      .join("\n")
      .toLowerCase();
    return termsOf(query).every((term) => hay.includes(term));
  }

  function transcriptSnippet(ep, query, radius = 110) {
    const text = ep.transcript || "";
    const terms = termsOf(query);
    if (!text || !terms.length) return null;
    const lower = text.toLowerCase();
    let idx = -1;
    let hit = "";
    for (const term of terms) {
      const i = lower.indexOf(term);
      if (i !== -1 && (idx === -1 || i < idx)) {
        idx = i;
        hit = term;
      }
    }
    if (idx === -1) return null;
    const start = Math.max(0, idx - radius);
    const end = Math.min(text.length, idx + hit.length + radius);
    let snip = text.slice(start, end).replace(/\s+/g, " ").trim();
    if (start > 0) snip = "…" + snip;
    if (end < text.length) snip = snip + "…";
    return snip;
  }

  function matchSources(ep, query) {
    const terms = termsOf(query);
    if (!terms.length) return [];
    const sources = [];
    const title = (ep.title || "").toLowerCase();
    const summary = (ep.summary || "").toLowerCase();
    const transcript = (ep.transcript || "").toLowerCase();
    const quotes = (ep.quotes || []).map((q) => (q.text || "").toLowerCase());
    if (terms.every((t) => title.includes(t))) sources.push("title");
    if (terms.every((t) => summary.includes(t))) sources.push("summary");
    if (quotes.some((q) => terms.every((t) => q.includes(t)))) sources.push("quote");
    if (terms.every((t) => transcript.includes(t))) sources.push("transcript");
    else if (terms.some((t) => transcript.includes(t))) sources.push("transcript");
    return sources;
  }

  function openCard(card, open = true) {
    if (!card) return;
    card.classList.toggle("open", open);
    const btn = card.querySelector("button.btn[data-toggle]");
    if (btn) btn.textContent = open ? "Collapse" : "Expand";
  }

  // Single delegated click handler — nested data-toggle used to fire twice (open then close).
  cardsEl.addEventListener("click", (e) => {
    if (e.target.closest("a")) return;

    const openHit = e.target.closest("[data-open-episode]");
    if (openHit) {
      e.preventDefault();
      e.stopPropagation();
      const id = openHit.getAttribute("data-id");
      const card = document.getElementById(`ep-${id}`);
      if (!card) return;
      openCard(card, true);
      card.scrollIntoView({ behavior: "smooth", block: "start" });
      const mark = card.querySelector("[data-transcript] mark");
      if (mark) mark.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }

    const toggle = e.target.closest("[data-toggle]");
    if (!toggle || !cardsEl.contains(toggle)) return;
    e.preventDefault();
    const card = toggle.closest(".card");
    openCard(card, !card.classList.contains("open"));
  });

  function render(query = "") {
    const eps = data.episodes.filter((ep) => matches(ep, query));
    statusEl.textContent = query
      ? `${eps.length} of ${data.episodes.length} episodes match`
      : `${data.episodes.length} episodes · full transcripts searchable`;
    emptyEl.classList.toggle("hidden", eps.length > 0);

    cardsEl.innerHTML = eps
      .map((ep) => {
        const sources = query ? matchSources(ep, query) : [];
        const snip = query ? transcriptSnippet(ep, query) : null;
        const quotes = (ep.quotes || [])
          .map(
            (q) => `
          <li class="quote">
            <p class="quote-text">“${highlight(q.text, query)}”</p>
            <div class="quote-meta">
              <span class="speaker ${escapeHtml(q.speaker || "Unknown")}">${escapeHtml(
                q.speaker || "Unknown"
              )}</span>
              <span>${q.timestamp ? escapeHtml(q.timestamp) : "—"}</span>
            </div>
          </li>`
          )
          .join("");

        const sourceBadges = sources.length
          ? `<div class="hit-sources">${sources
              .map((s) => `<span class="badge">${escapeHtml(s)}</span>`)
              .join("")}</div>`
          : "";

        const snipBlock =
          snip && sources.includes("transcript")
            ? `<button type="button" class="transcript-hit" data-open-episode data-id="${escapeHtml(
                ep.id
              )}">
            <span class="hit-label">Transcript match</span>
            <span class="hit-snip">${highlight(snip, query)}</span>
            <span class="hit-cta">Open episode ↓</span>
          </button>`
            : "";

        const transcriptHighlighted = query
          ? highlight(ep.transcript || "", query)
          : escapeHtml(ep.transcript || "No transcript available.");

        return `
        <article class="card ${query ? "hit-card" : ""}" id="ep-${escapeHtml(
          ep.id
        )}" data-id="${escapeHtml(ep.id)}">
          <div class="card-head">
            <img class="thumb" src="${escapeHtml(ep.thumbnail)}" alt="" loading="lazy" />
            <div class="card-main">
              <div class="card-meta">
                <span>${escapeHtml(ep.uploadDate || "undated")}</span>
                <span>${fmtDuration(ep.durationSec)}</span>
                <span>${(ep.quotes || []).length} quotes</span>
                <span>${Math.round(((ep.transcript || "").length) / 1000)}k chars transcript</span>
              </div>
              <h2 class="card-title">${highlight(ep.title, query)}</h2>
              <p class="blurb">${highlight(blurb(ep.summary), query)}</p>
              ${sourceBadges}
              ${snipBlock}
              <div class="actions">
                <button type="button" class="btn" data-toggle>Expand</button>
                <a class="btn btn-yt" href="${escapeHtml(
                  ep.url
                )}" target="_blank" rel="noopener">Watch on YouTube ↗</a>
              </div>
            </div>
          </div>
          <div class="card-body">
            <h3 class="section-label">Summary</h3>
            <div class="summary">${highlight(ep.summary, query)}</div>
            <h3 class="section-label">Quotes</h3>
            <ul class="quotes">${quotes}</ul>
            <h3 class="section-label">Full transcript</h3>
            <div class="transcript" data-transcript>${transcriptHighlighted}</div>
          </div>
        </article>`;
      })
      .join("");

    if (query.trim()) {
      cardsEl.querySelectorAll(".card").forEach((card) => openCard(card, true));
      const first = cardsEl.querySelector(".card");
      if (first) {
        requestAnimationFrame(() => {
          first.scrollIntoView({ behavior: "smooth", block: "nearest" });
          const mark = first.querySelector(".transcript mark, .quote-text mark, .summary mark");
          if (mark) mark.scrollIntoView({ behavior: "smooth", block: "center" });
        });
      }
    }
  }

  fetch("episodes.json")
    .then((r) => {
      if (!r.ok) throw new Error(`Failed to load episodes.json (${r.status})`);
      return r.json();
    })
    .then((json) => {
      data = json;
      playlistLink.href = json.playlist || "#";
      if (json.generatedAt) {
        try {
          generatedEl.textContent = `Generated ${new Date(json.generatedAt).toLocaleString()}`;
        } catch {
          generatedEl.textContent = "";
        }
      }
      const params = new URLSearchParams(location.search);
      const initialQ = params.get("q") || "";
      if (initialQ) qEl.value = initialQ;
      render(initialQ);
      qEl.addEventListener("input", () => {
        const q = qEl.value;
        const url = new URL(location.href);
        if (q) url.searchParams.set("q", q);
        else url.searchParams.delete("q");
        history.replaceState(null, "", url);
        render(q);
      });
      qEl.focus();
    })
    .catch((err) => {
      statusEl.textContent = String(err.message || err);
    });
})();

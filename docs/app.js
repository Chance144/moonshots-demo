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
    const re = new RegExp(`(${terms.map(t => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "gi");
    return safe.replace(re, "<mark>$1</mark>");
  }

  function blurb(summary) {
    const one = summary.replace(/\s+/g, " ").trim();
    return one.length > 220 ? one.slice(0, 217) + "…" : one;
  }

  function matches(ep, query) {
    if (!query) return true;
    const hay = [
      ep.title,
      ep.summary,
      ...ep.quotes.map(q => q.text),
      ...ep.quotes.map(q => q.speaker || ""),
    ]
      .join("\n")
      .toLowerCase();
    return query
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean)
      .every(term => hay.includes(term));
  }

  function render(query = "") {
    const eps = data.episodes.filter(ep => matches(ep, query));
    statusEl.textContent = query
      ? `${eps.length} of ${data.episodes.length} episodes match`
      : `${data.episodes.length} episodes`;
    emptyEl.classList.toggle("hidden", eps.length > 0);
    cardsEl.innerHTML = eps
      .map(ep => {
        const quotes = ep.quotes
          .map(
            q => `
          <li class="quote">
            <p class="quote-text">“${highlight(q.text, query)}”</p>
            <div class="quote-meta">
              <span class="speaker ${escapeHtml(q.speaker || "Unknown")}">${escapeHtml(q.speaker || "Unknown")}</span>
              <span>${q.timestamp ? escapeHtml(q.timestamp) : "—"}</span>
            </div>
          </li>`
          )
          .join("");
        return `
        <article class="card ${query ? "hit-card" : ""}" data-id="${escapeHtml(ep.id)}">
          <div class="card-head" data-toggle>
            <img class="thumb" src="${escapeHtml(ep.thumbnail)}" alt="" loading="lazy" />
            <div class="card-main">
              <div class="card-meta">
                <span>${escapeHtml(ep.uploadDate || "undated")}</span>
                <span>${fmtDuration(ep.durationSec)}</span>
                <span>${ep.quotes.length} quotes</span>
              </div>
              <h2 class="card-title">${highlight(ep.title, query)}</h2>
              <p class="blurb">${highlight(blurb(ep.summary), query)}</p>
              <div class="actions">
                <button type="button" class="btn" data-toggle>Expand</button>
                <a class="btn btn-yt" href="${escapeHtml(ep.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Watch on YouTube ↗</a>
              </div>
            </div>
          </div>
          <div class="card-body">
            <h3 class="section-label">Summary</h3>
            <div class="summary">${highlight(ep.summary, query)}</div>
            <h3 class="section-label">Quotes</h3>
            <ul class="quotes">${quotes}</ul>
          </div>
        </article>`;
      })
      .join("");

    cardsEl.querySelectorAll("[data-toggle]").forEach(el => {
      el.addEventListener("click", e => {
        if (e.target.closest("a")) return;
        const card = el.closest(".card");
        const open = card.classList.toggle("open");
        const btn = card.querySelector("button.btn");
        if (btn) btn.textContent = open ? "Collapse" : "Expand";
      });
    });
  }

  fetch("episodes.json")
    .then(r => {
      if (!r.ok) throw new Error(`Failed to load episodes.json (${r.status})`);
      return r.json();
    })
    .then(json => {
      data = json;
      playlistLink.href = json.playlist || "#";
      if (json.generatedAt) {
        try {
          generatedEl.textContent = `Generated ${new Date(json.generatedAt).toLocaleString()}`;
        } catch {
          generatedEl.textContent = "";
        }
      }
      render("");
      qEl.addEventListener("input", () => render(qEl.value));
      qEl.focus();
    })
    .catch(err => {
      statusEl.textContent = String(err.message || err);
    });
})();

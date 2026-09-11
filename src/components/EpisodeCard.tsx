import { Link } from "react-router-dom";
import { highlight } from "../lib/search";
import type { Episode } from "../types";

function formatDate(iso: string): string {
  if (!iso) return "";
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function EpisodeCard({
  episode,
  query,
  quoteHits,
}: {
  episode: Episode;
  query: string;
  quoteHits: number[];
}) {
  const snippet = episode.summary.split(/\n\n/)[0] ?? episode.summary;
  const preview = snippet.length > 280 ? `${snippet.slice(0, 277).trim()}…` : snippet;
  const matchedQuote =
    quoteHits.length > 0 ? episode.quotes[quoteHits[0]] : episode.quotes[0];
  const q = query.trim();

  return (
    <article className="card">
      <Link to={`/episode/${episode.id}${q ? `?q=${encodeURIComponent(q)}` : ""}`} className="card-link">
        <div className="thumb-wrap">
          <img src={episode.thumbnail} alt="" />
          {episode.durationLabel && <span className="duration">{episode.durationLabel}</span>}
        </div>
        <div className="card-body">
          <p className="kicker">
            {episode.episodeNumber ? `EP ${episode.episodeNumber}` : "Moonshots"} ·{" "}
            {formatDate(episode.publishedAt)}
          </p>
          <h2 dangerouslySetInnerHTML={{ __html: highlight(episode.title, query) }} />
          <p
            className="card-summary"
            dangerouslySetInnerHTML={{ __html: highlight(preview, query) }}
          />
          {matchedQuote && (
            <p className="card-quote">
              <span className="card-quote-mark">“</span>
              <span
                dangerouslySetInnerHTML={{
                  __html: highlight(matchedQuote.text, query),
                }}
              />
              <span className="card-quote-time"> {matchedQuote.timestamp}</span>
            </p>
          )}
        </div>
      </Link>
    </article>
  );
}

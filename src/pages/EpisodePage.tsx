import { Link, Navigate, useParams, useSearchParams } from "react-router-dom";
import { highlight } from "../lib/search";
import { episodeDate, episodeDuration, episodeUrl } from "../types";
import type { Episode } from "../types";

function formatDate(iso: string): string {
  if (!iso) return "";
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

export function EpisodePage({ episodes }: { episodes: Episode[] }) {
  const { id } = useParams();
  const [params] = useSearchParams();
  const episode = episodes.find((item) => item.id === id);
  if (!episode) return <Navigate to="/" replace />;

  const query = params.get("q") ?? "";

  return (
    <main className="page detail">
      <Link to={query ? `/?q=${encodeURIComponent(query)}` : "/"} className="back">
        ← All episodes
      </Link>

      <div className="detail-hero">
        <img src={episode.thumbnail} alt="" className="detail-thumb" />
        <div>
          {episode.episodeNumber && <p className="kicker">Episode {episode.episodeNumber}</p>}
          <h1>{episode.title}</h1>
          <p className="meta">
            {formatDate(episodeDate(episode))}
            {episodeDuration(episode) ? ` · ${Math.floor((episodeDuration(episode) || 0) / 60)} min` : ""}
            {episode.channel ? ` · ${episode.channel}` : ""}
          </p>
          <a className="watch" href={episodeUrl(episode)} target="_blank" rel="noreferrer">
            Watch on YouTube ↗
          </a>
        </div>
      </div>

      <section>
        <h2>Summary</h2>
        <p className="source-note">
          {episode.summary.split(/\s+/).length} words · from the episode captions
          {episode.transcript ? ` · ${Math.round(episode.transcript.length / 1000)}k-char transcript` : ""}
        </p>
        {episode.summary.split("\n\n").map((para) => (
          <p
            key={para.slice(0, 40)}
            className="summary"
            dangerouslySetInnerHTML={{ __html: highlight(para, query) }}
          />
        ))}
      </section>

      <section>
        <h2>Top quotes</h2>
        <ol className="quotes">
          {episode.quotes.map((quote) => (
            <li key={`${quote.seconds}-${quote.text.slice(0, 24)}`}>
              <blockquote>
                <p dangerouslySetInnerHTML={{ __html: highlight(quote.text, query) }} />
                <footer>
                  {quote.speaker ? <span className="speaker">{quote.speaker}</span> : null}
                  <a
                    href={`${episodeUrl(episode)}${quote.seconds ? `&t=${quote.seconds}s` : ""}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {quote.timestamp}
                  </a>
                </footer>
              </blockquote>
            </li>
          ))}
        </ol>
      </section>

      {episode.transcript && (
        <section>
          <h2>Full transcript</h2>
          <p
            className="summary"
            dangerouslySetInnerHTML={{ __html: highlight(episode.transcript, query) }}
          />
        </section>
      )}
    </main>
  );
}

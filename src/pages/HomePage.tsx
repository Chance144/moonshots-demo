import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { EpisodeCard } from "../components/EpisodeCard";
import { searchEpisodes } from "../lib/search";
import type { Episode } from "../types";

export function HomePage({ episodes }: { episodes: Episode[] }) {
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const hits = useMemo(() => searchEpisodes(episodes, query), [episodes, query]);
  const searching = query.trim().length >= 2;

  return (
    <main className="page">
      <section className="hero">
        <h1>Search the last five Moonshots.</h1>
        <p className="lede">
          Live demo for the WSU faculty seminar. Each card opens a real episode
          summary and the top quotes pulled from the YouTube English captions —
          nothing fabricated.
        </p>
        <label className="search">
          <span className="search-label">Search titles, summaries, and quotes</span>
          <input
            autoFocus
            type="search"
            placeholder="Try AGI, Cybercab, Navier-Stokes, Waymo…"
            value={query}
            onChange={(e) => {
              const next = e.target.value;
              if (next) setParams({ q: next }, { replace: true });
              else setParams({}, { replace: true });
            }}
          />
        </label>
        <p className="result-count" aria-live="polite">
          {searching
            ? `${hits.length} episode${hits.length === 1 ? "" : "s"} match “${query.trim()}”`
            : `${episodes.length} newest episodes`}
        </p>
      </section>

      {hits.length === 0 ? (
        <p className="empty">No matches. Try a single keyword from a title or quote.</p>
      ) : (
        <ul className="card-grid">
          {hits.map((hit) => (
            <li key={hit.episode.id}>
              <EpisodeCard
                episode={hit.episode}
                query={query}
                quoteHits={hit.matched.quotes}
              />
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

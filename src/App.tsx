import { useEffect, useState } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { EpisodePage } from "./pages/EpisodePage";
import { HomePage } from "./pages/HomePage";
import type { Episode, EpisodeCatalog } from "./types";

export default function App() {
  const [episodes, setEpisodes] = useState<Episode[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/episodes.json")
      .then((res) => {
        if (!res.ok) throw new Error(`Could not load episodes.json (${res.status})`);
        return res.json() as Promise<EpisodeCatalog>;
      })
      .then((data) => setEpisodes(data.episodes))
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="brand-kicker">WSU faculty seminar</span>
          <span className="brand-title">Moonshots Archive</span>
        </Link>
        <p className="brand-meta">
          Last 5 episodes · Peter H. Diamandis · searchable transcripts
        </p>
      </header>

      {error && <p className="banner error">{error}. Run <code>npm run data</code> then refresh.</p>}
      {!episodes && !error && <p className="banner">Loading episodes…</p>}

      {episodes && (
        <Routes>
          <Route path="/" element={<HomePage episodes={episodes} />} />
          <Route path="/episode/:id" element={<EpisodePage episodes={episodes} />} />
        </Routes>
      )}

      <footer className="footer">
        <p>
          Search covers titles, summaries, quotes, and full transcripts.
          Source playlist:{" "}
          <a href="https://www.youtube.com/playlist?list=PL1wpF5k0tdIve4idTp3-FX2ZY7ks_BKeU">
            Moonshots with Peter Diamandis
          </a>
          .
        </p>
      </footer>
    </div>
  );
}

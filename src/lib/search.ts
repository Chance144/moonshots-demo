import type { Episode } from "../types";

export type SearchHit = {
  episode: Episode;
  score: number;
  matched: {
    title: boolean;
    summary: boolean;
    quotes: number[];
    transcript: boolean;
  };
};

function normalize(value: string): string {
  return value.toLowerCase();
}

export function tokenizeQuery(query: string): string[] {
  return query
    .toLowerCase()
    .split(/[^a-z0-9%$.]+/i)
    .map((t) => t.trim())
    .filter((t) => t.length >= 2);
}

export function searchEpisodes(episodes: Episode[], query: string): SearchHit[] {
  const terms = tokenizeQuery(query);
  if (terms.length === 0) {
    return episodes.map((episode) => ({
      episode,
      score: 0,
      matched: { title: false, summary: false, quotes: [], transcript: false },
    }));
  }

  return episodes
    .map((episode) => {
      const title = normalize(episode.title);
      const summary = normalize(episode.summary);
      const transcript = normalize(episode.transcript || "");
      const quoteTexts = episode.quotes.map((q) => normalize(q.text));

      let score = 0;
      const titleHit = terms.every((t) => title.includes(t));
      const summaryHit = terms.every((t) => summary.includes(t));
      const transcriptHit = Boolean(transcript) && terms.every((t) => transcript.includes(t));
      const quoteHits: number[] = [];

      if (titleHit) score += 8;
      else score += terms.filter((t) => title.includes(t)).length * 2;

      if (summaryHit) score += 4;
      else score += terms.filter((t) => summary.includes(t)).length;

      if (transcriptHit) score += 3;
      else score += terms.filter((t) => transcript.includes(t)).length;

      quoteTexts.forEach((text, index) => {
        const hits = terms.filter((t) => text.includes(t)).length;
        if (hits === terms.length) {
          quoteHits.push(index);
          score += 5;
        } else if (hits > 0) {
          quoteHits.push(index);
          score += hits;
        }
      });

      return {
        episode,
        score,
        matched: {
          title: titleHit,
          summary: summaryHit,
          quotes: quoteHits,
          transcript: transcriptHit,
        },
      };
    })
    .filter((hit) => hit.score > 0)
    .sort((a, b) => b.score - a.score);
}

export function highlight(text: string, query: string): string {
  const terms = tokenizeQuery(query);
  if (!terms.length) return escapeHtml(text);
  const pattern = new RegExp(`(${terms.map(escapeRegExp).join("|")})`, "ig");
  return escapeHtml(text).replace(pattern, "<mark>$1</mark>");
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

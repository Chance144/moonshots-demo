export type Quote = {
  text: string;
  timestamp: string;
  seconds?: number;
  speaker: string | null;
};

export type Episode = {
  id: string;
  title: string;
  url?: string;
  youtubeUrl?: string;
  uploadDate?: string;
  publishedAt?: string;
  durationSec?: number | null;
  durationSeconds?: number | null;
  durationLabel?: string;
  channel?: string;
  thumbnail: string;
  summary: string;
  quotes: Quote[];
  transcript?: string;
  episodeNumber?: number | null;
  summaryWordCount?: number;
  transcriptSource?: string | null;
  transcriptCueCount?: number;
  description?: string;
};

export type EpisodeCatalog = {
  generatedAt?: string;
  source?: string;
  playlist: string;
  channel?: string;
  note?: string;
  episodes: Episode[];
};

export function episodeUrl(episode: Episode): string {
  return episode.url || episode.youtubeUrl || `https://www.youtube.com/watch?v=${episode.id}`;
}

export function episodeDate(episode: Episode): string {
  return episode.uploadDate || episode.publishedAt || "";
}

export function episodeDuration(episode: Episode): number | null {
  const value = episode.durationSec ?? episode.durationSeconds;
  return typeof value === "number" ? value : null;
}

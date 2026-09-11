export type Quote = {
  text: string;
  timestamp: string;
  seconds: number;
  speaker: string | null;
};

export type Episode = {
  id: string;
  title: string;
  episodeNumber: number | null;
  publishedAt: string;
  durationSeconds: number | null;
  durationLabel: string;
  channel: string;
  thumbnail: string;
  youtubeUrl: string;
  description: string;
  summary: string;
  summaryWordCount: number;
  quotes: Quote[];
  transcriptSource: string | null;
  transcriptCueCount: number;
};

export type EpisodeCatalog = {
  generatedAt: string;
  source: string;
  playlist: string;
  channel: string;
  note: string;
  episodes: Episode[];
};

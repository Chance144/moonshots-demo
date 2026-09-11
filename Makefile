PLAYLIST_LIMIT ?= 5

.PHONY: scrape scrape-ids process data pages serve

# Refresh last N Moonshots videos from the official playlist.
scrape:
	python3 scripts/scrape.py --playlist --limit $(PLAYLIST_LIMIT)

scrape-ids:
	python3 scripts/scrape.py --ids vAgEf4jX_1o,1DB_QDiviH4,JywXvB8PpTs,tfBEWh9ibfU,0mOXQ4_kY04

# Attach transcripts from raw/ and copy catalog to site/ + docs/ (Pages).
process:
	python3 scripts/process.py

data: scrape process

pages:
	python3 scripts/process.py

serve:
	python3 -m http.server 4173 --directory docs

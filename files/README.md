# Sales Intelligence Automator

A prototype tool that cuts down pre-call research time for sales teams. You paste in a list of company URLs or names, it scrapes their websites, runs them through a local language model, and spits out a structured brief for each one — what they do, who they sell to, whether they look like a viable B2B lead, and three questions worth asking on a discovery call.

No external API, no usage costs, no rate limits. The model runs on your machine.

---

## Project Structure

```
files/
├── app.py               # Flask server and job orchestration
├── scraper.py           # Web scraping and content cleaning
├── analyzer.py          # Local model inference (HuggingFace)
├── storage.py           # JSON-based result persistence
├── templates/
│   └── index.html       # Frontend (single HTML file)
├── data/
│   └── results.json     # Generated output store
└── requirements.txt
```

---

## Dependencies

- **Flask** — web framework
- **requests + beautifulsoup4 + lxml** — scraping and HTML parsing
- **transformers + torch + accelerate** — local model runtime (HuggingFace)

---

## Installation

```bash
git clone <your-repo>
cd files
pip install -r requirements.txt
```

The language model (`Qwen2.5-1.5B-Instruct`, ~3GB) downloads automatically the first time you run an analysis. After that it's cached locally and loads in a few seconds.

---

## Running

```bash
python app.py
```

Open **http://localhost:5000**.

No API key or environment variables needed.

To swap to a larger model for better output quality:

```bash
set HF_MODEL=Qwen/Qwen2.5-3B-Instruct
python app.py
```

---

## Using the Interface

1. Paste leads into the text box — one per line, URLs or company names or both
2. Click **Run Analysis**
3. Watch the progress bar as each lead gets processed
4. Expand any result card to see the full brief
5. Use the filter buttons to sort by qualification status
6. **Load Sample Leads** fills in the 15 leads from the assignment spec

Results persist between sessions. **Clear Results** wipes them.

---

## Design Notes

### Architecture

The pipeline has three stages: scrape → analyze → store. Flask runs a background thread per job so the UI stays responsive during processing. The frontend polls `/status/<job_id>` every 1.2 seconds and updates the progress bar. Results go into `data/results.json` (a stand-in for a proper database), which means they survive page reloads and appear automatically on next visit.

The `analyze_lead` function in `analyzer.py` returns plain Python dicts, making it easy to swap the JSON file for a database write or a CRM API call downstream. The Flask routes are thin enough to drop into a larger FastAPI or Django app without much rework.

### Tool Choices

Flask was the obvious choice here — no ORM, no auth, no complex routing, so a microframework is the right fit. BeautifulSoup handles malformed HTML well, which matters because small business sites tend to be messy. The boilerplate removal works by stripping noise tags (`nav`, `footer`, `script`, `style`) first, then doing a second pass to decompose any container whose CSS class or ID matches patterns like `cookie`, `banner`, `sidebar`, `newsletter`. It's heuristic-based but covers the vast majority of cases in this dataset.

For the language model, I went with `Qwen2.5-1.5B-Instruct` via HuggingFace Transformers. It runs on CPU without a GPU, fits in under 4GB of RAM, and follows structured JSON instructions reliably for its size. Using a local model means no API key, no cost, and no rate limit — which matters when running a full batch of leads. The system prompt enforces JSON-only output; a two-pass parser (direct `json.loads`, then a regex fallback to extract the outermost `{...}` block) handles any stray preamble text the model occasionally adds.

### Edge Cases

For company name inputs without URLs (e.g. "Joe's Backyard Landscaping – Phoenix AZ"), the scraper slugifies the name and tries a `.com` guess. If that 404s or returns no usable content, the lead still gets analyzed — the model just works from the name and industry context alone, which is usually enough for a basic qualification. Each lead runs inside a `try/except` so one failure doesn't stop the rest of the batch. The `is_boilerplate_element` function guards against decomposed BeautifulSoup tags that have `attrs=None`, which causes crashes on certain site layouts in newer BS4 versions.

### What I'd Improve With More Time

- **Parallel scraping** using `asyncio` + `aiohttp` — right now it's sequential, so large batches are slow
- **Better URL resolution for name-only leads** — a DuckDuckGo or SerpAPI lookup would be more reliable than slugifying the company name
- **Multi-page crawling** — follow `/about`, `/services`, and `/team` links to get richer content before sending to the model
- **PostgreSQL backend** with proper pagination and search in the UI
- **CSV/CRM export** — one-click download and a webhook for pushing qualified leads to HubSpot or Salesforce
- **Confidence scores** alongside the Yes/No decision for easier prioritization

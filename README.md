# Student Opportunity Intelligence Agent

A web dashboard that searches the live web for internships, hackathons, scholarships, competitions,
workshops and fellowships, then ranks them for **your** profile (branch, year, skills, location) and shows
*why* each one matches. It shows deadlines it can find and lets you save the ones you like.

Everything shown comes from real SerpApi (Google) search results or from what you type yourself. The app
never invents opportunities, dates, deadlines, scores or links.

## Features

**Search and ranking**
- Live Google search through [SerpApi](https://serpapi.com), driven by your profile and a plain-English request
- Eligibility analysis: Likely Eligible, Eligibility Unclear, Likely Not Eligible (includes graduation-year checks)
- Transparent match score out of 100, with a breakdown
- NEW badge for postings from the last 7 days (when SerpApi returns a posting date)
- Noise filtering: profile pages, forums, social sites, personal portfolios, outdated postings, results that do
  not mention your requested topic or type
- Duplicate merging: the same event found on several sites becomes one card

**Interface**
- Sidebar with your student profile, recent searches and a light/dark mode switch
- Statistics: Total found, Likely eligible, New this week, Average match, Deadlines soon
- Opportunity cards showing match score, eligibility, NEW badge, posted date, deadline, location and matched skills
- Details window with the score breakdown, eligibility reasoning and the searches that found the result
- Keyword search, advanced filters (type, eligibility, minimum score, new this week, deadline within 14 days,
  has a deadline) and sorting (Newest + Match, Match Score, Deadline)
- Save/bookmark opportunities, with source links on every card
- Responsive layout, live progress while searching, and clear empty and error states

## How it works

```
Browser (index.html)
        |  POST /api/search   (streams live progress)
        v
Flask server (server.py)
        |
        v
agent.py:  query_planner -> SerpApi -> filter noise -> merge duplicates
           -> eligibility -> scoring -> ranked results
```

The SerpApi key stays on the server. The browser never sees it.

**Match score (100 points):** skills 35, academic year 20, branch 15, opportunity type 15, location 10,
freshness 5.

## Project structure

| File | Purpose |
|---|---|
| `server.py` | Flask server: serves the page and the `/api/search` endpoint |
| `index.html` | The whole interface: profile, search, filters, cards, details window, saved |
| `agent.py` | Pipeline that connects all the steps below |
| `query_planner.py` | Turns your profile and request into search queries |
| `serpapi_client.py` | SerpApi wrapper, API key handling, error mapping |
| `eligibility.py` | Eligibility signals and opportunity type detection |
| `scoring.py` | Transparent match scoring |
| `utils.py` | De-duplication, filtering, deadline and date parsing |
| `models.py` | Data models (`StudentProfile`, `Opportunity`) |
| `requirements.txt` | Python dependencies |
| `.env.example` | Template for your API key file |

## Setup

You need Python 3.10 or newer (developed on Python 3.12/3.13) and a SerpApi key.

```bash
git clone <repository-url>
cd <repository-folder>

python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# macOS / Linux:       source .venv/bin/activate

pip install -r requirements.txt
```

### Add your SerpApi key

1. Create a free account at https://serpapi.com and copy your key from **Manage API Key**.
2. Copy `.env.example` to `.env` (same folder as `server.py`) and put your key in it:

   ```
   SERPAPI_KEY=your_real_key_here
   ```

   No quotes, no spaces. Every team member uses their own key. **Never commit `.env`.**

## Run

```bash
python server.py
```

Open http://127.0.0.1:5000 (press Ctrl+F5 after updating files). To use another port, set the `PORT`
environment variable first, for example `PORT=5055` (PowerShell: `$env:PORT="5055"`).

## Using the app

1. Fill in the student profile in the sidebar.
2. In **Discover**, type what you want, for example:
   `Find Python internships suitable for a 2nd-year CSE student with no prior work experience.`
3. Review the cards. Use **Details** for the score breakdown and **Save** to bookmark the ones you want.
4. Use **Filters** and **Sort by** to narrow the list, and **Open page** to apply on the official site.

Tips: naming a type (hackathons, internships...) searches only that type. Naming a topic (Python, ML...) keeps
only results that mention it.

## API

| Method | Path | Description |
|---|---|---|
| GET | `/` | The web app |
| GET | `/api/status` | `{"configured": true/false}`, whether a SerpApi key was found |
| POST | `/api/search` | Body: `{"request": "...", "profile": {...}}`. Streams newline-delimited JSON: `progress`, then `done` or `error` |

## Data and privacy

- Saved items, your profile, recent searches and the theme are stored in **your browser's localStorage**. They are not sent anywhere and do not sync between devices or browsers.
- Search requests go from the server to SerpApi using your key.

## Known limits

- **SerpApi quota:** one search in the app runs up to 6 SerpApi queries, so it uses up to 6 of your searches.
- Eligibility and skill detection read only the short search snippet, not the full page. Always confirm details
  on the official page using **Open page**.
- Posted dates appear only when SerpApi returns them. Deadlines appear only when found in the snippet text.
- Search results are kept in memory only, so they are cleared when you reload the page. Saved items stay.

## Troubleshooting

| Problem | Fix |
|---|---|
| "API key missing" | Create `.env` with `SERPAPI_KEY=...` next to `server.py`, then restart |
| "API key rejected" | Re-copy the key from SerpApi. Remove any old `SERPAPI_KEY` set in the terminal or Windows environment, which overrides `.env` |
| Page not updating | Stop all old servers, restart, press Ctrl+F5 |
| Port already in use | Run on another port with the `PORT` variable |
| "No result mentioned ..." | The request was too narrow. Reword it or drop the topic word |

## Contributing

1. Create a branch: `git checkout -b feature/short-description`
2. Keep changes focused, and test a real search before opening a pull request.
3. Do not commit `.env`, API keys or `__pycache__`.

## Team

Add team member names and roles here.

## License

Add a license here (for example MIT) before making the repository public.

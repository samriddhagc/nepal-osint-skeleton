# NepalOSINT — Open Source Intelligence Dashboard

A production-grade, real-time intelligence dashboard for Nepal's political landscape, elections, governance, and public data. Built with React, FastAPI, PostgreSQL, and Redis.

![Dashboard](docs/dashboard-preview.png)

## What is NepalOSINT?

NepalOSINT is a real-time OSINT (Open Source Intelligence) dashboard purpose-built for monitoring Nepal's:

- **Elections** — Live seat counts, party breakdowns, PR votes, constituency maps, swing analysis
- **Parliament** — MP profiles, session tracking, committee assignments, legislative activity
- **Governance** — Manifesto promise tracking (RSP 2082 verified against PDF), government decisions
- **News** — Multi-source aggregation from 10+ Nepali news outlets with deduplication
- **Public Data** — Weather, river levels, seismic activity, energy, aviation, market data
- **Social Media** — Twitter/X monitoring for political discourse

This is the **open-source skeleton** — a fully functional dashboard framework. The architecture supports extension with custom analysis modules, AI agents, and specialized intelligence features.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Frontend                      │
│  React 18 + TypeScript + Vite + Tailwind        │
│  Blueprint 5 Dark Theme + Zustand + React Query │
│  Widget-based Dashboard System                  │
├─────────────────────────────────────────────────┤
│                  Nginx Proxy                    │
├─────────────────────────────────────────────────┤
│                   Backend                       │
│  FastAPI + SQLAlchemy 2.0 Async + Alembic       │
│  Repository → Service → API Route pattern       │
│  JWT Auth (consumer/analyst/dev roles)          │
├──────────────┬──────────────────────────────────┤
│  PostgreSQL  │        Redis                     │
│  (primary)   │  (response cache + pub/sub)      │
└──────────────┴──────────────────────────────────┘
```

### Key Design Decisions

- **Widget System** — Every dashboard panel is a self-contained `<Widget>` component with standardized props, error boundaries, and loading states
- **Response Cache Middleware** — Redis-backed cache layer that serves identical GET responses to all users within TTL windows (the dashboard is read-only, so all users see the same data)
- **Multi-Source Ingestion** — Async scrapers for 10+ news sources, government APIs, market data, weather, river monitoring — all running on APScheduler intervals
- **Nepali Date Support** — Full Bikram Sambat (BS) ↔ Gregorian conversion utilities
- **Role-Based Access** — Three tiers: `consumer` (public), `analyst` (extended), `dev` (admin)

## Features

### Election Dashboard
- Live seat allocation with party-wise breakdown
- Interactive constituency map with vote margins
- PR (proportional representation) vote tracking
- Swing analysis and incumbency comparison
- Close races monitoring

### News Intelligence
- Real-time aggregation from Ekantipur, Ratopati, Republica, Himalayan Times, Kantipur TV, Nepali Times
- RSS + HTML scraping with intelligent deduplication
- Source reliability tracking
- Developing stories timeline

### Governance Tracker
- Manifesto promise tracking (verified against party PDFs)
- Government decisions and announcements
- Parliament session monitoring
- Know Your Neta (MP profile search)

### Public Data Monitoring
- Weather (all 77 districts)
- River levels and flood warnings
- Seismic activity
- Energy production and load-shedding
- Aviation (flights and incidents)
- Market data (NEPSE, gold, forex)

## Extending with AI Agents

The skeleton is designed to support AI-powered analyst agents. Here's how the agent workflow is architected:

### Agent Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Local Machine                             │
│                                                                  │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────────────┐   │
│  │  Scheduler   │───▸│  Agent Runner │───▸│  Claude / LLM API│   │
│  │  (cron)      │    │  (Python)     │    │  (analysis engine│   │
│  └─────────────┘    └──────┬───────┘    └────────────────────┘   │
│                            │                                     │
│                     GET data from server                         │
│                     POST results to server                       │
│                            │                                     │
├────────────────────────────┼─────────────────────────────────────┤
│                        Server                                    │
│                            │                                     │
│  ┌─────────────────────────▼──────────────────────────────────┐  │
│  │                    FastAPI Backend                         │  │
│  │                                                            │  │
│  │  GET  /api/v1/stories/export    → Raw stories for analysis │  │
│  │  GET  /api/v1/twitter/export    → Raw tweets for analysis  │  │
│  │  POST /api/v1/briefs/ingest     → Store analyst brief      │  │
│  │  POST /api/v1/promises/ingest   → Update promise statuses  │  │
│  │                                                            │  │
│  │  ┌──────────┐  ┌───────┐  ┌──────────────────────────┐     │  │
│  │  │PostgreSQL│  │ Redis │  │ APScheduler (scrapers)   │     │  │
│  │  └──────────┘  └───────┘  └──────────────────────────┘     │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                  Frontend (React)                          │  │
│  │  Displays agent results via dashboard widgets              │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### How Agents Work

1. **Data Collection** — The backend continuously scrapes 10+ sources (news, government, market data) on APScheduler intervals and stores raw data in PostgreSQL.

2. **Agent Runner** — A local script (or cron job) periodically calls export endpoints to fetch recent raw data:
   ```bash
   # Fetch latest stories and tweets
   curl -H "Authorization: Bearer $TOKEN" https://your-server/api/v1/stories/export?hours=4
   curl -H "Authorization: Bearer $TOKEN" https://your-server/api/v1/twitter/export?hours=4
   ```

3. **LLM Analysis** — The agent feeds raw data to an LLM (Claude, GPT, etc.) with structured prompts to produce:
   - **Intelligence Briefs** — Summarized situation reports with key developments, risk assessments, and recommended actions
   - **Promise Status Updates** — Cross-referencing news against manifesto promises to track fulfillment
   - **Anomaly Detection** — Flagging unusual patterns in data (e.g., sudden sentiment shifts, unusual government activity)

4. **Result Ingestion** — The agent POSTs structured results back to the backend:
   ```bash
   # Ingest an analyst brief
   curl -X POST https://your-server/api/v1/briefs/ingest \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"headline": "...", "summary": "...", "key_developments": [...], "risk_level": "medium"}'
   ```

5. **Dashboard Display** — Frontend widgets consume the ingested data via React Query hooks, showing briefs, promise tracker updates, and alerts in real-time.

### Building Your Own Agent

```python
"""Example: Simple analyst agent that generates intelligence briefs."""
import httpx
import anthropic  # or any LLM SDK

API_BASE = "https://your-server/api/v1"
TOKEN = "your-jwt-token"
headers = {"Authorization": f"Bearer {TOKEN}"}

async def run_analyst_agent():
    async with httpx.AsyncClient() as client:
        # 1. Fetch raw data
        stories = (await client.get(f"{API_BASE}/stories/export?hours=4", headers=headers)).json()
        tweets = (await client.get(f"{API_BASE}/twitter/export?hours=4", headers=headers)).json()

        # 2. Analyze with LLM
        llm = anthropic.Anthropic()
        analysis = llm.messages.create(
            model="claude-sonnet-4-20250514",
            messages=[{
                "role": "user",
                "content": f"""Analyze these Nepal news stories and tweets.
                Produce a structured intelligence brief with:
                - headline, summary, key_developments, risk_level
                Stories: {stories[:20]}
                Tweets: {tweets[:50]}"""
            }],
        )

        # 3. Post results back
        brief = parse_brief(analysis)  # Your parsing logic
        await client.post(f"{API_BASE}/briefs/ingest", json=brief, headers=headers)
```

### Agent Ideas

| Agent | Input | Output | Schedule |
|-------|-------|--------|----------|
| **Analyst Brief** | News stories + tweets | Situation report with risk assessment | Every 4 hours |
| **Promise Tracker** | News + government decisions | Promise status updates with evidence | Daily |
| **Anomaly Detector** | All data streams | Alerts for unusual patterns | Every 2 hours |
| **Sentiment Monitor** | Twitter + news | Political sentiment trends by party/topic | Every hour |
| **Election Predictor** | Polling data + news + social | Seat projections with confidence intervals | Daily |
| **Budget Tracker** | Government financial data | Spending anomalies and budget vs actual | Weekly |

## Quick Start

### Prerequisites
- Node.js 18+
- Python 3.11+
- PostgreSQL 15+
- Redis 7+

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env
# Edit .env with your database credentials

# Run migrations
alembic upgrade head

# Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Set API URL
echo "VITE_API_URL=http://localhost:8000" > .env.local

# Start dev server
npm run dev
```

### Docker (Recommended)

```bash
docker compose up -d
```

This starts PostgreSQL, Redis, backend, and frontend with Nginx.

## Project Structure

```
nepal-osint-skeleton/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard/          # Widget-based dashboard system
│   │   │   │   ├── Widget.tsx      # Base widget component
│   │   │   │   ├── widgets/        # 25+ public widgets
│   │   │   │   └── ...
│   │   │   ├── elections/          # Election visualization
│   │   │   ├── map/                # Leaflet map components
│   │   │   └── common/            # Shared UI primitives
│   │   ├── api/                    # API client & React Query hooks
│   │   ├── stores/                 # Zustand state management
│   │   ├── pages/                  # Route-level pages
│   │   └── lib/                    # Utilities (Nepali dates, etc.)
│   └── package.json
│
├── backend/
│   ├── app/
│   │   ├── api/v1/                # FastAPI route handlers
│   │   ├── core/                  # Database, Redis, WebSocket
│   │   ├── models/                # SQLAlchemy ORM models
│   │   ├── repositories/         # Data access layer
│   │   ├── schemas/              # Pydantic validation
│   │   ├── services/             # Business logic
│   │   ├── ingestion/            # Async scrapers (10+ sources)
│   │   ├── tasks/                # APScheduler jobs
│   │   └── utils/                # Nepali date, province mapping
│   ├── alembic/                  # Database migrations
│   └── requirements.txt
│
└── docker-compose.yml
```

## Data Sources

| Source | Type | Update Interval |
|--------|------|----------------|
| Ekantipur | News | 5 min |
| Ratopati | News | 5 min |
| Republica | News | 5 min |
| Himalayan Times | News | 5 min |
| Kantipur TV | News | 5 min |
| ECN (Election Commission) | Election Results | 30 sec |
| hr.parliament.gov.np | Parliament Data | 2 hrs |
| DHM Nepal | Weather | 15 min |
| DHM Nepal | River Levels | 15 min |
| NEPSE | Stock Market | 1 min |
| NRB | Forex Rates | 1 hr |
| Twitter/X | Social Media | 1 min |

## Widget System

Creating a new widget:

```tsx
import { Widget } from '../Widget';
import { Activity } from 'lucide-react';

export const MyWidget = memo(function MyWidget() {
  return (
    <Widget id="my-widget" icon={<Activity size={14} />}>
      <div style={{ padding: 16 }}>
        {/* Your widget content */}
      </div>
    </Widget>
  );
});
```

Register it in `widgets/index.tsx` to make it available on the dashboard.

## Contributing

We welcome contributions! Areas where help is especially valuable:

- **New data source scrapers** — Government ministries, provincial governments, municipal data
- **Data visualization** — Better charts, maps, and interactive displays
- **Nepali NLP** — Tokenization, entity recognition, sentiment analysis for Nepali text
- **AI Agents** — Build new analyst agents (see [Extending with AI Agents](#extending-with-ai-agents))
- **Testing** — Unit tests, integration tests, scraper reliability tests
- **Documentation** — API docs, architecture guides, deployment guides
- **Accessibility** — Screen reader support, keyboard navigation
- **Mobile** — Responsive design improvements

### Development Guidelines

1. Follow the Repository → Service → API Route pattern
2. All scrapers should be async and handle failures gracefully
3. Use Pydantic schemas for API request/response validation
4. Write type-safe TypeScript (no `any` types)
5. Use the `<Widget>` component for new dashboard panels
6. Test with the Nepali calendar — dates in Nepal use Bikram Sambat

## License

MIT License — see [LICENSE](LICENSE) for details.

## Acknowledgments

- Election data from the [Election Commission of Nepal](https://election.gov.np/)
- Parliament data from [hr.parliament.gov.np](https://hr.parliament.gov.np/)
- Weather and river data from the Department of Hydrology and Meteorology
- Built with [React](https://react.dev/), [FastAPI](https://fastapi.tiangolo.com/), [Blueprint](https://blueprintjs.com/), and [Tailwind CSS](https://tailwindcss.com/)

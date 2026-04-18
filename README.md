# AI Personal Finance Tracker

Local-first personal finance tracker with bank statement upload, smart categorization, analytics dashboard, budgeting, insights, forecasts, and exports.

## Stack

- **Backend:** FastAPI, SQLAlchemy, SQLite, Pandas, NumPy
- **Frontend:** React, Tailwind CSS, Recharts
- **AI hooks:** Ollama local LLM (default), OpenAI-compatible fallback

## Features

- Upload `.xlsx` / `.csv` bank statements with flexible column detection
- Data cleaning (null filtering, dedupe, date/amount normalization)
- Re-upload safety: duplicate statement rows are skipped automatically
- Smart category tagging with manual override + learning
- Dashboard: income/expense, category pie, monthly trends, merchant spend, recurring detection
- Insights engine: overspending + anomaly alerts
- Forecasting: next month expense/savings/balance
- Budget planning and budget-vs-actual monitoring
- Premium intelligence: financial health score, net-worth estimate, weekly recap, upcoming bill predictions
- Risk analytics: overspending alerts, spending pattern detection, and category anomaly detection
- AI advisor endpoint: actionable "Do / Avoid" suggestions from transaction analytics
- Goal planning: create savings goals and track progress milestones
- Merchant mapping manager: bulk-edit unique merchants and apply category rules globally
- Exports: transactions to Excel, summary to PDF
- Encrypted sensitive text fields at rest (description/merchant)

## Project Structure

```text
backend/
  app/
    main.py
    models.py
    services/
frontend/
  src/
    App.jsx
```

## Run Locally

## 1) Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
setup_ollama.bat
uvicorn app.main:app --reload --port 8005
```

Open API docs: `http://localhost:8005/docs`
If your frontend runs on a different dev port, update `CORS_ORIGINS` in `backend\.env` (comma-separated).  
For dynamic localhost ports, use `CORS_ORIGIN_REGEX=^https?://(localhost|127\.0\.0\.1)(:\d+)?$`.

## 2) Frontend

```bash
cd frontend
npm install
# optional when backend runs on non-default port
# set VITE_API_BASE_URL=http://localhost:8005
npm run dev
```

Open app: `http://localhost:5173` (or `5174` if Vite auto-switches)

## LLM Integration

Default setup uses **Ollama (free, local)**.

1) Install Ollama and start it:

```env
ollama serve
ollama pull qwen2.5:7b
```

2) Set `backend/.env`:

```env
ENABLE_REMOTE_LLM=true
LLM_PROVIDER=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5:7b
LLM_API_KEY=ollama
```

3) Restart backend.

Diagnostics:
- `GET /api/ai/diagnostics` should return `ok: true`.
- If diagnostics fails, run:
  - `ollama list` (model should include `qwen2.5:7b`)
  - `ollama run qwen2.5:7b "say ok"` (confirms model is usable)

If LLM is unavailable, app falls back to deterministic local suggestions.

## API Endpoints

- `POST /api/upload-statement`
- `GET /api/transactions`
- `PATCH /api/transactions/{id}/category`
- `GET /api/dashboard`
- `POST /api/insights/generate`
- `GET /api/insights`
- `GET /api/ai/advice`
- `GET /api/ai/diagnostics`
- `POST /api/forecast`
- `POST /api/budgets`
- `GET /api/budgets`
- `GET /api/premium/overview`
- `POST /api/goals`
- `GET /api/goals`
- `PATCH /api/goals/{id}/progress`
- `GET /api/merchant-mappings`
- `PUT /api/merchant-mappings/bulk`
- `GET /api/export/transactions.xlsx`
- `GET /api/export/summary.pdf`

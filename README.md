# Chotu-Gyani (छोटू ज्ञानी)
*Your business. Your language. Your AI.*

Chotu-Gyani is an AI-powered voice & conversational operating system designed for Indian small businesses (Vyapaaris, retailers, distributors). It allows users to manage customers, ledger balances, invoices, payment commitments (*vaada*), and automated payment reminders (*takaada*) speaking or typing in **Hindi, English, or Hinglish**.

---

## 🚀 Architecture Overview

- **Backend (`/backend`)**:
  - FastAPI modular monolith with Pydantic v2
  - PostgreSQL 16 (asyncpg + SQLAlchemy 2.0) with `pg_trgm` fuzzy matching
  - Strict multi-tenancy enforced by `X-Business-ID` header and database constraints
  - Argon2id password hashing + rotating JWT tokens
  - Intent extraction pipeline with structured outputs and prompt injection defense
  - Two-phase pending action approval gate for any business-altering mutations
  - Voice STT / TTS provider adapters (`mock`, `groq`, `gnani`)

- **Frontend (`/frontend`)**:
  - React 19 + TypeScript + Vite + Tailwind CSS
  - In-browser microphone voice recording with STT & TTS playback
  - Real-time Pending Action preview & 1-click confirmation cards
  - Full Ledger Suite: Customers directory, Invoices & bills, Payment tracking, Reminders (WhatsApp/SMS/Call), Commitments
  - AI Agents Studio & Customizer with test sandbox
  - Audio Studio Workbench for STT and TTS testing
  - 1-Click Demo Login for instant testing

---

## ⚡ Quick Start

### 1. Start Database & Backend

In your terminal:
```powershell
cd backend

# Ensure database is running (PostgreSQL on port 5433 or configured in .env)
# Run Alembic migrations
uv run alembic upgrade head

# Seed synthetic demo business (Sharma Traders)
uv run python -m scripts.seed_demo_data

# Start FastAPI server on port 8000
uv run uvicorn app.main:app --reload --port 8000
```

### 2. Start Frontend

In a second terminal:
```powershell
cd frontend

# Install dependencies (already prepared)
npm install

# Start Vite dev server on port 3000
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 🔑 Demo Login

On the login page, you can either click the **"Login as Sharma Traders Owner"** button or enter:
- **Email:** `owner@sharmatraders.example.com`
- **Password:** `Demo12345`

### Sample Voice / Text Prompts to Try:
- *"Ramesh Gupta ka balance kitna hai?"*
- *"List overdue invoices"*
- *"Ramesh Gupta ko kal subah 10 baje reminder set karo"* (Triggers pending confirmation card)
- *"Ramesh ne agle somvar ko 5000 dene ka vaada kiya hai"* (Triggers commitment confirmation card)
- *"Record payment of 5000 for Ramesh via UPI"*


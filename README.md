# Chotu-Gyani (छोटू ज्ञानी)
*Your business. Your language. Your AI.*

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19-61DAFB.svg)](https://react.dev)
[![Telegram](https://img.shields.io/badge/Telegram-Bot%20API-2CA5E0.svg)](https://core.telegram.org/bots)
[![Gnani.ai](https://img.shields.io/badge/Voice%20AI-Gnani.ai%20Vachana-orange.svg)](https://gnani.ai)

---

## 📄 Solution Pitch (Executive Summary)

### The Problem
India is powered by over **63 million MSMEs, retail shopkeepers, and vyapaaris**. Their daily operations run on mutual trust, informal credit (*udhaar*), and paper notebooks (*bahi-khata*). While this system is flexible, it suffers from critical vulnerabilities:
1. **Uncollected Dues & Lost Revenue**: Shopkeepers frequently forget payment follow-ups (*takaada*), leading to delayed cash flows and bad debts.
2. **Friction with Traditional Software**: Conventional ERPs, Tally, and generic accounting tools fail small retailers. They require desktop computers, English literacy, complex menu navigation, and manual typing during busy store hours.
3. **Awkward Payment Chasing**: Shopkeepers hesitate to call customers repeatedly for overdue balances due to fear of damaging personal relationships.

### The Solution: Chotu-Gyani
**Chotu-Gyani** is an AI-powered voice & conversational operating system designed specifically for Indian small businesses. It functions as a 24/7 digital *munim* (accountant) that shopkeepers can simply speak to in **Hindi, English, or Hinglish**. Whether from a modern web dashboard or directly on Telegram while standing at the counter, Chotu handles everything through natural voice notes and simple text.

### Key Capabilities Built & Completed

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CHOTU-GYANI SYSTEM                            │
├──────────────────────────┬──────────────────────────────────────────────┤
│  Input Channels          │  Web App (React 19)  •  Telegram Bot (24/7)  │
├──────────────────────────┼──────────────────────────────────────────────┤
│  Voice Engine (Gnani.ai) │  Prisma-v3.0 (STT)   •  Timbre-v3.0 (TTS)    │
├──────────────────────────┼──────────────────────────────────────────────┤
│  Core Ledger             │  Customers • Invoices • Payments • Vaada     │
├──────────────────────────┼──────────────────────────────────────────────┤
│  Safety Gate             │  Two-Phase Confirmation on all Write Actions │
├──────────────────────────┼──────────────────────────────────────────────┤
│  Automated Delivery      │  Scheduled Reminders via Telegram & Email    │
└──────────────────────────┴──────────────────────────────────────────────┘
```

1. **Native Indian Voice AI (Gnani.ai Integration)**:
   - **Speech-to-Text (STT)**: Powered by Gnani.ai Vachana `prisma-v3.0` with real-time FFmpeg audio sniffing and conversion (transcoding WebM/OGG browser and Telegram audio into 16kHz mono WAV).
   - **Text-to-Speech (TTS)**: Powered by Gnani.ai `timbre-v3.0` with natural Indian accents (Shivani voice for Hindi, Devansh for English), speaking replies back to the shopkeeper.
   - **Hinglish & Colloquial Date Parsing**: Understands natural conversational phrases like *"3 tarik 10 baje"*, *"kal shaam"*, *"agle somvar 5000"* with dynamic same-day hour resolution.

2. **Strict Financial Safety Gate (Two-Phase Mutations)**:
   - Financial actions (creating customers, recording udhar commitments, scheduling reminders, collecting payments) **never mutate data blindly**.
   - The engine generates a structured preview with interactive `[✅ Confirm]` and `[❌ Cancel]` buttons before executing any ledger change.

3. **24/7 Telegram Bot Assistant**:
   - Shopkeepers can run their entire business via Telegram without opening a browser.
   - **Interactive Security**: `/start` authentication using registered email and password (passwords auto-deleted from chat for safety).
   - **Two-Way Voice Notes**: Receive voice notes from shopkeepers, transcribe via Gnani, process intent, and respond with synthesized voice notes.
   - **Inline Confirmations**: Direct `[Confirm]` / `[Cancel]` buttons inside Telegram chat for financial mutations.

4. **Automated Reminders & Multi-Channel Delivery (Telegram & Email)**:
   - **Zero-Friction Email Capture**: When recording udhar (*payment commitments*), Chotu asks for the customer's email ID (with optional skip) to attach it to their ledger record.
   - **Background Worker**: Background cron loop scans due reminders every 30 seconds.
   - **Proactive Alerts**: Automatically dispatches payment reminders to customers via **Email** and **Telegram**, ensuring on-time collections without awkward manual calls.

5. **Enterprise Multi-Tenancy & Security**:
   - Multi-tenant architecture enforced via `X-Business-ID` header, row-level isolation, PostgreSQL with `pg_trgm` fuzzy customer search, and Argon2id password encryption.

---

## 🛠️ Tech Stack

| Layer | Technologies |
|---|---|
| **Backend** | Python 3.12, FastAPI, SQLAlchemy 2.0 (asyncpg), PostgreSQL 16, Pydantic v2, Alembic, `uv` |
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS, Lucide Icons |
| **Voice AI** | Gnani.ai Vachana (`prisma-v3.0` STT, `timbre-v3.0` TTS), Groq Whisper & Orpheus |
| **LLM Reasoning** | Groq (OpenAI GPT-OSS-120B / Llama 3) with strict JSON schema outputs |
| **Integrations** | Telegram Bot API (`python-telegram-bot`), Google Workspace / Gmail API, FFmpeg |

---

## ⚙️ Configuration & Environment (`.env.example`)

The backend configuration includes all voice, messaging, and Google Workspace / email delivery headers:

```ini
# --- Runtime & Database ---
APP_ENV=dev
DATABASE_URL=postgresql+asyncpg://chotu:chotu@localhost:5433/chotu
TEST_DATABASE_URL=postgresql+asyncpg://chotu:chotu@localhost:5433/chotu_test

# --- Authentication ---
JWT_SECRET=your-secure-jwt-secret-here
ACCESS_TOKEN_TTL_MINUTES=15
REFRESH_TOKEN_TTL_DAYS=30

# --- Providers (LLM, STT, TTS) ---
LLM_PROVIDER=groq
STT_PROVIDER=gnani
TTS_PROVIDER=gnani

GROQ_API_KEY=your_groq_api_key
GROQ_LLM_MODEL=openai/gpt-oss-120b

# --- Gnani.ai Voice Engine ---
GNANI_API_KEY=your_gnani_api_key
GNANI_BASE_URL=https://api.vachana.ai

# --- Telegram Bot ---
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_from_botfather
TELEGRAM_WEBHOOK_URL=

# --- Google Workspace & Email Delivery (Customer Reminders) ---
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/integrations/google-sheets/callback
GOOGLE_REFRESH_TOKEN=
GOOGLE_SENDER_EMAIL=billing@yourbusiness.com
GOOGLE_APPLICATION_CREDENTIALS=

# --- SMTP Mail Delivery ---
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=billing@yourbusiness.com
SMTP_TLS=true

# --- Background Workers ---
ENABLE_WORKERS=true
WORKER_POLL_SECONDS=30
```

---

## ⚡ Quick Start

### 1. Database & Backend Setup

```powershell
cd backend

# Run database migrations
uv run alembic upgrade head

# Seed synthetic demo data (Sharma Traders)
uv run python -m scripts.seed_demo_data

# Start FastAPI server on port 8000
uv run uvicorn app.main:app --reload --port 8000
```

*Note: The Telegram bot starts automatically in background polling mode alongside FastAPI when `TELEGRAM_BOT_TOKEN` is configured.*

### 2. Frontend Setup

```powershell
cd frontend

# Install packages
npm install

# Start Vite development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 📱 Testing Chotu-Gyani

### Web Dashboard Testing
1. Visit `http://localhost:3000`.
2. Login with Demo credentials:
   - **Email:** `owner@sharmatraders.example.com`
   - **Password:** `Demo12345`
3. Try typing or speaking via the microphone:
   - *"Ramesh ka balance kitna hai?"*
   - *"Suresh ne 3000 ka udhar liya hai 10 tarik tak"*
   - *"Kal subah 10 baje Rakesh ko payment reminder set karo"*
   - *"Record payment of 5000 for Ramesh via UPI"*

### Telegram Bot Testing
1. Search for your bot handle on Telegram and send `/start`.
2. Enter your registered email (e.g., `anirudhsing308@gmail.com` or demo email).
3. Enter your password (message is automatically deleted for privacy).
4. Send text messages or hold the microphone button to send **voice notes** in Hindi or English!
5. Confirm actions using the inline `[✅ Confirm / पुष्टि करें]` keyboard.

---

## 📂 Project Directory Structure

```
chotu-gyaani/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # REST endpoints (auth, ledger, assistant, audio, integrations)
│   │   ├── core/            # Config, security (Argon2id, JWT), permissions, logging
│   │   ├── db/models/       # SQLAlchemy models (Customer, Invoice, Payment, Commitment, Reminder)
│   │   ├── integrations/    # Telegram Bot integration (voice & text handlers)
│   │   ├── providers/       # LLM (Groq), STT (Gnani, Groq), TTS (Gnani, Groq), Delivery
│   │   ├── services/        # Assistant pipeline, action service, audit trail
│   │   ├── tools/           # Financial tools registry (balance, payment, commitment, reminder)
│   │   ├── utils/           # Hinglish date engine, phone/audio utils, i18n
│   │   └── workers/         # Background reminder & expiry loop
│   ├── alembic/             # Database migrations
│   └── .env.example         # Template with Google, Telegram, and Gnani headers
└── frontend/
    ├── src/
    │   ├── components/      # UI components (AudioBar, ActionCard, Ledger tables)
    │   ├── pages/           # Assistant Chat, Dashboard, Customers, Invoices, Reminders
    │   └── services/        # API client with automatic X-Business-ID injection
    └── package.json
```

---

## 📜 License
Proprietary & Confidential. Built for Indian small businesses.

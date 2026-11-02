"""Tests run against real PostgreSQL (docker compose), never SQLite.
The schema is built by running the Alembic migrations, which also verifies them."""
import os
import subprocess
import sys
from pathlib import Path

os.environ["APP_ENV"] = "test"
os.environ.setdefault("TEST_DATABASE_URL", "postgresql+asyncpg://chotu:chotu@localhost:5433/chotu_test")
os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
os.environ["LLM_PROVIDER"] = "mock"
os.environ["STT_PROVIDER"] = "mock"
os.environ["TTS_PROVIDER"] = "mock"
os.environ["ENABLE_WORKERS"] = "false"
os.environ["REDIS_URL"] = ""
os.environ["GROQ_API_KEY"] = ""
os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["GOOGLE_CLIENT_SECRET"] = ""

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.core.rate_limit import rate_limiter  # noqa: E402
from app.db.session import get_sessionmaker, init_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.providers.llm import set_llm_override  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TABLES = ["action_logs", "idempotency_keys", "usage_records", "integrations", "messages", "pending_actions",
          "conversations", "agents", "reminders", "payment_commitments", "payments", "invoices", "customers",
          "invitations", "password_resets", "refresh_tokens", "business_members", "businesses", "users"]


@pytest.fixture(scope="session", autouse=True)
def _migrate() -> None:
    url = os.environ["TEST_DATABASE_URL"]
    env = {**os.environ, "ALEMBIC_DATABASE_URL": url}
    reset = ("import asyncio, asyncpg\n"
             "async def m():\n"
             f"    c = await asyncpg.connect('{url.replace('+asyncpg', '')}')\n"
             "    await c.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public;')\n"
             "    await c.close()\n"
             "asyncio.run(m())\n")
    subprocess.run([sys.executable, "-c", reset], check=True, cwd=ROOT, env=env)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, cwd=ROOT, env=env)
    init_engine(url)


@pytest.fixture(autouse=True)
async def _clean_db() -> None:
    async with get_sessionmaker()() as db:
        await db.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
        await db.commit()
    rate_limiter.reset()
    set_llm_override(None)
    yield
    set_llm_override(None)


@pytest.fixture
async def client() -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=60) as c:
        yield c


@pytest.fixture
async def db():
    async with get_sessionmaker()() as session:
        yield session


# ---------------- helpers ----------------
class Account:
    def __init__(self, client: httpx.AsyncClient, token: str, user_id: str, business_id: str | None = None):
        self.client = client
        self.token = token
        self.user_id = user_id
        self.business_id = business_id

    @property
    def headers(self) -> dict:
        h = {"Authorization": f"Bearer {self.token}"}
        if self.business_id:
            h["X-Business-ID"] = self.business_id
        return h

    async def get(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return await self.client.get(url, headers={**self.headers, **kw.pop("headers", {})}, **kw)

    async def post(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return await self.client.post(url, headers={**self.headers, **kw.pop("headers", {})}, **kw)

    async def patch(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return await self.client.patch(url, headers={**self.headers, **kw.pop("headers", {})}, **kw)

    async def delete(self, url: str, **kw):  # type: ignore[no-untyped-def]
        return await self.client.delete(url, headers={**self.headers, **kw.pop("headers", {})}, **kw)


async def register(client: httpx.AsyncClient, email: str, password: str = "Passw0rd!", name: str = "Test User"
                   ) -> Account:
    r = await client.post("/auth/register", json={"email": email, "password": password, "name": name})
    assert r.status_code == 201, r.text
    body = r.json()["data"]
    return Account(client, body["tokens"]["access_token"], body["user"]["id"])


async def owner_with_business(client: httpx.AsyncClient, email: str = "owner@example.com",
                              name: str = "Sharma Traders") -> Account:
    acc = await register(client, email)
    r = await client.post("/businesses", json={"name": name}, headers=acc.headers)
    assert r.status_code == 201, r.text
    acc.business_id = r.json()["data"]["business"]["id"]
    return acc


async def add_member(owner: Account, email: str, role: str) -> Account:
    """Invite + accept, then (for owner role) promote."""
    member = await register(owner.client, email)
    invite_role = "admin" if role in ("admin", "owner") else "member"
    r = await owner.post("/members/invite", json={"email": email, "role": invite_role})
    assert r.status_code == 201, r.text
    token = r.json()["data"]["debug_invite_token"]
    r = await owner.client.post("/invitations/accept", json={"token": token}, headers=member.headers)
    assert r.status_code == 200, r.text
    member.business_id = owner.business_id
    if role == "owner":
        r = await owner.patch(f"/members/{member.user_id}", json={"role": "owner"})
        assert r.status_code == 200, r.text
    return member


async def make_customer(acc: Account, name: str, phone: str | None = None, notes: str | None = None) -> dict:
    r = await acc.post("/customers", json={"name": name, "phone": phone, "notes": notes})
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def make_invoice(acc: Account, customer_id: str, number: str, total_paise: int, issued_on: str,
                       due_on: str) -> dict:
    r = await acc.post("/invoices", json={"customer_id": customer_id, "number": number, "total_paise": total_paise,
                                          "issued_on": issued_on, "due_on": due_on})
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def new_conversation(acc: Account, **body) -> str:  # type: ignore[no-untyped-def]
    r = await acc.post("/conversations", json=body)
    assert r.status_code == 201, r.text
    return r.json()["data"]["id"]


async def say(acc: Account, conv_id: str, text_: str) -> dict:
    r = await acc.post(f"/conversations/{conv_id}/messages", json={"content": text_})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def wav_with_transcript(text_: str, seconds: float = 1.0) -> bytes:
    import io
    import struct
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(struct.pack("<h", 0) * int(8000 * seconds))
    data = buf.getvalue()
    # Append a RIFF-compliant custom chunk carrying the mock transcript.
    payload = b"TRANSCRIPT:" + text_.encode("utf-8") + b"\x00"
    if len(payload) % 2:
        payload += b"\x00"
    chunk = b"mock" + struct.pack("<I", len(payload)) + payload
    riff_size = struct.unpack("<I", data[4:8])[0] + len(chunk)
    return data[:4] + struct.pack("<I", riff_size) + data[8:] + chunk

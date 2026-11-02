"""Hit every API route on a running server over real HTTP and verify coverage
against the app's own route table.

Usage: uv run python -m scripts.smoke_all_routes [base_url]
"""
import asyncio
import io
import logging
import struct
import sys
import uuid
import wave
from datetime import date, timedelta

import httpx

from app.main import app

logging.getLogger("httpx").setLevel(logging.WARNING)

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
RESULTS: list[tuple[str, str, int, int, bool]] = []
TODAY = date.today()


def d(n: int) -> str:
    return (TODAY + timedelta(days=n)).isoformat()


def wav(transcript: str) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 8000)
    data = buf.getvalue()
    payload = b"TRANSCRIPT:" + transcript.encode() + b"\x00"
    payload += b"\x00" * (len(payload) % 2)
    chunk = b"mock" + struct.pack("<I", len(payload)) + payload
    return data[:4] + struct.pack("<I", struct.unpack("<I", data[4:8])[0] + len(chunk)) + data[8:] + chunk


class S:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.c = client
        self.headers: dict[str, str] = {}

    async def call(self, method: str, template: str, path: str | None = None, expect: int = 200,
                   headers: dict | None = None, **kw) -> httpx.Response:  # type: ignore[no-untyped-def]
        r = await self.c.request(method, path or template, headers={**self.headers, **(headers or {})}, **kw)
        ok = r.status_code == expect
        RESULTS.append((method, template, r.status_code, expect, ok))
        flag = "OK " if ok else "BAD"
        print(f"  {flag} {method:<6} {path or template:<70} {r.status_code} (expected {expect})")
        if not ok:
            print(f"      body: {r.text[:300]}")
        return r


async def main() -> int:
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        s = S(client)
        tag = uuid.uuid4().hex[:8]
        print(f"Smoke testing {BASE}\n")

        await s.call("GET", "/health")
        await s.call("GET", "/ready")

        # ---------- auth ----------
        email = f"owner-{tag}@example.com"
        r = await s.call("POST", "/auth/register", expect=201,
                         json={"email": email, "password": "Passw0rd!", "name": "Rajesh Sharma"})
        tokens = r.json()["data"]["tokens"]
        r = await s.call("POST", "/auth/login", json={"email": email, "password": "Passw0rd!"})
        tokens = r.json()["data"]["tokens"]
        s.headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        await s.call("GET", "/auth/me")
        await s.call("PATCH", "/auth/me", json={"preferred_language": "hi-Latn"})
        r = await s.call("POST", "/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        new_tokens = r.json()["data"]["tokens"]
        s.headers = {"Authorization": f"Bearer {new_tokens['access_token']}"}

        # ---------- business ----------
        r = await s.call("POST", "/businesses", expect=201, json={"name": f"Sharma Traders {tag}"})
        bid = r.json()["data"]["business"]["id"]
        s.headers["X-Business-ID"] = bid
        await s.call("GET", "/businesses/me")
        await s.call("PATCH", "/businesses/me", json={"default_language": "hi-Latn"})

        # ---------- members ----------
        member_email = f"member-{tag}@example.com"
        r = await client.post("/auth/register", json={"email": member_email, "password": "Passw0rd!", "name": "M"})
        member_token = r.json()["data"]["tokens"]["access_token"]
        member_id = r.json()["data"]["user"]["id"]
        r = await s.call("POST", "/members/invite", expect=201, json={"email": member_email, "role": "member"})
        invite_token = r.json()["data"]["debug_invite_token"]
        await s.call("POST", "/invitations/accept", json={"token": invite_token},
                     headers={"Authorization": f"Bearer {member_token}", "X-Business-ID": ""})
        await s.call("GET", "/members")
        await s.call("PATCH", "/members/{user_id}", f"/members/{member_id}", json={"role": "admin"})

        # ---------- customers ----------
        r = await s.call("POST", "/customers", expect=201, json={"name": "Ramesh Gupta", "phone": "9812345601"})
        gupta = r.json()["data"]["id"]
        r = await s.call("POST", "/customers", expect=201, json={"name": "Ramesh Verma", "phone": "9812345602"})
        verma = r.json()["data"]["id"]
        await s.call("GET", "/customers", params={"q": "ramesh"})
        await s.call("GET", "/customers/{customer_id}", f"/customers/{gupta}")
        await s.call("PATCH", "/customers/{customer_id}", f"/customers/{gupta}", json={"notes": "Regular"})
        csv_bytes = b"name,phone\nSunita Devi,9812345603\nBad,12\n"
        await s.call("POST", "/customers/import", params={"dry_run": "false"},
                     files={"file": ("c.csv", csv_bytes, "text/csv")})
        r = await s.call("POST", "/customers", expect=201, json={"name": "Temp Customer"})
        await s.call("DELETE", "/customers/{customer_id}", f"/customers/{r.json()['data']['id']}")

        # ---------- invoices & payments ----------
        r = await s.call("POST", "/invoices", expect=201, json={
            "customer_id": gupta, "number": "INV-1001", "total_paise": 1250000, "issued_on": d(-40), "due_on": d(-10)})
        inv = r.json()["data"]["id"]
        await s.call("POST", "/invoices", expect=201, json={
            "customer_id": verma, "number": "INV-1002", "total_paise": 800000, "issued_on": d(-5), "due_on": d(20)})
        await s.call("GET", "/invoices", params={"overdue": "true"})
        await s.call("GET", "/invoices/{invoice_id}", f"/invoices/{inv}")
        await s.call("PATCH", "/invoices/{invoice_id}", f"/invoices/{inv}", json={"description": "Rice and dal"})
        r = await s.call("POST", "/invoices/{invoice_id}/payments", f"/invoices/{inv}/payments", expect=202,
                         json={"amount_paise": 250000, "method": "upi"})
        pay_action = r.json()["data"]["id"]
        await s.call("POST", "/actions/{action_id}/confirm", f"/actions/{pay_action}/confirm")
        await s.call("GET", "/invoices/{invoice_id}/payments", f"/invoices/{inv}/payments")
        await s.call("GET", "/payments")

        # ---------- reminders ----------
        r = await s.call("POST", "/reminders", expect=201, json={
            "customer_id": gupta, "invoice_id": inv, "scheduled_at": f"{d(3)}T10:00:00+05:30"})
        rem = r.json()["data"]["id"]
        await s.call("GET", "/reminders")
        await s.call("GET", "/reminders/{reminder_id}", f"/reminders/{rem}")
        await s.call("PATCH", "/reminders/{reminder_id}", f"/reminders/{rem}", json={"channel": "sms"})
        await s.call("POST", "/reminders/{reminder_id}/complete", f"/reminders/{rem}/complete")
        r = await client.post("/reminders", headers=s.headers,
                              json={"customer_id": verma, "scheduled_at": f"{d(4)}T10:00:00+05:30"})
        await s.call("POST", "/reminders/{reminder_id}/cancel", f"/reminders/{r.json()['data']['id']}/cancel")

        # ---------- payment commitments ----------
        r = await s.call("POST", "/payment-commitments", expect=201, json={
            "customer_id": verma, "promised_on": d(5), "promised_amount_paise": 500000})
        pc = r.json()["data"]["id"]
        await s.call("GET", "/payment-commitments")
        await s.call("GET", "/payment-commitments/{commitment_id}", f"/payment-commitments/{pc}")
        await s.call("PATCH", "/payment-commitments/{commitment_id}", f"/payment-commitments/{pc}",
                     json={"notes": "Will pay via UPI"})
        await s.call("DELETE", "/payment-commitments/{commitment_id}", f"/payment-commitments/{pc}")

        # ---------- conversations (demo script) ----------
        r = await s.call("POST", "/conversations", expect=201, json={})
        conv = r.json()["data"]["id"]
        await s.call("GET", "/conversations")
        await s.call("GET", "/conversations/{conversation_id}", f"/conversations/{conv}")
        msg = "/conversations/{conversation_id}/messages"
        for text in ("Kitne invoice overdue hain?", "Ramesh ka kitna baaki hai?", "Ramesh Gupta"):
            r = await s.call("POST", msg, f"/conversations/{conv}/messages", json={"content": text})
            print(f"      reply: {r.json()['data']['reply']!r}")
        r = await s.call("POST", msg, f"/conversations/{conv}/messages", json={"content": "Kal 5 baje yaad dila do"})
        print(f"      reply: {r.json()['data']['reply']!r}")
        action = r.json()["data"]["action"]["id"]
        await s.call("GET", msg, f"/conversations/{conv}/messages")
        r = await s.call("POST", "/conversations/{conversation_id}/messages/audio",
                         f"/conversations/{conv}/messages/audio",
                         files={"file": ("q.wav", wav("Ramesh Verma ko parso yaad dila do"), "audio/wav")})
        audio_action = r.json()["data"]["action"]["id"]
        print(f"      transcript: {r.json()['data']['transcript']['text']!r}")

        # ---------- actions ----------
        await s.call("GET", "/actions")
        await s.call("GET", "/actions/{action_id}", f"/actions/{action}")
        await s.call("POST", "/actions/{action_id}/confirm", f"/actions/{action}/confirm")
        await s.call("POST", "/actions/{action_id}/confirm", f"/actions/{action}/confirm", expect=409)
        await s.call("POST", "/actions/{action_id}/cancel", f"/actions/{audio_action}/cancel")

        # ---------- dashboard / audit / usage ----------
        await s.call("GET", "/dashboard/summary")
        await s.call("GET", "/dashboard/activity")
        await s.call("GET", "/dashboard/upcoming-reminders")
        await s.call("GET", "/dashboard/overdue-invoices")
        await s.call("GET", "/audit-logs")
        await s.call("GET", "/usage")

        # ---------- agents ----------
        r = await s.call("POST", "/agents/generate", json={"description": "Overdue dues ke liye reminder bhejne "
                                                                          "wala assistant, called Vasooli Bhai."})
        cfg = r.json()["data"]["config"]
        await s.call("POST", "/agents/generate-from-audio",
                     files={"file": ("a.wav", wav("Ek assistant banao jo customers ko yaad dilaye"), "audio/wav")})
        r = await s.call("POST", "/agents", expect=201, json=cfg)
        agent = r.json()["data"]["id"]
        await s.call("GET", "/agents")
        await s.call("GET", "/agents/{agent_id}", f"/agents/{agent}")
        await s.call("PATCH", "/agents/{agent_id}", f"/agents/{agent}", json={"instructions": "Be polite and brief."})
        await s.call("POST", "/agents/{agent_id}/test", f"/agents/{agent}/test",
                     json={"message": "Ramesh Gupta ka kitna baaki hai?"})
        await s.call("POST", "/agents/{agent_id}/activate", f"/agents/{agent}/activate")
        await s.call("POST", "/agents/{agent_id}/deactivate", f"/agents/{agent}/deactivate")
        await s.call("DELETE", "/agents/{agent_id}", f"/agents/{agent}")

        # ---------- audio ----------
        await s.call("POST", "/audio/transcribe", files={"file": ("q.wav", wav("Namaste"), "audio/wav")})
        await s.call("POST", "/audio/speech", json={"text": "Namaste", "language": "hi-Latn"})
        await s.call("GET", "/audio/providers")

        # ---------- integrations (no Google credentials configured -> 503) ----------
        await s.call("GET", "/integrations")
        await s.call("POST", "/integrations/google-sheets/connect", expect=503)
        await s.call("GET", "/integrations/google-sheets/callback", params={"code": "x", "state": "y"}, expect=503)
        await s.call("POST", "/integrations/google-sheets/import", json={"spreadsheet_id": "abcdef12345"}, expect=503)
        await s.call("DELETE", "/integrations/{integration_id}", f"/integrations/{uuid.uuid4()}", expect=404)

        # ---------- export, member removal, logout, password reset, deletion ----------
        await s.call("GET", "/export")
        await s.call("DELETE", "/members/{user_id}", f"/members/{member_id}")
        await s.call("POST", "/auth/logout", json={"refresh_token": new_tokens["refresh_token"]})
        r = await s.call("POST", "/auth/forgot-password", expect=202, json={"email": email})
        await s.call("POST", "/auth/reset-password",
                     json={"token": r.json()["data"]["debug_reset_token"], "new_password": "N3wPassword"})
        await s.call("DELETE", "/businesses/me")

    # ---------- coverage check against the app's route table ----------
    defined = {(m.upper(), path) for path, ops in app.openapi()["paths"].items() for m in ops}
    hit = {(m, p) for m, p, *_ in RESULTS}
    missing = sorted(defined - hit)
    failed = [r for r in RESULTS if not r[4]]
    print(f"\nRoutes defined: {len(defined)} | routes exercised: {len(hit & defined)} | calls: {len(RESULTS)} "
          f"| unexpected status: {len(failed)}")
    if missing:
        print("NOT EXERCISED:", missing)
    return 1 if (failed or missing) else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

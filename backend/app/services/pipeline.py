"""The assistant pipeline: one function for typed text and transcribed audio.

normalize -> (awaiting slot?) -> intent extraction -> validation -> permissions
-> entity resolution -> missing-field questions -> read tool / pending action
-> templated reply in the user's language."""
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select

from app.api.deps import Ctx
from app.core.exceptions import AppError, ProviderNotConfigured, ProviderUnavailable
from app.core.logging import log_event
from app.db.models import Agent, Conversation, Customer, Message, PendingAction
from app.providers.llm import IntentContext, LLMProvider, get_llm
from app.repositories import ledger as repo
from app.schemas.assistant import Intent, IntentEntities
from app.services import action_service
from app.tools.registry import REGISTRY, WRITE_TOOLS, ToolContext, effective_tools
from app.utils.dates import resolve_date, resolve_datetime, resolve_future_date
from app.utils.i18n import detect_language, normalize_lang, t
from app.utils.numbers import parse_amount_to_paise
from app.utils.phone import try_normalize_phone
from app.utils.text import normalize_name

logger = logging.getLogger(__name__)

ORDINALS = {
    "1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "first": 0, "1st": 0, "pehla": 0, "pehle": 0, "pehli": 0,
    "pahla": 0, "second": 1, "2nd": 1, "doosra": 1, "dusra": 1, "doosre": 1, "dusre": 1, "doosri": 1,
    "third": 2, "3rd": 2, "teesra": 2, "tisra": 2, "teesre": 2, "fourth": 3, "4th": 3, "last": -1,
    "aakhri": -1, "akhri": -1, "पहला": 0, "पहले": 0, "दूसरा": 1, "दूसरे": 1, "तीसरा": 2, "आखिरी": -1,
}
NEUTRAL_TOKENS = {"wala", "wale", "wali", "vala", "vale", "ji", "the", "one", "sahab", "bhai", "number", "option"}


@dataclass
class Outcome:
    reply: str
    language: str
    intent: dict | None = None
    tool: str | None = None
    data: Any = None
    action: PendingAction | None = None
    preview: dict | None = None
    clarification: dict | None = None
    state: dict = field(default_factory=dict)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _pick_ordinal(text: str, n: int) -> int | None:
    toks = re.findall(r"[\wऀ-ॿ]+", text.lower())
    if not toks or len(toks) > 4:
        return None
    for tok in toks:
        if tok in ORDINALS:
            idx = ORDINALS[tok]
            idx = n - 1 if idx == -1 else idx
            return idx if 0 <= idx < n else None
    return None


def _pick_by_name(text: str, candidates: list[dict]) -> int | None:
    q = set(normalize_name(text).split()) - NEUTRAL_TOKENS
    if not q:
        return None
    q |= {"".join(sorted(q, key=normalize_name(text).find))} | set(re.findall(r"\d{2,}", text))
    scores = []
    for c in candidates:
        tokens = set(normalize_name(c.get("name", "")).split())
        if c.get("number"):
            number = c["number"]
            tokens |= {normalize_name(number).replace(" ", "")} | set(re.findall(r"\d{2,}", number))
            # An invoice number is decisive over the shared customer name.
            if q & ({normalize_name(number).replace(" ", "")} | set(re.findall(r"\d{2,}", number))):
                return candidates.index(c)
        scores.append(len(q & tokens))
    best = max(scores)
    if best == 0 or scores.count(best) > 1:
        return None
    return scores.index(best)


def _options(candidates: list[dict]) -> str:
    lines = []
    for i, c in enumerate(candidates, 1):
        extra = f" ({c['phone']})" if c.get("phone") else ""
        if c.get("number"):
            extra = f" - {c['number']}" + (f", {c['balance_display']}" if c.get("balance_display") else "")
        lines.append(f"{i}. {c['name']}{extra}")
    return "\n".join(lines)


class Pipeline:
    def __init__(self, ctx: Ctx, conversation: Conversation | None, agent: Agent | None, dry_run: bool) -> None:
        self.ctx = ctx
        self.conversation = conversation
        self.agent = agent
        self.dry_run = dry_run
        self.state: dict = dict(conversation.state or {}) if conversation else {}
        self.llm: LLMProvider | None = None
        self.text = ""

    # -------- entry point --------
    async def run(self, text: str, language_hint: str | None) -> Outcome:
        text = _clean(text)
        self.text = text
        lang = normalize_lang(language_hint) if language_hint else (
            detect_language(text) if text else normalize_lang(
                (self.conversation.language if self.conversation else None) or self.ctx.business.default_language))
        if not text:
            return Outcome(t("empty_input", lang), lang)

        awaiting = self.state.get("awaiting")
        if awaiting:
            out = await self._resume(awaiting, text, lang)
            if out is not None:
                return out
            self.state.pop("awaiting", None)

        try:
            intent = await self._extract(text, lang)
        except (ProviderUnavailable, ProviderNotConfigured):
            return Outcome(t("provider_unavailable", lang), lang, intent={"type": "error"})
        return await self._handle(intent, lang, resolved={})

    async def _extract(self, text: str, lang: str) -> Intent:
        llm = get_llm()
        self.llm = llm
        allowed = sorted(self._effective())
        recent: list[dict] = []
        if self.conversation and not self.dry_run:
            rows = (await self.ctx.db.execute(
                select(Message.role, Message.content).where(Message.conversation_id == self.conversation.id)
                .order_by(Message.created_at.desc()).limit(4))).all()
            recent = [{"role": r, "content": c[:500]} for r, c in reversed(rows)]
        ictx = IntentContext(language=lang, timezone=self.ctx.business.timezone,
                             today_iso=action_service.tool_ctx(self.ctx, lang).today.isoformat(),
                             allowed_intents=allowed, agent_instructions=self.agent.instructions if self.agent else None,
                             awaiting_slot=None, recent_turns=recent)
        started = time.perf_counter()
        raw = await llm.extract_intent(text, ictx)
        try:
            intent = Intent.model_validate(raw.model_dump() if hasattr(raw, "model_dump") else raw)
        except ValidationError:
            intent = Intent(type="unsupported")
        log_event(logger, "intent_extracted", provider=llm.name, intent_type=intent.type,
                  provider_latency_ms=round((time.perf_counter() - started) * 1000))
        return intent

    def _effective(self) -> set[str]:
        agent_tools = list(self.agent.enabled_tools) if self.agent else None
        return effective_tools(self.ctx.role, agent_tools, self.ctx.business.settings)

    def _tctx(self, lang: str) -> ToolContext:
        return action_service.tool_ctx(self.ctx, lang)

    # -------- clarification resume --------
    async def _resume(self, awaiting: dict, text: str, lang: str) -> Outcome | None:
        slot = awaiting.get("slot")
        snapshot = awaiting.get("intent_snapshot") or {}
        resolved = dict(awaiting.get("resolved") or {})
        try:
            intent = Intent.model_validate(snapshot)
        except ValidationError:
            return None
        cands = awaiting.get("candidates") or []
        if slot in ("customer", "invoice") and cands:
            idx = _pick_ordinal(text, len(cands))
            if idx is None:
                idx = _pick_by_name(text, cands)
            if idx is None:
                return None
            resolved[f"{slot}_id"] = cands[idx]["id"]
            self.state.pop("awaiting", None)
            return await self._handle(intent, lang, resolved=resolved)
        if slot in ("date", "amount", "customer_name", "invoice_number"):
            try:
                fresh = await self._extract(text, lang)
            except (ProviderUnavailable, ProviderNotConfigured):
                return Outcome(t("provider_unavailable", lang), lang)
            e = fresh.entities
            merged = intent.entities.model_copy()
            filled = False
            if slot == "date" and e.date:
                merged.date, filled = e.date, True
            elif slot == "amount" and e.amount_phrase:
                merged.amount_phrase, filled = e.amount_phrase, True
            elif slot == "customer_name" and (e.customer_name or e.customer_phone or e.query):
                merged.customer_name = e.customer_name or e.query
                merged.customer_phone = e.customer_phone
                filled = True
            elif slot == "invoice_number" and e.invoice_number:
                merged.invoice_number, filled = e.invoice_number, True
            if not filled:
                return None
            if e.channel and not merged.channel:
                merged.channel = e.channel
            intent = intent.model_copy(update={"entities": merged})
            self.state.pop("awaiting", None)
            return await self._handle(intent, lang, resolved=resolved)
        return None

    def _ask(self, lang: str, key: str, slot: str, intent: Intent, resolved: dict, **kw: Any) -> Outcome:
        self.state["awaiting"] = {"slot": slot, "candidates": [], "intent_snapshot": intent.model_dump(mode="json"),
                                  "resolved": resolved}
        return Outcome(t(key, lang, **kw), lang, intent=intent.model_dump(mode="json"), tool=intent.type,
                       clarification={"slot": slot, "options": []})

    def _clarify(self, lang: str, key: str, slot: str, intent: Intent, resolved: dict, candidates: list[dict],
                 **kw: Any) -> Outcome:
        self.state["awaiting"] = {"slot": slot, "candidates": candidates,
                                  "intent_snapshot": intent.model_dump(mode="json"), "resolved": resolved}
        return Outcome(t(key, lang, options=_options(candidates), **kw), lang,
                       intent=intent.model_dump(mode="json"), tool=intent.type,
                       clarification={"slot": slot, "options": candidates})

    # -------- resolution helpers --------
    async def _resolve_customer(self, intent: Intent, lang: str, resolved: dict) -> Customer | Outcome:
        db, bid = self.ctx.db, self.ctx.business_id
        if resolved.get("customer_id"):
            c = (await db.execute(select(Customer).where(Customer.id == uuid.UUID(str(resolved["customer_id"])),
                                                         Customer.business_id == bid,
                                                         Customer.archived_at.is_(None)))).scalar_one_or_none()
            if c is not None:
                return c
        e = intent.entities
        phone = try_normalize_phone(e.customer_phone) if e.customer_phone else None
        name = e.customer_name or (e.query if intent.type == "search_customers" else None)
        if not phone and not name:
            focus = self.state.get("focus_customer_id")
            if focus:
                c = (await db.execute(select(Customer).where(Customer.id == uuid.UUID(focus),
                                                             Customer.business_id == bid,
                                                             Customer.archived_at.is_(None)))).scalar_one_or_none()
                if c is not None:
                    return c
            return self._ask(lang, "ask_customer", "customer_name", intent, resolved)
        match, cands = await repo.resolve_customer(db, bid, name=name, phone_e164=phone)
        if match is not None:
            return match
        if cands:
            options = [{"id": str(c.id), "name": c.name, "phone": c.phone_e164} for c in cands[:5]]
            return self._clarify(lang, "clarify_customer", "customer", intent, resolved, options,
                                 query=name or phone or "")
        return Outcome(t("not_found_customer", lang, query=name or phone or ""), lang,
                       intent=intent.model_dump(mode="json"), tool=intent.type)

    async def _resolve_invoice_for(self, intent: Intent, lang: str, resolved: dict, customer: Customer | None,
                                   *, required: bool) -> tuple[uuid.UUID | None, Outcome | None]:
        tctx = self._tctx(lang)
        if resolved.get("invoice_id"):
            return uuid.UUID(str(resolved["invoice_id"])), None
        if intent.entities.invoice_number:
            items, _ = await repo.list_invoices(self.ctx.db, self.ctx.business_id, tctx.today,
                                                number=intent.entities.invoice_number, limit=1)
            if not items or (customer and items[0].customer_id != customer.id):
                return None, Outcome(t("not_found_invoice", lang, query=intent.entities.invoice_number), lang,
                                     intent=intent.model_dump(mode="json"), tool=intent.type)
            return items[0].id, None
        if customer is None:
            return None, None
        items, _ = await repo.list_invoices(self.ctx.db, self.ctx.business_id, tctx.today,
                                            customer_id=customer.id, status="open", limit=50)
        items = [i for i in items if i.balance_paise > 0]
        if len(items) == 1:
            return items[0].id, None
        if not required:
            return None, None
        if not items:
            return None, Outcome(t("balance_zero", lang, customer=customer.name), lang,
                                 intent=intent.model_dump(mode="json"), tool=intent.type)
        options = [{"id": str(i.id), "name": customer.name, "number": i.number,
                    "balance_display": i.balance_display} for i in items[:5]]
        return None, self._clarify(lang, "clarify_invoice", "invoice", intent,
                                   {**resolved, "customer_id": str(customer.id)}, options, customer=customer.name)

    # -------- main dispatch --------
    async def _handle(self, intent: Intent, lang: str, resolved: dict) -> Outcome:
        itype = intent.type
        idump = intent.model_dump(mode="json")
        if itype == "smalltalk":
            try:
                llm = self.llm or get_llm()
                reply = await llm.compose_reply(self.text, lang,
                                                self.agent.instructions if self.agent else None)
            except AppError:
                reply = ""
            return Outcome(reply or t("smalltalk", lang), lang, intent=idump)
        if itype in ("unsupported", "clarify") or itype not in REGISTRY:
            return Outcome(t("unsupported", lang), lang, intent=idump)
        if itype not in self._effective():
            return Outcome(t("permission_denied", lang), lang, intent=idump, tool=itype)

        tool = REGISTRY[itype]
        tctx = self._tctx(lang)
        tz = self.ctx.business.timezone
        e: IntentEntities = intent.entities
        try:
            if itype in ("list_overdue_invoices", "get_dashboard_summary"):
                inp = tool.input_schema.model_validate({})
                return await self._run_read(tool, tctx, inp, idump, lang)

            if itype == "get_invoice_details":
                if not e.invoice_number:
                    return self._ask(lang, "ask_invoice", "invoice_number", intent, resolved)
                inp = tool.input_schema.model_validate({"invoice_number": e.invoice_number})
                try:
                    return await self._run_read(tool, tctx, inp, idump, lang)
                except AppError as err:
                    if err.code == "invoice_not_found":
                        return Outcome(t("not_found_invoice", lang, query=e.invoice_number), lang, intent=idump,
                                       tool=itype)
                    raise

            if itype == "search_customers":
                query = e.query or e.customer_name or e.customer_phone
                if not query:
                    return self._ask(lang, "ask_customer", "customer_name", intent, resolved)
                inp = tool.input_schema.model_validate({"query": query})
                return await self._run_read(tool, tctx, inp, idump, lang)

            # Everything below needs a customer (record_payment may come via invoice number instead).
            customer: Customer | None = None
            if not (itype == "record_payment" and e.invoice_number and not e.customer_name):
                res = await self._resolve_customer(intent, lang, resolved)
                if isinstance(res, Outcome):
                    return res
                customer = res
                self.state["focus_customer_id"] = str(customer.id)
                resolved = {**resolved, "customer_id": str(customer.id)}

            if itype in ("get_customer_balance", "list_customer_reminders"):
                assert customer is not None
                inp = tool.input_schema.model_validate({"customer_id": customer.id})
                return await self._run_read(tool, tctx, inp, idump, lang)

            if itype == "schedule_reminder":
                assert customer is not None
                if not e.date:
                    return self._ask(lang, "ask_date", "date", intent, resolved)
                when = resolve_datetime(e.date.model_dump(), tz, tctx.now)
                invoice_id, out = await self._resolve_invoice_for(intent, lang, resolved, customer, required=False)
                if out:
                    return out
                payload: dict[str, Any] = {"customer_id": customer.id, "invoice_id": invoice_id,
                                           "scheduled_at": when,
                           "channel": e.channel or "whatsapp"}
                return await self._propose(tool, tctx, payload, idump, lang)

            if itype == "record_payment_commitment":
                assert customer is not None
                if not e.date:
                    return self._ask(lang, "ask_date", "date", intent, resolved)
                promised_on = resolve_future_date(e.date.model_dump(), tz, tctx.now)
                amount = None
                if e.amount_phrase:
                    amount = parse_amount_to_paise(e.amount_phrase)
                    if amount is None:
                        return Outcome(t("invalid_input", lang, detail=e.amount_phrase), lang, intent=idump,
                                       tool=itype)
                invoice_id, out = await self._resolve_invoice_for(intent, lang, resolved, customer, required=False)
                if out:
                    return out
                payload = {"customer_id": customer.id, "invoice_id": invoice_id,
                           "promised_amount_paise": amount, "promised_on": promised_on}
                return await self._propose(tool, tctx, payload, idump, lang)

            if itype == "record_payment":
                if not e.amount_phrase:
                    return self._ask(lang, "ask_amount", "amount", intent, resolved)
                amount = parse_amount_to_paise(e.amount_phrase)
                if amount is None:
                    return Outcome(t("invalid_input", lang, detail=e.amount_phrase), lang, intent=idump, tool=itype)
                invoice_id, out = await self._resolve_invoice_for(intent, lang, resolved, customer, required=True)
                if out:
                    return out
                if invoice_id is None:
                    return self._ask(lang, "ask_invoice", "invoice_number", intent, resolved)
                paid_on: date = resolve_date(e.date.model_dump(), tz, tctx.now) if e.date else tctx.today
                payload = {"invoice_id": invoice_id, "amount_paise": amount, "paid_on": paid_on, "method": "cash"}
                return await self._propose(tool, tctx, payload, idump, lang)
        except AppError as err:
            if err.code == "date_in_past":
                return Outcome(t("date_in_past", lang), lang, intent=idump, tool=itype)
            if err.code in ("invalid_date", "invalid_time", "missing_date"):
                return Outcome(t("invalid_input", lang, detail=err.message), lang, intent=idump, tool=itype)
            if err.code == "permission_denied":
                return Outcome(t("permission_denied", lang), lang, intent=idump, tool=itype)
            if err.status_code in (404, 422):
                return Outcome(t("invalid_input", lang, detail=err.message), lang, intent=idump, tool=itype)
            raise
        return Outcome(t("unsupported", lang), lang, intent=idump)

    async def _run_read(self, tool: Any, tctx: ToolContext, inp: Any, idump: dict, lang: str) -> Outcome:
        result = await tool.run(tctx, inp)
        return Outcome(result.text, lang, intent=idump, tool=tool.name, data=result.data)

    async def _propose(self, tool: Any, tctx: ToolContext, payload: dict, idump: dict, lang: str) -> Outcome:
        assert tool.name in WRITE_TOOLS
        inp = tool.input_schema.model_validate(payload)
        if self.dry_run:
            preview = await tool.preview(tctx, inp)
            return Outcome(t("dry_run", lang, text=preview["text"]), lang, intent=idump, tool=tool.name,
                           preview=preview)
        action = await action_service.propose(tctx, tool, inp, self.conversation.id if self.conversation else None,
                                              commit=False)
        return Outcome(action.preview["text"], lang, intent=idump, tool=tool.name, action=action,
                       preview=action.preview)


async def process_user_message(ctx: Ctx, conversation: Conversation | None, text: str,
                               language_hint: str | None = None, *, dry_run: bool = False,
                               source: str = "text", agent: Agent | None = None) -> dict:
    """Shared entry point for typed text, audio transcripts and agent dry-runs."""
    if agent is None and conversation is not None and conversation.agent_id:
        agent = await ctx.db.get(Agent, conversation.agent_id)
        if agent is not None and (agent.business_id != ctx.business_id or agent.status != "active"):
            agent = None
    pipeline = Pipeline(ctx, conversation, agent, dry_run)
    outcome = await pipeline.run(text, language_hint)
    llm_name = pipeline.llm.name if pipeline.llm else get_llm().name

    user_msg = assistant_msg = None
    if not dry_run and conversation is not None:
        user_msg = Message(conversation_id=conversation.id, role="user", content=_clean(text) or "(empty)",
                           language=outcome.language, tool_metadata={"source": source})
        ctx.db.add(user_msg)
        await ctx.db.flush()
        meta: dict[str, Any] = {"tool": outcome.tool, "llm_provider": llm_name}
        if outcome.action is not None:
            meta["action_id"] = str(outcome.action.id)
        if outcome.clarification:
            meta["clarification"] = outcome.clarification
        assistant_msg = Message(conversation_id=conversation.id, role="assistant", content=outcome.reply,
                                intent=outcome.intent, tool_metadata=meta, language=outcome.language)
        ctx.db.add(assistant_msg)
        conversation.state = pipeline.state
        conversation.language = outcome.language
        await ctx.db.commit()
        await ctx.db.refresh(user_msg)
        await ctx.db.refresh(assistant_msg)
        if outcome.action is not None:
            await ctx.db.refresh(outcome.action)

    return {
        "outcome": outcome,
        "user_message": user_msg,
        "assistant_message": assistant_msg,
        "llm_provider": llm_name,
    }

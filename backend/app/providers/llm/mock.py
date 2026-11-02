"""Deterministic rule-based mock LLM. Clearly labelled as `mock` in responses.

It maps English, Hindi and Hinglish utterances to the same validated Intent
schema the real provider returns, so the whole pipeline runs offline."""
import re
from datetime import date

from app.providers.llm.base import IntentContext
from app.schemas.assistant import AgentConfig, DateSpec, Intent, IntentEntities
from app.utils.i18n import detect_language, t
from app.utils.numbers import find_amount_phrase

WEEKDAY_WORDS = {
    "monday": ["monday", "mon", "somvar", "somwar", "सोमवार"],
    "tuesday": ["tuesday", "tue", "mangalvar", "mangalwar", "mangal", "मंगलवार"],
    "wednesday": ["wednesday", "wed", "budhvar", "budhwar", "budh", "बुधवार"],
    "thursday": ["thursday", "thu", "guruvar", "guruwar", "brihaspativar", "veervar", "गुरुवार"],
    "friday": ["friday", "fri", "shukravar", "shukrawar", "shukra", "शुक्रवार"],
    "saturday": ["saturday", "sat", "shanivar", "shaniwar", "shani", "शनिवार"],
    "sunday": ["sunday", "sun", "ravivar", "raviwar", "itvaar", "itwar", "रविवार"],
}
MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}

INJECTION = re.compile(
    r"ignore (all |the )?(previous|prior|above)|system prompt|disregard (the )?(rules|instructions)|"
    r"\bdrop\s+table\b|\bdelete\s+from\b|\bselect\s+\*|;\s*--|skip (the )?confirmation|without confirm|"
    r"bypass|jailbreak|you are now|act as (an? )?admin|reveal (your )?(prompt|instructions)|"
    r"all customers' data|delete all", re.I)

GREETINGS = {"hi", "hello", "hey", "namaste", "namaskar", "thanks", "thank", "you", "dhanyavad", "dhanyawad",
             "shukriya", "ok", "okay", "theek", "hai", "good", "morning", "evening", "नमस्ते", "धन्यवाद", "ji",
             "bhai", "haan", "accha", "acha"}

STOP = set("""
a an the is are was were be been am i me my we our you your he she it they them this that these those
of for to from in on at by with about and or but not no yes please kindly can could would will shall should
do does did done how much many what which who whom whose when where why there here all any some show tell give
get find search list set schedule remind reminder reminders send create add make record mark note save
owe owes owed outstanding balance due dues pending overdue invoice invoices bill bills payment payments paid pay
received receive promise promised promises commit committed customer customers client clients details detail
number phone contact info information summary dashboard overview total today tomorrow day after next this week
month end upcoming scheduled late past money amount rupees rs inr only also again now then me us him her their
let know check see look up up has have had via whatsapp sms call message text him them it's what's how's
ka ki ke ko ne se me mein par pe hai hain tha thi the ho hoga hogi hua hui kya kitna kitne kitni kaun kaunsa
konsa kab kahan kaise baaki baki bakaya udhaar udhar dena lena dene liye wala wale wali sab saare sare kul
yaad dila dilao dilana dilado karo kar karna karke kardo kr krdo do de diya diye dijiye dena hai bata batao
bataiye dikhao dikha dekho dhundo dhoondo khojo bhejo bhej laga lagao rakh rakho aaj kal parso agle agla agli
pichhle wale vaada vada wada dega degi denge dene ko bola bole kaha mila mile milega mil gaya gaye jama
hisaab hisab kitab kitaab kaisa kaisi chal raha rahi abhi tak ek doosra dusra pehla teesra wala ji bhai sahab saab
subah shaam sham raat dopahar baje bje ghante minute din hafte mahine baad pehle ke liye
ignore previous instructions system prompt payments
का की के को ने से में पर है हैं था थी कितना कितने कितनी कौन कब बाकी बकाया याद दिला दिलाओ दो दें करो कर
बताओ दिखाओ आज कल परसों अगले बिल भुगतान वादा दिया दिए मिला मिले जमा ग्राहक रिमाइंडर ओवरड्यू कुल हिसाब बजे
सुबह शाम रात रुपये रुपए हज़ार हजार लाख सौ
""".split())

ALL_WEEKDAY_TOKENS = {w for ws in WEEKDAY_WORDS.values() for w in ws}


def _norm_invoice(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    return f"INV-{digits}"


class MockLLM:
    name = "mock"

    # ---------------- entity extraction ----------------
    def _extract(self, text: str) -> tuple[IntentEntities, str]:
        working = " " + text + " "
        ent = IntentEntities()

        def cut(pattern: str, flags: int = re.I) -> list[re.Match]:
            nonlocal working
            matches = list(re.finditer(pattern, working, flags))
            for m in reversed(matches):
                working = working[:m.start()] + " | " + working[m.end():]
            return matches

        inv = cut(r"\b(?:inv(?:oice)?\s*(?:no\.?|number|#)?\s*[-#]?\s*(\d{2,}))\b|#(\d{2,})\b")
        if inv:
            ent.invoice_number = _norm_invoice(inv[0].group(0))

        iso = cut(r"\b(\d{4}-\d{2}-\d{2})\b")
        ph = cut(r"(?<![\w-])\+?\d[\d\s-]{8,}\d\b")
        if ph:
            ent.customer_phone = re.sub(r"[\s-]", "", ph[0].group(0))

        for ch, words in (("whatsapp", r"whats\s?app"), ("sms", r"\bsms\b|\btext message\b"),
                          ("call", r"\bphone call\b|\bcall\b")):
            if cut(words):
                ent.channel = ch  # type: ignore[assignment]
                break

        date_spec = DateSpec()
        dm = cut(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b") if not iso else []
        mon = cut(r"\b(\d{1,2})\s*(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b"
                  ) if not (iso or dm) else []
        today = date.today()
        if iso:
            date_spec.date = iso[0].group(1)
        elif dm:
            d, m_, y = int(dm[0].group(1)), int(dm[0].group(2)), dm[0].group(3)
            year = int(y) + (2000 if y and len(y) == 2 else 0) if y else today.year
            try:
                cand = date(year, m_, d)
                if not y and cand < today:
                    cand = date(year + 1, m_, d)
                date_spec.date = cand.isoformat()
            except ValueError:
                pass
        elif mon:
            d, m_ = int(mon[0].group(1)), MONTHS[mon[0].group(2).lower()[:3]]
            try:
                cand = date(today.year, m_, d)
                if cand < today:
                    cand = date(today.year + 1, m_, d)
                date_spec.date = cand.isoformat()
            except ValueError:
                pass

        if not date_spec.date:
            rel = None
            if cut(r"\bday after tomorrow\b|\bparso(n)?\b|परसों"):
                rel = "day_after_tomorrow"
            elif cut(r"\btomorrow\b|\bkal\b|\bkl\b|कल"):
                rel = "tomorrow"
            elif cut(r"\btoday\b|\baaj\b|आज"):
                rel = "today"
            elif cut(r"\bend of (the )?month\b|mahine ke (end|aakhir|akhir) (mein|me|tak)?|महीने के अंत"):
                rel = "end_of_month"
            elif m := cut(r"\b(?:in\s+)?(\d{1,2}|ek|do|teen|char|paanch|saat)\s+(days?|din|weeks?|hafte|hafton|"
                          r"months?|mahine)\s*(baad|mein|me|later)?\b"):
                small = {"ek": 1, "do": 2, "teen": 3, "char": 4, "paanch": 5, "saat": 7}
                nraw = m[0].group(1).lower()
                n = int(nraw) if nraw.isdigit() else small[nraw]
                unit = m[0].group(2).lower()
                unit_key = "days" if unit.startswith(("day", "din")) else (
                    "weeks" if unit.startswith(("week", "haft")) else "months")
                rel = f"in_{n}_{unit_key}"
            elif cut(r"\bnext week\b|agle hafte|अगले हफ्ते"):
                rel = "next_week"
            elif cut(r"\bnext month\b|agle mahine|अगले महीने"):
                rel = "next_month"
            else:
                for day, day_words in WEEKDAY_WORDS.items():
                    pat = r"(?:\b(next|agle|agla|coming|this|is)\s+)?(?:" + "|".join(
                        re.escape(w) + (r"\b" if w.isascii() else "") for w in day_words) + r")"
                    pat = r"(?:(?<=\s)|^)" + pat
                    mm = cut(pat)
                    if mm:
                        prefix = (mm[0].group(1) or "").lower()
                        rel = f"next_{day}" if prefix in ("next", "agle", "agla") else f"this_{day}"
                        break
            date_spec.relative = rel

        # time
        tm = cut(r"\b(?:at\s+)?(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.|baje|bje|o'?clock|बजे)")
        if not tm:
            tm = cut(r"\bat\s+(\d{1,2})(?:[:.](\d{2}))?\b()")
        low = text.lower()
        if tm:
            h = int(tm[0].group(1))
            mi = int(tm[0].group(2) or 0)
            suffix = (tm[0].group(3) or "").lower().replace(".", "")
            pm_words = re.search(r"\b(evening|night|afternoon|shaam|sham|raat|dopahar)\b|शाम|रात|दोपहर", low)
            am_words = re.search(r"\b(morning|subah|savere)\b|सुबह", low)
            if suffix == "pm" and h < 12:
                h += 12
            elif suffix == "am" and h == 12:
                h = 0
            elif suffix not in ("am", "pm"):
                if pm_words and h < 12:
                    h += 12
                elif not am_words and 1 <= h <= 7:
                    h += 12  # shop-hours heuristic: "5 baje" means 17:00
            if 0 <= h <= 23 and 0 <= mi <= 59:
                date_spec.time = f"{h:02d}:{mi:02d}"
        elif re.search(r"\b(morning|subah)\b|सुबह", low):
            date_spec.time = "10:00"
        elif re.search(r"\b(evening|shaam|sham)\b|शाम", low):
            date_spec.time = "18:00"
        cut(r"\b(subah|shaam|sham|raat|dopahar|morning|evening|night|afternoon)\b|सुबह|शाम|रात")

        if date_spec.date or date_spec.relative:
            ent.date = date_spec
        elif date_spec.time:
            ent.date = DateSpec(relative="today", time=date_spec.time)

        amount = find_amount_phrase(working.replace("|", " "))
        if amount:
            ent.amount_phrase = amount
            # remove the amount words from the working text
            for tok in amount.split():
                working = re.sub(r"(?<!\w)" + re.escape(tok) + r"(?!\w)", " | ", working, count=1, flags=re.I)
            cut(r"₹|\brs\.?|\brupees?\b|\brupaye\b|रुपये|रुपए")

        ent.customer_name = self._name(working)
        return ent, working

    def _name(self, working: str) -> str | None:
        runs: list[list[str]] = [[]]
        for raw in re.split(r"\s+", working):
            tok = raw.strip(".,!?;:\"()")
            tok = re.sub(r"'s$|’s$", "", tok)
            if not tok or tok == "|":
                runs.append([])
                continue
            low = tok.lower()
            if low in STOP or low in ALL_WEEKDAY_TOKENS or low in GREETINGS or any(c.isdigit() for c in tok):
                runs.append([])
                continue
            if len(tok) < 2:
                runs.append([])
                continue
            runs[-1].append(tok)
        runs = [r for r in runs if r]
        if not runs:
            return None
        best = max(runs, key=len)
        name = " ".join(best[:4])
        return name.title() if name.isascii() else name

    # ---------------- intent ----------------
    async def extract_intent(self, text: str, ctx: IntentContext) -> Intent:
        raw = text.strip()
        low = raw.lower()
        if not raw:
            return Intent(type="unsupported", confidence=0.0)
        if INJECTION.search(raw):
            return Intent(type="unsupported", confidence=0.95)

        ent, _ = self._extract(raw)
        words = set(re.findall(r"[\w']+", low))

        def has(*pats: str) -> bool:
            return any(re.search(p, low) for p in pats)

        is_greeting = words and words <= GREETINGS
        reminder_word = has(r"\bremind", r"\breminders?\b", r"yaad", r"याद", r"रिमाइंडर")
        list_word = has(r"\blist\b", r"\bshow\b", r"\bwhich\b", r"\bwhat\b", r"\bupcoming\b", r"\bkaun",
                        r"\bdikhao\b", r"\bdikha\b", r"\bbatao\b", r"\bbata\b", r"\bkitne\b", r"\bhow many\b",
                        r"\bany\b", r"कौन", r"दिखाओ", r"बताओ")
        set_word = has(r"\bset\b", r"\bschedule\b", r"\bdila", r"\bremind\b", r"\bremind me\b", r"\bbhej",
                       r"\blaga", r"\bkar do\b", r"\bkardo\b", r"\bkaro\b", r"\bcreate\b", r"\badd\b", r"दिला",
                       r"\bsend\b")
        commit_word = has(r"\bpromis", r"\bvaada\b", r"\bvada\b", r"\bwada\b", r"वादा", r"\bcommit",
                          r"\bdega\b", r"\bdegi\b", r"\bdenge\b", r"dene (ko|ka) (bola|kaha)", r"\bwill pay\b",
                          r"देगा", r"देंगे")
        paid_word = has(r"\bpaid\b", r"\breceived\b", r"payment mila", r"\bmil gay", r"\bmil gaye\b",
                        r"\bde diy", r"\bde diye\b", r"\bjama\b", r"\bdiya hai\b", r"\bdiye hai", r"मिल गए",
                        r"दे दिए", r"दे दिया", r"जमा", r"record (a )?payment", r"\bgot\b.*\bpayment\b",
                        r"pay kar diya", r"\bpaid us\b", r"bhar diya", r"\bchuka")
        overdue_word = has(r"overdue", r"past due", r"due date (nikal|guzar|cross)", r"ओवरड्यू", r"\blate\b",
                           r"samay par nahi", r"time pe nahi")
        dashboard_word = has(r"dashboard", r"\bsummary\b", r"\boverview\b", r"hisaab kitaab", r"hisab kitab",
                             r"business kaisa", r"\bkul\b", r"\btotal outstanding\b", r"\bcollection\b",
                             r"कुल", r"सारांश", r"\bsab ka\b", r"\bsabka\b", r"how is (my )?business")
        balance_word = has(r"baaki", r"\bbaki\b", r"bakaya", r"\bbalance\b", r"\bowe", r"outstanding",
                           r"\bdues?\b", r"udhaar", r"udhar", r"बाकी", r"बकाया", r"उधार", r"how much",
                           r"kitna (dena|lena|paisa)", r"\bkitna\b")
        search_word = has(r"\bfind\b", r"\bsearch\b", r"dhundo", r"dhoondo", r"khojo", r"\bphone\b",
                          r"\bnumber\b", r"\bcontact\b", r"\bdetails?\b", r"\bcustomers?\b", r"ढूंढो",
                          r"\blook up\b", r"\bwho is\b")
        has_customer = bool(ent.customer_name or ent.customer_phone)

        itype: str
        conf = 0.9
        if is_greeting:
            itype = "smalltalk"
        elif reminder_word and list_word and not (set_word and ent.date):
            itype = "list_customer_reminders"
        elif reminder_word:
            itype = "schedule_reminder"
        elif commit_word and not paid_word:
            itype = "record_payment_commitment"
        elif paid_word:
            itype = "record_payment"
        elif overdue_word and not has_customer:
            itype = "list_overdue_invoices"
        elif ent.invoice_number:
            itype = "get_invoice_details"
        elif dashboard_word and not has_customer:
            itype = "get_dashboard_summary"
        elif balance_word or overdue_word:
            itype = "get_customer_balance" if (has_customer or not dashboard_word) else "get_dashboard_summary"
        elif search_word and has_customer:
            itype = "search_customers"
        elif has_customer and len(words) <= 4:
            itype = "search_customers"
            conf = 0.6
        else:
            itype = "unsupported"
            conf = 0.3

        if itype not in ctx.allowed_intents and itype not in ("clarify", "smalltalk", "unsupported"):
            pass  # permission filtering happens in the pipeline, not here

        if itype == "search_customers" and not ent.query:
            ent.query = ent.customer_name or ent.customer_phone
        if itype not in ("schedule_reminder", "record_payment_commitment", "record_payment"):
            ent.amount_phrase = ent.amount_phrase if itype == "unsupported" else None

        missing: list[str] = []
        needs_customer = itype in ("get_customer_balance", "schedule_reminder", "record_payment_commitment",
                                   "list_customer_reminders")
        if needs_customer and not has_customer:
            missing.append("customer")
        if itype == "record_payment" and not has_customer and not ent.invoice_number:
            missing.append("customer")
        if itype in ("schedule_reminder", "record_payment_commitment") and not ent.date:
            missing.append("date")
        if itype == "record_payment" and not ent.amount_phrase:
            missing.append("amount")
        if itype == "get_invoice_details" and not ent.invoice_number:
            missing.append("invoice_number")
        return Intent(type=itype, entities=ent, confidence=conf, missing_fields=missing)  # type: ignore[arg-type]

    # ---------------- agents ----------------
    async def generate_agent_config(self, description: str, language: str | None,
                                    allowed_tools: list[str]) -> AgentConfig:
        low = description.lower()
        lang = language or detect_language(description)
        tools = {"search_customers", "get_customer_balance", "get_invoice_details"}
        if re.search(r"remind|yaad|याद|follow", low):
            tools |= {"schedule_reminder", "list_customer_reminders"}
        if re.search(r"overdue|collect|vasool|वसूली|due", low):
            tools |= {"list_overdue_invoices"}
        if re.search(r"promise|vaada|commit", low):
            tools |= {"record_payment_commitment"}
        if re.search(r"payment|record|jama", low):
            tools |= {"record_payment"}
        if re.search(r"summary|dashboard|report|hisaab", low):
            tools |= {"get_dashboard_summary"}
        # Tools explicitly named in the description are kept as requested (validated later).
        for named in re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", low):
            tools.add(named)
        name_m = re.search(r"(?:called|named|naam)\s+\"?([\w ]{2,40}?)\"?(?:[.,]|$)", description, re.I)
        name = name_m.group(1).strip() if name_m else "Collections Assistant"
        instructions = (
            "You help the shopkeeper manage customers, dues and reminders. Be brief and polite. "
            f"Focus: {description.strip()}"
        )
        return AgentConfig(name=name[:120], description=description[:1000], language=lang,  # type: ignore[arg-type]
                           instructions=instructions[:4000], enabled_tools=sorted(tools), knowledge_sources=[])

    async def compose_reply(self, text: str, language: str, agent_instructions: str | None) -> str:
        return t("smalltalk", language)

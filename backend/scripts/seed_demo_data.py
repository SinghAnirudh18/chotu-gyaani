"""Idempotent synthetic demo data: business "Sharma Traders" with two customers
named Ramesh, several invoices, and one overdue invoice for Ramesh Gupta.

Usage: uv run python -m scripts.seed_demo_data
"""
import asyncio
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.db.models import Business, BusinessMember, Customer, Invoice, Payment, User
from app.db.session import dispose_engine, get_sessionmaker
from app.utils.dates import today_in
from app.utils.text import normalize_name

DEMO_EMAIL = "owner@sharmatraders.example.com"
DEMO_PASSWORD = "Demo12345"
BUSINESS_NAME = "Sharma Traders"

CUSTOMERS = [
    ("Ramesh Gupta", "+919812345601"),
    ("Ramesh Verma", "+919812345602"),
    ("Sunita Devi", "+919812345603"),
    ("Mohan Lal", "+919812345604"),
]


async def seed(db: AsyncSession, *, email: str = DEMO_EMAIL, password: str = DEMO_PASSWORD) -> dict:
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        user = User(email=email, password_hash=hash_password(password), name="Rajesh Sharma",
                    preferred_language="hi-Latn")
        db.add(user)
        await db.flush()
    biz = (await db.execute(
        select(Business).join(BusinessMember, BusinessMember.business_id == Business.id)
        .where(BusinessMember.user_id == user.id, Business.name == BUSINESS_NAME))).scalar_one_or_none()
    if biz is None:
        biz = Business(name=BUSINESS_NAME, timezone="Asia/Kolkata", default_language="hi-Latn")
        db.add(biz)
        await db.flush()
        db.add(BusinessMember(business_id=biz.id, user_id=user.id, role="owner"))
        await db.flush()

    customers: dict[str, Customer] = {}
    for name, phone in CUSTOMERS:
        c = (await db.execute(select(Customer).where(Customer.business_id == biz.id, Customer.name == name))
             ).scalar_one_or_none()
        if c is None:
            c = Customer(business_id=biz.id, name=name, name_normalized=normalize_name(name), phone_e164=phone)
            db.add(c)
            await db.flush()
        customers[name] = c

    today = today_in(biz.timezone)
    invoices = [
        # number, customer, total (paise), issued offset, due offset
        ("INV-1001", "Ramesh Gupta", 1_250_000, -40, -10),   # overdue, partially paid
        ("INV-1002", "Ramesh Verma", 800_000, -5, 20),
        ("INV-1003", "Sunita Devi", 450_000, -20, 5),
        ("INV-1004", "Mohan Lal", 2_000_000, -3, 27),
        ("INV-1005", "Ramesh Gupta", 300_000, -2, 28),
    ]
    inv_rows: dict[str, Invoice] = {}
    for number, cname, total, issued, due in invoices:
        inv = (await db.execute(select(Invoice).where(Invoice.business_id == biz.id, Invoice.number == number))
               ).scalar_one_or_none()
        if inv is None:
            inv = Invoice(business_id=biz.id, customer_id=customers[cname].id, number=number, total_paise=total,
                          issued_on=today + timedelta(days=issued), due_on=today + timedelta(days=due),
                          description=f"Goods supplied ({number})")
            db.add(inv)
            await db.flush()
        inv_rows[number] = inv

    has_payment = (await db.execute(select(Payment).where(Payment.invoice_id == inv_rows["INV-1001"].id))).first()
    if not has_payment:
        db.add(Payment(business_id=biz.id, invoice_id=inv_rows["INV-1001"].id, amount_paise=250_000,
                       paid_on=today - timedelta(days=15), method="upi"))
    await db.commit()
    return {"user_id": user.id, "business_id": biz.id, "email": email, "password": password,
            "customers": {k: v.id for k, v in customers.items()},
            "invoices": {k: v.id for k, v in inv_rows.items()}}


async def main() -> None:
    async with get_sessionmaker()() as db:
        out = await seed(db)
    await dispose_engine()
    print(f"Seeded business {out['business_id']} ({BUSINESS_NAME})")
    print(f"Login: {out['email']} / {out['password']}")
    print(f"Use header X-Business-ID: {out['business_id']}")


if __name__ == "__main__":
    asyncio.run(main())

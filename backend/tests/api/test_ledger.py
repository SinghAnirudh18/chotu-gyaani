from datetime import date, timedelta

from tests.conftest import make_customer, make_invoice, owner_with_business

TODAY = date.today()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()  # noqa: E731


async def test_customer_crud_search_and_pagination(client) -> None:  # type: ignore[no-untyped-def]
    owner = await owner_with_business(client)
    g = await make_customer(owner, "Ramesh Gupta", "98123 45601")
    assert g["phone_e164"] == "+919812345601"
    await make_customer(owner, "Ramesh Verma")
    await make_customer(owner, "Sunita Devi")
    r = await owner.post("/customers", json={"name": "Bad", "phone": "123"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_phone"

    r = await owner.get("/customers", params={"page_size": 2})
    assert r.json()["meta"] == {"page": 1, "page_size": 2, "total": 3} and len(r.json()["data"]) == 2
    r = await owner.get("/customers", params={"q": "रमेश"})  # Devanagari finds Latin names
    assert {c["name"] for c in r.json()["data"]} == {"Ramesh Gupta", "Ramesh Verma"}
    r = await owner.get("/customers", params={"q": "Suneeta"})
    assert [c["name"] for c in r.json()["data"]] == ["Sunita Devi"]
    r = await owner.get("/customers", params={"phone": "+91 98123 45601"})
    assert [c["id"] for c in r.json()["data"]] == [g["id"]]

    r = await owner.patch(f"/customers/{g['id']}", json={"name": "Ramesh K Gupta", "notes": "VIP"})
    assert r.status_code == 200 and r.json()["data"]["name"] == "Ramesh K Gupta"
    r = await owner.get(f"/customers/{g['id']}")
    assert r.json()["data"]["balance"]["outstanding_paise"] == 0
    r = await owner.delete(f"/customers/{g['id']}")
    assert r.status_code == 200 and r.json()["data"]["archived_at"]
    assert r.json()["meta"] == {}
    assert (await owner.get("/customers")).json()["meta"]["total"] == 2
    assert (await owner.get("/customers", params={"include_archived": "true"})).json()["meta"]["total"] == 3
    assert (await owner.patch(f"/customers/{g['id']}", json={"name": "x"})).status_code == 404


async def test_customer_csv_import(client) -> None:  # type: ignore[no-untyped-def]
    owner = await owner_with_business(client)
    await make_customer(owner, "Existing", "+919812345699")
    csv_data = ("name,phone,email\nAsha,9812345611,asha@example.com\n,9812345612,\nBadPhone,12,\n"
                "Dup,+919812345699,\nRavi,,ravi@example.com\n")
    files = {"file": ("customers.csv", csv_data.encode(), "text/csv")}
    r = await owner.post("/customers/import", files=files)
    body = r.json()["data"]
    assert r.status_code == 200 and body["dry_run"] is True
    assert body["valid_count"] == 2 and body["error_count"] == 3 and body["created"] == 0
    assert {e["row"] for e in body["errors"]} == {3, 4, 5}
    r = await owner.post("/customers/import", params={"dry_run": "false"}, files=files)
    assert r.json()["data"]["created"] == 2
    assert (await owner.get("/customers")).json()["meta"]["total"] == 3
    r = await owner.post("/customers/import", files={"file": ("x.csv", b"foo,bar\n1,2\n", "text/csv")})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_csv"


async def test_invoices_balances_filters_and_payments(client) -> None:  # type: ignore[no-untyped-def]
    owner = await owner_with_business(client)
    c = await make_customer(owner, "Ramesh Gupta")
    c2 = await make_customer(owner, "Sunita Devi")
    overdue = await make_invoice(owner, c["id"], "INV-1", 100000, D(-30), D(-1))
    future = await make_invoice(owner, c["id"], "INV-2", 50000, D(-1), D(10))
    other = await make_invoice(owner, c2["id"], "INV-3", 70000, D(-1), D(5))
    assert overdue["is_overdue"] and not future["is_overdue"] and overdue["total_display"] == "₹1,000"
    r = await owner.post("/invoices", json={"customer_id": c["id"], "number": "INV-1", "total_paise": 1,
                                            "issued_on": D(0), "due_on": D(1)})
    assert r.status_code == 409 and r.json()["error"]["code"] == "invoice_number_taken"
    r = await owner.post("/invoices", json={"customer_id": c["id"], "number": "INV-X", "total_paise": 100,
                                            "issued_on": D(5), "due_on": D(1)})
    assert r.status_code == 422
    r = await owner.post("/invoices", json={"customer_id": c["id"], "number": "INV-Y", "total_paise": 0,
                                            "issued_on": D(0), "due_on": D(1)})
    assert r.status_code == 422

    assert (await owner.get("/invoices", params={"overdue": "true"})).json()["meta"]["total"] == 1
    assert (await owner.get("/invoices", params={"customer_id": c["id"]})).json()["meta"]["total"] == 2
    assert (await owner.get("/invoices", params={"overdue": "false"})).json()["meta"]["total"] == 2

    # Partial payment via a confirmed action.
    r = await owner.post(f"/invoices/{overdue['id']}/payments", json={"amount_paise": 40000, "method": "upi"})
    assert r.status_code == 202 and r.json()["data"]["type"] == "record_payment"
    assert (await owner.post(f"/actions/{r.json()['data']['id']}/confirm")).status_code == 200
    inv = (await owner.get(f"/invoices/{overdue['id']}")).json()["data"]
    assert inv["paid_paise"] == 40000 and inv["balance_paise"] == 60000 and inv["status"] == "open"
    # Remaining payment marks it paid.
    r = await owner.post(f"/invoices/{overdue['id']}/payments", json={"amount_paise": 60000})
    await owner.post(f"/actions/{r.json()['data']['id']}/confirm")
    inv = (await owner.get(f"/invoices/{overdue['id']}")).json()["data"]
    assert inv["status"] == "paid" and inv["balance_paise"] == 0 and not inv["is_overdue"]
    pays = (await owner.get(f"/invoices/{overdue['id']}/payments")).json()
    assert pays["meta"]["total"] == 2 and pays["data"][0]["amount_display"]
    assert (await owner.get("/payments", params={"customer_id": c["id"]})).json()["meta"]["total"] == 2
    assert (await owner.get("/payments", params={"customer_id": c2["id"]})).json()["meta"]["total"] == 0
    # Paid invoice cannot take more payments; void rules.
    r = await owner.post(f"/invoices/{overdue['id']}/payments", json={"amount_paise": 1})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invoice_not_open"
    assert (await owner.patch(f"/invoices/{overdue['id']}", json={"status": "void"})).status_code == 409
    r = await owner.patch(f"/invoices/{other['id']}", json={"status": "void", "description": "cancelled order"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "void" and r.json()["data"]["balance_paise"] == 0
    r = await owner.patch(f"/invoices/{future['id']}", json={"total_paise": 80000, "due_on": D(20)})
    assert r.json()["data"]["balance_paise"] == 80000
    cust = (await owner.get(f"/customers/{c['id']}")).json()["data"]
    assert cust["balance"]["outstanding_paise"] == 80000


async def test_reminders_crud(client) -> None:  # type: ignore[no-untyped-def]
    owner = await owner_with_business(client)
    c = await make_customer(owner, "Ramesh Gupta")
    other = await make_customer(owner, "Sunita Devi")
    inv = await make_invoice(owner, c["id"], "INV-1", 100000, D(-5), D(5))
    r = await owner.post("/reminders", json={"customer_id": c["id"], "scheduled_at": "2001-01-01T00:00:00Z"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "date_in_past"
    r = await owner.post("/reminders", json={"customer_id": other["id"], "invoice_id": inv["id"],
                                             "scheduled_at": "2099-01-01T10:00:00Z"})
    assert r.status_code == 422
    r = await owner.post("/reminders", json={"customer_id": c["id"], "invoice_id": inv["id"],
                                             "scheduled_at": "2099-01-01T10:00:00+05:30", "channel": "sms"})
    assert r.status_code == 201
    rem = r.json()["data"]
    assert rem["status"] == "scheduled" and rem["scheduled_at"].startswith("2099-01-01T04:30")
    await owner.post("/reminders", json={"customer_id": other["id"], "scheduled_at": "2099-02-01T10:00:00Z"})
    assert (await owner.get("/reminders", params={"customer_id": c["id"]})).json()["meta"]["total"] == 1
    assert (await owner.get("/reminders", params={"upcoming": "true"})).json()["meta"]["total"] == 2
    assert (await owner.get("/reminders", params={"invoice_id": inv["id"]})).json()["meta"]["total"] == 1
    r = await owner.patch(f"/reminders/{rem['id']}", json={"channel": "whatsapp", "message": "Please pay"})
    assert r.status_code == 200 and r.json()["data"]["channel"] == "whatsapp"
    r = await owner.post(f"/reminders/{rem['id']}/cancel")
    assert r.status_code == 200 and r.json()["data"]["status"] == "cancelled"
    assert (await owner.post(f"/reminders/{rem['id']}/cancel")).status_code == 409
    assert (await owner.patch(f"/reminders/{rem['id']}", json={"channel": "sms"})).status_code == 409
    assert (await owner.get("/reminders", params={"status": "cancelled"})).json()["meta"]["total"] == 1
    second = (await owner.get("/reminders", params={"status": "scheduled"})).json()["data"][0]
    r = await owner.post(f"/reminders/{second['id']}/complete")
    assert r.status_code == 200 and r.json()["data"]["status"] == "completed" and r.json()["data"]["completed_at"]
    assert (await owner.get(f"/reminders/{second['id']}")).json()["data"]["status"] == "completed"


async def test_payment_commitments_crud(client) -> None:  # type: ignore[no-untyped-def]
    owner = await owner_with_business(client)
    c = await make_customer(owner, "Mohan Lal")
    r = await owner.post("/payment-commitments", json={"customer_id": c["id"], "promised_on": D(-1)})
    assert r.status_code == 422
    r = await owner.post("/payment-commitments", json={"customer_id": c["id"], "promised_on": D(3),
                                                       "promised_amount_paise": 500000})
    assert r.status_code == 201
    pc = r.json()["data"]
    assert pc["status"] == "open"
    assert (await owner.get("/payment-commitments", params={"status": "open"})).json()["meta"]["total"] == 1
    assert (await owner.get(f"/payment-commitments/{pc['id']}")).status_code == 200
    r = await owner.patch(f"/payment-commitments/{pc['id']}", json={"status": "kept"})
    assert r.json()["data"]["status"] == "kept"
    r = await owner.delete(f"/payment-commitments/{pc['id']}")
    assert r.json()["data"]["status"] == "cancelled"
    assert (await owner.patch(f"/payment-commitments/{pc['id']}", json={"notes": "x"})).status_code == 409
    assert (await owner.get("/payments")).json()["meta"]["total"] == 0

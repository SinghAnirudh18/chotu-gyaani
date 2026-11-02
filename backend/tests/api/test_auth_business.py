from tests.conftest import Account, add_member, make_customer, owner_with_business, register


async def test_health_and_ready(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.get("/health")
    assert r.status_code == 200 and r.json() == {"data": {"status": "ok"}, "meta": {}}
    assert r.headers["x-request-id"]
    r = await client.get("/ready")
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["checks"]["database"] == "ok" and body["checks"]["providers"]["llm"] == "mock"


async def test_register_login_me(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post("/auth/register", json={"email": "New@Example.com", "password": "Passw0rd!", "name": "N"})
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["user"]["email"] == "new@example.com"
    assert data["tokens"]["token_type"] == "bearer" and data["tokens"]["expires_in"] == 900
    assert "password_hash" not in data["user"]
    r = await client.post("/auth/register", json={"email": "new@example.com", "password": "Passw0rd!", "name": "N"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"
    r = await client.post("/auth/register", json={"email": "weak@example.com", "password": "short", "name": "N"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "weak_password"
    r = await client.post("/auth/register", json={"email": "not-an-email", "password": "Passw0rd!", "name": "N"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"

    r = await client.post("/auth/login", json={"email": "NEW@example.com", "password": "Passw0rd!"})
    assert r.status_code == 200
    token = r.json()["data"]["tokens"]["access_token"]
    r = await client.post("/auth/login", json={"email": "new@example.com", "password": "wrong-pass1"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_credentials"

    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["data"]["user"]["email"] == "new@example.com" and r.json()["data"]["memberships"] == []


async def test_patch_me_and_password_change(client) -> None:  # type: ignore[no-untyped-def]
    acc = await register(client, "p@example.com")
    r = await acc.patch("/auth/me", json={"name": "Renamed", "preferred_language": "hi"})
    assert r.status_code == 200 and r.json()["data"]["user"]["name"] == "Renamed"
    r = await acc.patch("/auth/me", json={"current_password": "bad", "new_password": "NewPass123"})
    assert r.status_code == 401
    r = await acc.patch("/auth/me", json={"current_password": "Passw0rd!", "new_password": "NewPass123"})
    assert r.status_code == 200
    r = await client.post("/auth/login", json={"email": "p@example.com", "password": "NewPass123"})
    assert r.status_code == 200


async def test_refresh_rotation_reuse_and_logout(client) -> None:  # type: ignore[no-untyped-def]
    r = await client.post("/auth/register", json={"email": "r@example.com", "password": "Passw0rd!", "name": "R"})
    rt1 = r.json()["data"]["tokens"]["refresh_token"]
    r = await client.post("/auth/refresh", json={"refresh_token": rt1})
    assert r.status_code == 200
    rt2 = r.json()["data"]["tokens"]["refresh_token"]
    access = r.json()["data"]["tokens"]["access_token"]
    assert rt2 != rt1
    # Reusing the rotated token revokes the whole family.
    r = await client.post("/auth/refresh", json={"refresh_token": rt1})
    assert r.status_code == 401 and r.json()["error"]["code"] == "refresh_token_reused"
    r = await client.post("/auth/refresh", json={"refresh_token": rt2})
    assert r.status_code == 401
    # Logout revokes a token.
    r = await client.post("/auth/login", json={"email": "r@example.com", "password": "Passw0rd!"})
    rt3 = r.json()["data"]["tokens"]["refresh_token"]
    r = await client.post("/auth/logout", json={"refresh_token": rt3}, headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    r = await client.post("/auth/refresh", json={"refresh_token": rt3})
    assert r.status_code == 401
    r = await client.post("/auth/logout", json={"all_sessions": True}, headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200


async def test_forgot_and_reset_password(client) -> None:  # type: ignore[no-untyped-def]
    await register(client, "f@example.com")
    r = await client.post("/auth/forgot-password", json={"email": "unknown@example.com"})
    assert r.status_code == 202 and "debug_reset_token" not in r.json()["data"]
    r = await client.post("/auth/forgot-password", json={"email": "f@example.com"})
    assert r.status_code == 202
    token = r.json()["data"]["debug_reset_token"]
    r = await client.post("/auth/reset-password", json={"token": token, "new_password": "Brand1New"})
    assert r.status_code == 200
    r = await client.post("/auth/reset-password", json={"token": token, "new_password": "Brand2New"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_reset_token"
    r = await client.post("/auth/login", json={"email": "f@example.com", "password": "Brand1New"})
    assert r.status_code == 200


async def test_business_create_me_patch(client) -> None:  # type: ignore[no-untyped-def]
    owner = await owner_with_business(client)
    r = await owner.get("/businesses/me")
    b = r.json()["data"]
    assert r.status_code == 200 and b["role"] == "owner"
    assert b["business"]["timezone"] == "Asia/Kolkata" and b["business"]["currency"] == "INR"
    r = await owner.patch("/businesses/me", json={"name": "Sharma & Sons", "default_language": "en"})
    assert r.status_code == 200 and r.json()["data"]["business"]["name"] == "Sharma & Sons"
    r = await owner.patch("/businesses/me", json={"timezone": "Mars/Base"})
    assert r.status_code == 422
    r = await client.post("/businesses", json={"name": ""}, headers={"Authorization": f"Bearer {owner.token}"})
    assert r.status_code == 422
    me = (await client.get("/auth/me", headers={"Authorization": f"Bearer {owner.token}"})).json()["data"]
    assert me["memberships"][0]["role"] == "owner"


async def test_members_invite_roles_and_removal(client) -> None:  # type: ignore[no-untyped-def]
    owner = await owner_with_business(client)
    admin = await add_member(owner, "admin@example.com", "admin")
    member = await add_member(owner, "member@example.com", "member")
    r = await owner.get("/members")
    assert r.status_code == 200 and {m["role"] for m in r.json()["data"]} == {"owner", "admin", "member"}
    # Members cannot manage; admins cannot promote to admin/owner.
    assert (await member.post("/members/invite", json={"email": "x@example.com"})).status_code == 403
    r = await admin.patch(f"/members/{member.user_id}", json={"role": "admin"})
    assert r.status_code == 403
    r = await admin.post("/members/invite", json={"email": "z@example.com", "role": "admin"})
    assert r.status_code == 403
    # Duplicate invite of an existing member.
    assert (await owner.post("/members/invite", json={"email": "member@example.com"})).status_code == 409
    # Invitation for someone else's email is not usable.
    r = await owner.post("/members/invite", json={"email": "other@example.com"})
    stranger = await register(client, "stranger@example.com")
    r2 = await client.post("/invitations/accept", json={"token": r.json()["data"]["debug_invite_token"]},
                           headers=stranger.headers)
    assert r2.status_code == 404
    # Last owner cannot be demoted or removed.
    r = await owner.patch(f"/members/{owner.user_id}", json={"role": "member"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "last_owner"
    assert (await owner.delete(f"/members/{owner.user_id}")).status_code == 422
    r = await owner.patch(f"/members/{member.user_id}", json={"role": "admin"})
    assert r.status_code == 200 and r.json()["data"]["role"] == "admin"
    r = await owner.delete(f"/members/{member.user_id}")
    assert r.status_code == 200
    assert (await member.get("/businesses/me")).status_code == 404


async def test_export_and_delete_business(client) -> None:  # type: ignore[no-untyped-def]
    owner = await owner_with_business(client)
    admin = await add_member(owner, "admin@example.com", "admin")
    await make_customer(owner, "Ramesh Gupta", "+919812345601")
    r = await owner.get("/export")
    assert r.status_code == 200
    exported = r.json()["data"]
    assert exported["customers"][0]["name"] == "Ramesh Gupta" and "invoices" in exported
    assert (await admin.delete("/businesses/me")).status_code == 403
    r = await owner.delete("/businesses/me")
    assert r.status_code == 200
    assert (await owner.get("/businesses/me")).status_code == 404
    assert (await admin.get("/customers")).status_code == 404


async def test_member_role_matrix_on_routes(client) -> None:  # type: ignore[no-untyped-def]
    owner = await owner_with_business(client)
    member: Account = await add_member(owner, "m@example.com", "member")
    admin: Account = await add_member(owner, "a@example.com", "admin")
    member_denied = [("patch", "/businesses/me", {"name": "x"}), ("get", "/audit-logs", None), ("get", "/usage", None),
                     ("get", "/export", None), ("post", "/agents", {"name": "x"}), ("get", "/integrations", None),
                     ("delete", "/businesses/me", None)]
    for method, url, body in member_denied:
        kw = {"json": body} if body is not None else {}
        assert (await getattr(member, method)(url, **kw)).status_code == 403, url
    for method, url in [("get", "/audit-logs"), ("get", "/usage"), ("get", "/export")]:
        assert (await getattr(admin, method)(url)).status_code == 200, url
    assert (await admin.get("/integrations")).status_code == 403
    c = await make_customer(member, "Member Made")
    assert (await member.delete(f"/customers/{c['id']}")).status_code == 403
    assert (await admin.delete(f"/customers/{c['id']}")).status_code == 200

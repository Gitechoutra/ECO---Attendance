from tests.conftest import PASSWORD, Actor, login, make_person


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["database"] is True


def test_login_success_and_me(client, admin):
    r = admin.get("/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["role"]["code"] == "super_admin"
    assert "payroll.manage" in body["permissions"]


def test_login_wrong_password_and_unknown_user(client):
    p = make_person("employee")
    assert client.post("/api/v1/auth/login", json={"email": p["email"], "password": "nope"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "x"}).status_code == 401


def test_login_invalid_input(client):
    r = client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": "x"})
    assert r.status_code == 422
    assert "detail" in r.json()


def test_lockout_after_repeated_failures(client):
    p = make_person("employee")
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": p["email"], "password": "bad"})
    r = client.post("/api/v1/auth/login", json={"email": p["email"], "password": PASSWORD})
    assert r.status_code == 423


def test_unauthenticated_and_bad_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_refresh_rotation_and_reuse_detection(client):
    p = make_person("employee")
    r = client.post("/api/v1/auth/login", json={"email": p["email"], "password": PASSWORD}).json()
    rt1 = r["refresh_token"]
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": rt1})
    assert r2.status_code == 200
    rt2 = r2.json()["refresh_token"]
    assert rt2 != rt1
    # Reusing the rotated token revokes the whole family
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": rt1}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": rt2}).status_code == 401


def test_logout_revokes_refresh(client):
    p = make_person("employee")
    r = client.post("/api/v1/auth/login", json={"email": p["email"], "password": PASSWORD}).json()
    client.post("/api/v1/auth/logout", json={"refresh_token": r["refresh_token"]})
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": r["refresh_token"]}).status_code == 401


def test_change_password_rules_and_session_invalidation(client):
    a = Actor(client, "employee")
    weak = a.post("/auth/change-password", json={"current_password": PASSWORD, "new_password": "alllowercase1"})
    assert weak.status_code == 422
    wrong = a.post("/auth/change-password", json={"current_password": "x", "new_password": "NewPassw0rd"})
    assert wrong.status_code == 400
    ok = a.post("/auth/change-password", json={"current_password": PASSWORD, "new_password": "NewPassw0rd"})
    assert ok.status_code == 200
    # old access token is invalid (token version bumped)
    assert a.get("/auth/me").status_code == 401
    assert login(client, a.info["email"], "NewPassw0rd")


def test_employee_role_restrictions(client, employee):
    for url in ["/employees", "/payroll/runs", "/admin/users", "/admin/audit", "/attendance/live",
                "/recruitment/jobs", "/offers", "/reports/payroll", "/clients"]:
        assert employee.get(url).status_code == 403, url
    assert employee.post("/departments", json={"name": "Hack", "code": "HK"}).status_code == 403
    assert employee.post("/projects", json={"name": "Nope"}).status_code == 403


def test_project_manager_restrictions(client, pm):
    assert pm.get("/employees").status_code == 403
    assert pm.get("/payroll/runs").status_code == 403
    assert pm.post("/employees", json={"first_name": "X", "email": "x@example.com", "joining_date": "2025-01-01"}).status_code == 403
    assert pm.get("/clients").status_code == 200  # scoped list


def test_hr_access(client, hr):
    assert hr.get("/employees").status_code == 200
    assert hr.get("/payroll/runs").status_code == 200
    assert hr.get("/admin/settings").status_code == 200
    assert hr.put("/admin/roles/2", json={"name": "x", "permissions": []}).status_code == 403  # no admin.roles

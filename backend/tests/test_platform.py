import json

from sqlalchemy.exc import OperationalError

from tests.conftest import Actor


def test_reports_all_formats(admin):
    kinds = [r["key"] for r in admin.get("/reports").json()]
    assert set(kinds) >= {"attendance", "employees", "leave", "projects", "tasks", "clients", "payroll", "expenses", "recruitment"}
    for k in kinds:
        j = admin.get(f"/reports/{k}?date_from=2025-01-01&date_to=2026-12-31")
        assert j.status_code == 200, (k, j.text)
        assert set(j.json()) >= {"columns", "rows", "summary"}
        x = admin.get(f"/reports/{k}?date_from=2025-01-01&date_to=2026-12-31&format=xlsx")
        assert x.status_code == 200 and x.content[:2] == b"PK", k
        p = admin.get(f"/reports/{k}?date_from=2025-01-01&date_to=2026-12-31&format=pdf")
        assert p.status_code == 200 and p.content.startswith(b"%PDF"), k
    assert admin.get("/reports/attendance?date_from=2026-05-01&date_to=2026-01-01").status_code == 422


def test_reports_forbidden_for_employee(employee):
    assert employee.get("/reports").json() == []
    assert employee.get("/reports/payroll").status_code == 403


def test_dashboards_by_role(admin, pm, employee):
    a = admin.get("/dashboard").json()
    assert "company" in a and "headcount" in a["company"]
    e = employee.get("/dashboard").json()
    assert "company" not in e and "personal" in e


def test_ai_not_configured_and_tool_scoping(client, employee, admin, db_session):
    st = employee.get("/ai/status").json()
    assert st["configured"] is False
    r = employee.post("/ai/chat", json={"message": "hello"})
    assert r.status_code == 503 and "GEMINI_API_KEY" in r.json()["detail"]
    from app.api.deps import CurrentUser
    from app.models import User
    from app.services.ai import tool_preview
    from app.services.authz import effective_permissions
    u = db_session.get(User, employee.user_id)
    cu = CurrentUser(user=u, perms=effective_permissions(u))
    assert "not authorized" in json.loads(tool_preview(db_session, cu, "get_payroll_summary"))["error"]
    assert "not authorized" in json.loads(tool_preview(db_session, cu, "get_workforce_overview"))["error"]
    own = json.loads(tool_preview(db_session, cu, "get_attendance_summary"))
    assert all(r["name"] == employee.info["name"] for r in own["employees"])
    au = db_session.get(User, admin.user_id)
    ca = CurrentUser(user=au, perms=effective_permissions(au))
    assert "by_department" in json.loads(tool_preview(db_session, ca, "get_workforce_overview"))


def test_email_integration_requires_configuration(employee, hr):
    st = hr.get("/email/status").json()
    assert st["gmail"] is False and st["outlook"] is False
    r = hr.post("/email/connect", json={"provider": "gmail"})
    assert r.status_code == 503
    assert hr.get("/email/messages").json()["items"] == []
    assert employee.get("/email/accounts").status_code == 403


def test_admin_roles_overrides_and_safety(client, admin):
    target = Actor(client, "employee")
    assert target.get("/employees").status_code == 403
    r = admin.put(f"/admin/users/{target.user_id}/permissions", json={"code": "employees.view_all", "granted": True})
    assert r.status_code == 200 and "employees.view_all" in r.json()["effective"]
    assert target.get("/employees").status_code == 200
    admin.put(f"/admin/users/{target.user_id}/permissions", json={"code": "employees.view_all", "granted": None})
    assert target.get("/employees").status_code == 403
    # cannot demote yourself / remove last super admin
    assert admin.put(f"/admin/users/{admin.user_id}", json={"role_code": "employee", "is_active": True}).status_code == 400
    roles = admin.get("/admin/roles").json()
    sa = next(r for r in roles if r["code"] == "super_admin")
    assert admin.put(f"/admin/roles/{sa['id']}", json={"name": "Root", "permissions": []}).status_code == 409
    emp_role = next(r for r in roles if r["code"] == "employee")
    ok = admin.put(f"/admin/roles/{emp_role['id']}", json={"name": "Employee", "permissions": emp_role["permissions"]})
    assert ok.status_code == 200


def test_settings_validation_and_audit(admin):
    s = admin.get("/admin/settings").json()
    body = {k: s[k] for k in ("company_name", "timezone", "currency", "employee_code_prefix", "work_start", "work_end",
                              "grace_minutes", "half_day_minutes", "full_day_minutes", "weekly_offs",
                              "biometric_retention_days", "session_timeout_minutes", "require_face_for_attendance")}
    assert admin.put("/admin/settings", json={**body, "timezone": "Mars/Base"}).status_code == 422
    assert admin.put("/admin/settings", json={**body, "work_end": "08:00"}).status_code == 422
    logs = admin.get("/admin/audit?action=settings").json()
    assert logs["total"] >= 1


def test_notifications_flow(client, hr):
    e = Actor(client, "employee")
    hr.post("/announcements", json={"title": "Notify test", "body": "Body"})
    n = e.get("/notifications").json()
    assert n["unread_count"] >= 1
    e.post("/notifications/read-all")
    assert e.get("/notifications").json()["unread_count"] == 0


def test_database_failure_returns_503(client, admin):
    from app.db.session import get_db
    from app.main import app

    def broken():
        raise OperationalError("SELECT 1", {}, Exception(2003, "Can't connect"))
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = broken
    try:
        r = client.get("/api/v1/departments", headers=admin.headers)
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 503


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"

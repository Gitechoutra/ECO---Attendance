from datetime import date, timedelta

from tests.conftest import Actor


def test_project_client_task_flow(client, admin, pm):
    member = Actor(client, "employee")
    outsider = Actor(client, "employee")
    c = admin.post("/clients", json={"name": "Acme Retail", "email": "it@acme.example.com", "status": "active"})
    assert c.status_code == 201, c.text
    cid = c.json()["id"]
    p = admin.post("/projects", json={"name": "Acme POS Revamp", "client_id": cid, "manager_id": pm.employee_id,
                                      "start_date": str(date.today()), "end_date": str(date.today() + timedelta(days=60)),
                                      "status": "active"})
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    # project automatically appears in the client's project history
    assert any(x["id"] == pid for x in admin.get(f"/clients/{cid}/projects").json())
    # PM can see/manage; outsider cannot see
    assert pm.get(f"/projects/{pid}").json()["can_manage"] is True
    assert outsider.get(f"/projects/{pid}").status_code == 403
    # PM sees the client (scoped)
    assert any(x["id"] == cid for x in pm.get("/clients").json()["items"])
    # PM adds member; duplicate rejected
    assert pm.post(f"/projects/{pid}/members", json={"employee_id": member.employee_id, "role": "Developer"}).status_code == 201
    assert pm.post(f"/projects/{pid}/members", json={"employee_id": member.employee_id}).status_code == 409
    # tasks: assignee must be a member
    assert pm.post("/tasks", json={"title": "Bad", "project_id": pid, "assignee_id": outsider.employee_id}).status_code == 422
    t = pm.post("/tasks", json={"title": "Build checkout API", "project_id": pid, "assignee_id": member.employee_id,
                                "priority": "high", "due_date": str(date.today() - timedelta(days=1)), "estimated_hours": 8})
    assert t.status_code == 201, t.text
    tid = t.json()["id"]
    assert t.json()["is_overdue"] is True
    # member sees it, outsider doesn't
    assert any(x["id"] == tid for x in member.get("/tasks?scope=mine").json()["items"])
    assert outsider.get(f"/tasks/{tid}").status_code == 403
    # member cannot edit fully but can update status / progress / comment
    assert member.put(f"/tasks/{tid}", json={"title": "Hacked"}).status_code == 403
    assert member.post(f"/tasks/{tid}/updates", json={"progress": 50, "hours_spent": 3, "note": "Endpoints done"}).status_code == 201
    assert member.post(f"/tasks/{tid}/comments", json={"body": "Need API keys"}).status_code == 201
    detail = member.get(f"/tasks/{tid}").json()
    assert detail["status"] == "in_progress" and detail["progress"] == 50
    assert len(detail["comments"]) == 1 and len(detail["updates"]) == 1 and detail["history"]
    assert pm.get(f"/projects/{pid}").json()["progress"] == 50.0
    assert member.patch(f"/tasks/{tid}/status", json={"status": "done"}).status_code == 200
    assert pm.get(f"/projects/{pid}").json()["progress"] == 100.0
    # milestones and report
    m = pm.post(f"/projects/{pid}/milestones", json={"title": "MVP", "due_date": str(date.today() + timedelta(days=20))})
    assert m.status_code == 201
    rep = pm.get(f"/projects/{pid}/report").json()
    assert rep["status_breakdown"][-1]["count"] == 1
    # project cannot be deleted while it has tasks
    assert admin.delete(f"/projects/{pid}").status_code == 409


def test_personal_tasks(employee):
    r = employee.post("/tasks", json={"title": "Prepare demo notes"})
    assert r.status_code == 201 and r.json()["assignee_id"] is None
    other = employee.post("/tasks", json={"title": "Assign to someone else", "assignee_id": 1})
    assert other.status_code == 403


def test_delayed_project_detection(admin):
    p = admin.post("/projects", json={"name": "Legacy Migration", "status": "active",
                                      "start_date": "2024-01-01", "end_date": "2024-06-30"}).json()
    delayed = admin.get("/projects?delayed=true").json()["items"]
    assert any(x["id"] == p["id"] and x["is_delayed"] for x in delayed)


def test_client_subresources(admin, employee):
    cid = admin.post("/clients", json={"name": "Globex Corp", "status": "lead"}).json()["id"]
    assert admin.post(f"/clients/{cid}/contacts", json={"name": "Hank Scorpio", "email": "hank@globex.example.com",
                                                        "is_primary": True}).status_code == 201
    assert admin.post(f"/clients/{cid}/requirements", json={"title": "Mobile app"}).status_code == 201
    assert admin.post(f"/clients/{cid}/communications", json={"channel": "call", "subject": "Kickoff call"}).status_code == 201
    assert admin.post(f"/clients/{cid}/meetings", json={"title": "Discovery",
                                                        "scheduled_at": "2030-01-10T10:00:00"}).status_code == 201
    assert admin.post(f"/clients/{cid}/feedback", json={"rating": 6, "received_at": "2026-01-01"}).status_code == 422
    assert admin.post(f"/clients/{cid}/feedback", json={"rating": 5, "received_at": "2026-01-01"}).status_code == 201
    k = admin.post(f"/clients/{cid}/contracts", json={"title": "MSA", "value": 100000, "status": "active"})
    assert k.status_code == 201
    pdf = b"%PDF-1.4 test"
    assert admin.post(f"/clients/{cid}/contracts/{k.json()['id']}/file",
                      files={"file": ("msa.pdf", pdf, "application/pdf")}).status_code == 200
    detail = admin.get(f"/clients/{cid}").json()
    assert detail["primary_contact"]["name"] == "Hank Scorpio" and detail["avg_rating"] == 5.0
    comms = admin.get(f"/clients/{cid}/communications").json()
    assert len(comms) == 2  # call + meeting auto-logged
    assert employee.get(f"/clients/{cid}").status_code == 403
    assert admin.post("/clients", json={"name": "globex corp"}).status_code == 409


def test_global_search_respects_scope(admin, employee):
    admin.post("/clients", json={"name": "Zenith Searchable"})
    assert any(r["type"] == "client" for r in admin.get("/search?q=Zenith").json())
    assert not any(r["type"] == "client" for r in employee.get("/search?q=Zenith").json())

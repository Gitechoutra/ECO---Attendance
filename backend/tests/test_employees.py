from tests.conftest import login


def test_department_and_designation_crud(hr):
    r = hr.post("/departments", json={"name": "Engineering QA", "code": "engqa"})
    assert r.status_code == 201 and r.json()["code"] == "ENGQA"
    assert hr.post("/departments", json={"name": "engineering qa", "code": "X1"}).status_code == 409
    dep = r.json()["id"]
    d = hr.post("/designations", json={"title": "QA Engineer", "department_id": dep, "level": 2})
    assert d.status_code == 201
    assert hr.put(f"/departments/{dep}", json={"name": "Engineering QA", "code": "ENGQA", "description": "Testing"}).status_code == 200


def test_create_employee_full_flow(client, hr):
    dep = hr.post("/departments", json={"name": "Delivery", "code": "DLV"}).json()["id"]
    body = {"first_name": "Asha", "last_name": "Rao", "email": "Asha.Rao@example.com", "joining_date": "2025-03-10",
            "department_id": dep, "bank_account": "123456789012", "pan": "ABCDE1234F", "role_code": "employee"}
    r = hr.post("/employees", json=body)
    assert r.status_code == 201, r.text
    emp = r.json()
    assert emp["employee_code"].startswith("ECH")
    assert emp["email"] == "asha.rao@example.com"
    assert emp["temporary_password"]
    assert emp["bank_account"] == "123456789012"  # HR has view_sensitive
    # duplicate email rejected
    assert hr.post("/employees", json=body).status_code == 409
    # new employee can log in and must change password
    h = login(client, "asha.rao@example.com", emp["temporary_password"])
    me = client.get("/api/v1/auth/me", headers=h).json()
    assert me["must_change_password"] is True
    # available across modules: directory, leave balances
    assert any(e["id"] == emp["id"] for e in hr.get("/employees/directory").json())
    bal = client.get("/api/v1/leave/balances/me", headers=h).json()
    assert len(bal) >= 3
    # own profile hides sensitive values
    mine = client.get("/api/v1/employees/me", headers=h).json()
    assert mine["bank_account"].endswith("9012") and "•" in mine["bank_account"]


def test_employee_validation(hr):
    bad = [
        {"first_name": "", "email": "a@example.com", "joining_date": "2025-01-01"},
        {"first_name": "A", "email": "bad", "joining_date": "2025-01-01"},
        {"first_name": "A", "email": "a2@example.com", "joining_date": "2025-01-01", "date_of_birth": "2024-01-01"},
        {"first_name": "A", "email": "a3@example.com", "joining_date": "2025-01-01", "phone": "abc"},
        {"first_name": "A", "email": "a4@example.com", "joining_date": "2025-01-01", "department_id": 999999},
    ]
    for b in bad:
        assert hr.post("/employees", json=b).status_code in (409, 422), b


def test_update_history_and_deactivate(client, hr):
    emp = hr.post("/employees", json={"first_name": "Ravi", "email": "ravi.k@example.com", "joining_date": "2025-02-01"}).json()
    upd = {k: emp[k] for k in ("first_name", "last_name", "email", "joining_date")}
    upd["phone"] = "+91 98765 43210"
    assert hr.put(f"/employees/{emp['id']}", json=upd).status_code == 200
    hist = hr.get(f"/employees/{emp['id']}/history").json()
    assert any(h["event_type"] in ("updated", "created") for h in hist) and len(hist) >= 2
    pw = emp["temporary_password"]
    assert login(client, "ravi.k@example.com", pw)
    r = hr.post(f"/employees/{emp['id']}/deactivate", json={"exit_date": "2025-12-31", "exit_reason": "Resigned"})
    assert r.status_code == 200 and r.json()["status"] == "inactive"
    assert client.post("/api/v1/auth/login", json={"email": "ravi.k@example.com", "password": pw}).status_code == 403


def test_document_upload_and_access(client, hr, employee):
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    r = hr.post(f"/employees/{employee.employee_id}/documents", files={"file": ("id.png", png, "image/png")},
                data={"category": "id_proof"})
    assert r.status_code == 201, r.text
    fid = r.json()["id"]
    assert employee.get(f"/files/{fid}").status_code == 200  # own document
    other = client.post  # noqa: F841
    # spoofed content type rejected
    bad = hr.post(f"/employees/{employee.employee_id}/documents", files={"file": ("x.pdf", b"not a pdf", "application/pdf")})
    assert bad.status_code == 415


def test_other_employee_cannot_read_private_docs(client, hr, employee):
    from tests.conftest import Actor
    other = Actor(client, "employee")
    png = b"\x89PNG\r\n\x1a\n" + b"1" * 50
    fid = hr.post(f"/employees/{employee.employee_id}/documents", files={"file": ("p.png", png, "image/png")}).json()["id"]
    assert other.get(f"/files/{fid}").status_code == 403
    assert other.get(f"/employees/{employee.employee_id}/documents").status_code == 403
    basic = other.get(f"/employees/{employee.employee_id}").json()
    assert "bank_account" not in basic and "address" not in basic

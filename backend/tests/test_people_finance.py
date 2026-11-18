from datetime import date, timedelta

from tests.conftest import Actor, login


def test_recruitment_offer_conversion_flow(client, admin, hr):
    dept = hr.post("/departments", json={"name": "Platform", "code": "PLT"}).json()["id"]
    hr.post("/designations", json={"title": "Backend Engineer", "department_id": dept})
    job = hr.post("/recruitment/jobs", json={"title": "Backend Engineer", "department_id": dept, "positions": 2})
    assert job.status_code == 201
    cand = hr.post("/recruitment/candidates", json={"job_id": job.json()["id"], "first_name": "Meera", "last_name": "Nair",
                                                    "email": "meera.nair@example.com", "experience_years": 4})
    assert cand.status_code == 201
    cid = cand.json()["id"]
    assert hr.post("/recruitment/candidates", json={"job_id": job.json()["id"], "first_name": "Meera",
                                                    "email": "meera.nair@example.com"}).status_code == 409
    pdf = b"%PDF-1.4 resume"
    assert hr.post(f"/recruitment/candidates/{cid}/resume", files={"file": ("cv.pdf", pdf, "application/pdf")}).status_code == 200
    iv = hr.post(f"/recruitment/candidates/{cid}/interviews", json={"round_name": "Technical",
                                                                    "scheduled_at": "2030-02-01T10:00:00", "interviewer_id": admin.employee_id})
    assert iv.status_code == 201
    assert hr.post(f"/recruitment/interviews/{iv.json()['id']}/feedback",
                   json={"rating": 4, "recommendation": "hire", "feedback": "Strong"}).status_code == 200
    # offer with mismatched breakup rejected
    bad = hr.post("/offers", json={"candidate_id": cid, "designation": "Backend Engineer", "department_id": dept,
                                   "joining_date": str(date.today() + timedelta(days=30)), "annual_ctc": 1200000,
                                   "salary_breakup": [{"label": "Basic", "monthly": 50000, "annual": 600000}]})
    assert bad.status_code == 422
    offer = hr.post("/offers", json={"candidate_id": cid, "designation": "Backend Engineer", "department_id": dept,
                                     "joining_date": str(date.today() + timedelta(days=30)), "annual_ctc": 1200000,
                                     "salary_breakup": [{"label": "Basic", "monthly": 50000, "annual": 600000},
                                                        {"label": "HRA", "monthly": 50000, "annual": 600000}]})
    assert offer.status_code == 201, offer.text
    oid = offer.json()["id"]
    assert hr.post(f"/offers/{oid}/send").status_code == 409  # not approved yet
    sub = hr.post(f"/offers/{oid}/submit")
    assert sub.status_code == 200 and sub.json()["current_version"] == 1
    assert hr.post(f"/offers/{oid}/decision", json={"approve": True}).status_code == 403  # HR lacks offers.approve
    assert admin.post(f"/offers/{oid}/decision", json={"approve": True}).status_code == 200
    sent = hr.post(f"/offers/{oid}/send")
    assert sent.status_code == 200
    token = sent.json()["response_link"].rsplit("/", 1)[1]
    pub = client.get(f"/api/v1/public/offers/{token}")
    assert pub.status_code == 200 and pub.json()["recipient_name"] == "Meera Nair"
    assert client.get(f"/api/v1/public/offers/{token}/pdf").content.startswith(b"%PDF")
    assert client.post(f"/api/v1/public/offers/{token}/respond", json={"accept": True, "signature": "Someone Else"}).status_code == 422
    acc = client.post(f"/api/v1/public/offers/{token}/respond", json={"accept": True, "signature": "meera nair"})
    assert acc.status_code == 200 and acc.json()["status"] == "accepted"
    assert client.post(f"/api/v1/public/offers/{token}/respond", json={"accept": False, "signature": "Meera Nair"}).status_code == 409
    detail = hr.get(f"/offers/{oid}").json()
    assert detail["current_version"] == 2 and len(detail["versions"]) == 2
    # convert to employee
    conv = admin.post(f"/recruitment/candidates/{cid}/convert", json={"create_login": True})
    assert conv.status_code == 201, conv.text
    emp = conv.json()
    assert emp["designation"]["title"] == "Backend Engineer" and emp["department"]["id"] == dept
    assert admin.post(f"/recruitment/candidates/{cid}/convert", json={}).status_code == 409
    docs = admin.get(f"/employees/{emp['id']}/documents").json()
    cats = {d["category"] for d in docs}
    assert "offer_letter" in cats and "resume" in cats
    # the new employee can open their offer letter documents
    h = login(client, "meera.nair@example.com", emp["temporary_password"])
    fid = next(d["id"] for d in docs if d["category"] == "offer_letter")
    assert client.get(f"/api/v1/files/{fid}", headers=h).status_code == 200


def test_payroll_end_to_end(client, hr, set_face_required):
    set_face_required(False)
    e = Actor(client, "employee", joining_date=date(2024, 1, 1))
    comps = {c["code"]: c for c in hr.get("/payroll/components").json()}
    ded = hr.post("/payroll/components", json={"name": "Test Deduction", "code": "TDED", "kind": "deduction",
                                               "calc_type": "fixed", "default_value": 500})
    assert ded.status_code == 201
    first = date.today().replace(day=1)
    prev_month = (first - timedelta(days=1)).replace(day=1)
    s = hr.post("/payroll/structures", json={"employee_id": e.employee_id, "effective_from": "2024-01-01",
                                             "monthly_basic": 30000, "items": [
                                                 {"component_id": comps["HRA"]["id"], "value": 40},
                                                 {"component_id": ded.json()["id"], "value": 500}]})
    assert s.status_code == 201, s.text
    # mark every working day of the previous month present via manual attendance except LOP
    hr.post("/payroll/adjustments", json={"employee_id": e.employee_id, "year": prev_month.year, "month": prev_month.month,
                                          "kind": "bonus", "label": "Spot award", "amount": 2000})
    run = hr.post("/payroll/runs", json={"year": prev_month.year, "month": prev_month.month})
    assert run.status_code == 201, run.text
    slip = next(p for p in run.json()["payslips"] if p["employee_id"] == e.employee_id)
    # no attendance recorded => every working day is LOP => only bonus remains, deduction prorated? (fixed deduction applies)
    assert slip["lop_days"] == slip["working_days"]
    assert slip["paid_days"] == 0 and slip["bonus"] == 2000
    # now give full attendance via HR manual marks and recompute
    from app.services.attendance import working_days_in_range
    from app.db.session import SessionLocal
    import calendar
    end = prev_month.replace(day=calendar.monthrange(prev_month.year, prev_month.month)[1])
    with SessionLocal() as db:
        days = working_days_in_range(db, prev_month, end)
    for d in days:
        r = hr.post("/attendance/manual", json={"employee_id": e.employee_id, "work_date": str(d), "check_in": "09:00",
                                                "check_out": "18:00", "reason": "Test data"})
        assert r.status_code == 200
    run = hr.post("/payroll/runs", json={"year": prev_month.year, "month": prev_month.month}).json()
    slip = next(p for p in run["payslips"] if p["employee_id"] == e.employee_id)
    assert slip["lop_days"] == 0
    assert slip["gross_earnings"] == 42000.0  # 30000 + 40% HRA
    assert slip["total_deductions"] == 500.0  # fixed deduction prorated at 100%
    assert slip["net_pay"] == 43500.0  # 42000 + 2000 bonus - 500
    # employee cannot see draft payslips; can after finalize
    assert e.get("/payroll/my-payslips").json() == []
    assert e.get(f"/payroll/payslips/{slip['id']}/pdf").status_code == 403
    fin = hr.post(f"/payroll/runs/{run['id']}/finalize")
    assert fin.status_code == 200
    assert hr.post("/payroll/runs", json={"year": prev_month.year, "month": prev_month.month}).status_code == 409
    mine = e.get("/payroll/my-payslips").json()
    assert len(mine) == 1 and mine[0]["net_pay"] == 43500.0
    pdf = e.get(f"/payroll/payslips/{slip['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    other = Actor(client, "employee")
    assert other.get(f"/payroll/payslips/{slip['id']}/pdf").status_code == 403
    paid = hr.post(f"/payroll/runs/{run['id']}/pay", json={"paid_on": str(date.today()), "mode": "bank_transfer",
                                                           "payslip_ids": [slip["id"]]})
    assert paid.status_code == 200


def test_expenses_flow(client, hr):
    e = Actor(client, "employee")
    cats = {c["name"]: c for c in e.get("/expenses/categories").json()}
    no_receipt = e.post("/expenses", data={"title": "Cab", "amount": "450", "expense_date": str(date.today()),
                                           "category_id": str(cats["Travel"]["id"])})
    assert no_receipt.status_code == 422
    png = b"\x89PNG\r\n\x1a\n" + b"2" * 80
    r = e.post("/expenses", data={"title": "Cab to client", "amount": "450", "expense_date": str(date.today()),
                                  "category_id": str(cats["Travel"]["id"])}, files={"receipt": ("r.png", png, "image/png")})
    assert r.status_code == 201, r.text
    xid = r.json()["id"]
    assert e.post(f"/expenses/{xid}/review", json={"approve": True}).status_code == 403
    assert hr.post(f"/expenses/{xid}/reimburse", json={}).status_code == 409
    assert hr.post(f"/expenses/{xid}/review", json={"approve": False}).status_code == 422  # reason needed
    assert hr.post(f"/expenses/{xid}/review", json={"approve": True}).status_code == 200
    assert hr.post(f"/expenses/{xid}/reimburse", json={"reference": "UTR123"}).json()["status"] == "reimbursed"
    assert e.get(f"/files/{r.json()['receipt_file_id']}").status_code == 200
    future = e.post("/expenses", data={"title": "x", "amount": "1", "expense_date": str(date.today() + timedelta(days=5)),
                                       "category_id": str(cats["Other"]["id"])}, files={"receipt": ("r.png", png, "image/png")})
    assert future.status_code == 422


def test_announcements_and_meetings(client, hr):
    e = Actor(client, "employee")
    r = hr.post("/announcements", json={"title": "Office closed Friday", "body": "Maintenance work.", "is_pinned": True})
    assert r.status_code == 201
    assert any(a["id"] == r.json()["id"] for a in e.get("/announcements").json()["items"])
    role_only = hr.post("/announcements", json={"title": "HR only note", "body": "Internal", "audience": "role",
                                                "role_code": "hr_admin"}).json()
    assert not any(a["id"] == role_only["id"] for a in e.get("/announcements").json()["items"])
    assert e.post("/announcements", json={"title": "Nope", "body": "Nope"}).status_code == 403
    m = hr.post("/meetings", json={"title": "All hands", "start_at": "2030-03-01T10:00:00", "end_at": "2030-03-01T11:00:00",
                                   "attendee_ids": [e.employee_id]})
    assert m.status_code == 201, m.text
    assert e.post(f"/meetings/{m.json()['id']}/rsvp", json={"response": "accepted"}).json()["my_response"] == "accepted"
    assert hr.post("/meetings", json={"title": "Bad", "start_at": "2030-03-01T10:00:00",
                                      "end_at": "2030-03-01T09:00:00"}).status_code == 422
    ev = e.get("/calendar/events?date_from=2030-03-01&date_to=2030-03-02").json()
    assert any(x["type"] == "meeting" for x in ev)

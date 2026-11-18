import threading
from datetime import date, timedelta

import numpy as np
import pytest

from app.services import face


# ------------------------------------------------------------------ liveness logic (unit)

def _fa(yaw, seed):
    rng = np.random.default_rng(seed)
    emb = np.ones(128, dtype=np.float32) + rng.normal(0, 0.05, 128).astype(np.float32)
    emb /= np.linalg.norm(emb)
    gray = (rng.random((48, 64)) * 255).astype(np.uint8)
    return face.FrameAnalysis(emb, yaw, 0.95, (0, 0, 120, 120), gray)


def test_pose_sequence_detection():
    assert face.follows_sequence([0, 0.02, 0.25, 0.3, 0.01, -0.3], ["center", "left", "right"])
    assert not face.follows_sequence([0, -0.3, 0.3], ["center", "left", "right"])


def test_liveness_accepts_correct_sequence():
    frames = [_fa(y, i) for i, y in enumerate([0.0, 0.02, 0.15, 0.3, 0.32, 0.05, -0.25, -0.3])]
    ts = [i * 400 for i in range(8)]
    res = face.check_liveness(frames, ["center", "left", "right"], ts)
    assert res["frames"] == 8


def test_liveness_rejects_static_photo():
    same = _fa(0.0, 1)
    frames = [face.FrameAnalysis(same.embedding, y, 0.95, same.box, same.gray_small) for y in [0, 0, 0, 0, 0, 0, 0, 0]]
    with pytest.raises(face.FaceError):
        face.check_liveness(frames, ["center", "left", "center"], [i * 400 for i in range(8)])


def test_liveness_rejects_wrong_order_and_bad_timing():
    frames = [_fa(y, i) for i, y in enumerate([0.0, -0.3, -0.3, 0.0, 0.3, 0.3, 0.0, 0.0])]
    with pytest.raises(face.FaceError):
        face.check_liveness(frames, ["center", "left", "right"], [i * 400 for i in range(8)])
    frames = [_fa(y, i) for i, y in enumerate([0.0, 0.3, 0.3, 0.0, -0.3, -0.3, 0.0, 0.0])]
    with pytest.raises(face.FaceError):
        face.check_liveness(frames, ["center", "left", "right"], [i * 10 for i in range(8)])  # too fast


def test_face_engine_rejects_frame_without_face():
    import base64
    import cv2
    img = np.full((240, 320, 3), 128, np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    data = "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()
    with pytest.raises(face.FaceError):
        face.FaceEngine.get().analyze(face.decode_frame(data))


# ------------------------------------------------------------------ attendance API

def test_face_required_blocks_web_checkin(employee, set_face_required):
    set_face_required(True)
    assert employee.post("/attendance/check-in").status_code == 403


def test_challenge_nonce_is_single_use(employee, set_face_required):
    set_face_required(True)
    ch = employee.post("/attendance/challenge", json={"purpose": "check_in"}).json()
    assert ch["steps"][0] == "center" and len(ch["instructions"]) == 3
    body = {"nonce": ch["nonce"], "frames": ["data:image/jpeg;base64,AAAA"] * 6, "timestamps": [i * 300 for i in range(6)]}
    first = employee.post("/attendance/check-in/face", json=body)
    assert first.status_code in (400, 422)  # not enrolled / invalid frame
    again = employee.post("/attendance/check-in/face", json=body)
    assert again.status_code == 400 and "already used" in again.json()["detail"]


def test_checkin_break_checkout_and_duplicates(employee, set_face_required):
    set_face_required(False)
    r = employee.post("/attendance/check-in")
    assert r.status_code == 200, r.text
    assert r.json()["record"]["check_in_method"] == "web"
    assert employee.post("/attendance/check-in").status_code == 409  # duplicate prevention
    assert employee.post("/attendance/break", json={"action": "start"}).status_code == 200
    assert employee.post("/attendance/break", json={"action": "start"}).status_code == 409
    assert employee.post("/attendance/break", json={"action": "end"}).status_code == 200
    out = employee.post("/attendance/check-out")
    assert out.status_code == 200
    assert out.json()["record"]["check_out_at"]
    assert employee.post("/attendance/check-out").status_code == 409
    today = employee.get("/attendance/today").json()
    assert today["record"]["status"] in ("present", "late", "half_day")


def test_concurrent_checkins_only_one_succeeds(client, set_face_required):
    from tests.conftest import Actor
    set_face_required(False)
    a = Actor(client, "employee")
    results = []

    def go():
        results.append(a.post("/attendance/check-in").status_code)

    threads = [threading.Thread(target=go) for _ in range(5)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert results.count(200) == 1, results
    assert all(s in (200, 409) for s in results)


def test_correction_request_and_approval(employee, hr):
    d = (date.today() - timedelta(days=2)).isoformat()
    r = employee.post("/attendance/corrections", json={"work_date": d, "check_in": "09:30", "check_out": "18:30",
                                                      "reason": "Forgot to check in"})
    assert r.status_code == 201, r.text
    assert employee.post("/attendance/corrections", json={"work_date": d, "check_in": "09:30",
                                                          "reason": "Duplicate request"}).status_code == 409
    cid = r.json()["id"]
    assert employee.post(f"/attendance/corrections/{cid}/review", json={"approve": True}).status_code == 403
    ok = hr.post(f"/attendance/corrections/{cid}/review", json={"approve": True, "note": "ok"})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    month = employee.get(f"/attendance/my?year={d[:4]}&month={int(d[5:7])}").json()
    rec = [x for x in month["records"] if x["work_date"] == d][0]
    assert rec["worked_minutes"] == 540 and rec["check_in_method"] == "correction"


def test_future_correction_rejected(employee):
    d = (date.today() + timedelta(days=3)).isoformat()
    assert employee.post("/attendance/corrections", json={"work_date": d, "check_in": "09:00",
                                                          "reason": "Future"}).status_code == 422


def test_manual_mark_by_hr_and_live_board(hr, employee):
    d = (date.today() - timedelta(days=1)).isoformat()
    r = hr.post("/attendance/manual", json={"employee_id": employee.employee_id, "work_date": d, "check_in": "10:00",
                                            "check_out": "19:00", "reason": "Camera failure"})
    assert r.status_code == 200 and r.json()["check_in_method"] == "manual"
    board = hr.get("/attendance/live").json()
    assert any(row["employee"]["id"] == employee.employee_id for row in board["rows"])


# ------------------------------------------------------------------ leave

def _next_weekday(offset):
    return (date.today() + timedelta(days=offset)).isoformat()


def test_leave_apply_approve_balance(employee, hr, set_face_required):
    set_face_required(False)  # also sets every weekday as working
    types = employee.get("/leave/types").json()
    cl = next(t for t in types if t["code"] == "CL")
    start, end = _next_weekday(10), _next_weekday(11)
    if start[:4] != end[:4]:
        start, end = _next_weekday(20), _next_weekday(21)
    r = employee.post("/leave/requests", json={"leave_type_id": cl["id"], "start_date": start, "end_date": end,
                                               "reason": "Family function"})
    assert r.status_code == 201, r.text
    assert r.json()["days"] == 2
    # overlap
    assert employee.post("/leave/requests", json={"leave_type_id": cl["id"], "start_date": start, "end_date": start,
                                                  "reason": "Again"}).status_code == 409
    # appears in HR approvals
    approvals = hr.get("/leave/requests?scope=approvals&status=pending").json()["items"]
    assert any(a["id"] == r.json()["id"] for a in approvals)
    # employee cannot approve own
    assert employee.post(f"/leave/requests/{r.json()['id']}/review", json={"approve": True}).status_code == 403
    before = {b["leave_type"]["code"]: b for b in employee.get(f"/leave/balances/me?year={start[:4]}").json()}["CL"]
    assert hr.post(f"/leave/requests/{r.json()['id']}/review", json={"approve": True}).status_code == 200
    after = {b["leave_type"]["code"]: b for b in employee.get(f"/leave/balances/me?year={start[:4]}").json()}["CL"]
    assert after["used"] == before["used"] + 2
    # cancel restores
    assert employee.post(f"/leave/requests/{r.json()['id']}/cancel").status_code == 200
    restored = {b["leave_type"]["code"]: b for b in employee.get(f"/leave/balances/me?year={start[:4]}").json()}["CL"]
    assert restored["used"] == before["used"]


def test_leave_insufficient_balance_and_validation(employee):
    types = employee.get("/leave/types").json()
    sl = next(t for t in types if t["code"] == "SL")
    y = date.today().year
    r = employee.post("/leave/requests", json={"leave_type_id": sl["id"], "start_date": f"{y}-12-01",
                                               "end_date": f"{y}-12-28", "reason": "Too long"})
    assert r.status_code == 422
    r = employee.post("/leave/requests", json={"leave_type_id": sl["id"], "start_date": f"{y}-12-05",
                                               "end_date": f"{y}-12-01", "reason": "Backwards"})
    assert r.status_code == 422


def test_holiday_crud(hr, employee):
    y = date.today().year + 1
    r = hr.post("/holidays", json={"date": f"{y}-01-26", "name": "Republic Day"})
    assert r.status_code == 201
    assert hr.post("/holidays", json={"date": f"{y}-01-26", "name": "Dup"}).status_code == 409
    assert employee.post("/holidays", json={"date": f"{y}-08-15", "name": "X"}).status_code == 403
    assert any(h["name"] == "Republic Day" for h in employee.get(f"/holidays?year={y}").json())


def test_employee_can_self_enroll_but_not_others(client, employee):
    from tests.conftest import Actor
    other = Actor(client, "employee")
    mine = employee.post("/attendance/challenge", json={"purpose": "enroll"})
    assert mine.status_code == 200 and mine.json()["steps"][0] == "center"
    assert employee.post("/attendance/challenge", json={"purpose": "enroll", "employee_id": other.employee_id}).status_code == 403
    body = {"nonce": "x" * 20, "frames": ["data:image/jpeg;base64,AAAA"] * 6, "timestamps": [i * 300 for i in range(6)],
            "employee_id": other.employee_id, "consent_confirmed": True}
    assert employee.post("/attendance/face/enroll", json=body).status_code == 403
    # own enrollment passes the permission check and fails only on the (invalid) liveness capture
    body["employee_id"] = employee.employee_id
    body["nonce"] = mine.json()["nonce"]
    r = employee.post("/attendance/face/enroll", json=body)
    assert r.status_code == 422


def test_manual_request_notifies_hr_with_approval_link(employee, hr):
    d = (date.today() - timedelta(days=1)).isoformat()
    assert employee.post("/attendance/corrections", json={"kind": "manual", "work_date": d, "check_in": "09:40",
                                                          "reason": "Camera not working"}).status_code == 201
    notes = hr.get("/notifications").json()["items"]
    n = next(x for x in notes if x["title"] == "Attendance manual request")
    assert n["link"] == "/attendance?tab=requests"
    assert hr.get("/attendance/corrections?status=pending").json()["total"] >= 1

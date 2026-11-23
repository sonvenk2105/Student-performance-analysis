from app import db
from app.models import Assessment, AssessmentMark, AuditEvent, User
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import re

def login(client, name="Test Student", student_id="T-1"):
    password_by_student = getattr(client, "_student_test_passwords", {})
    client._student_test_passwords = password_by_student
    normalized_id = student_id.strip().upper()
    response = client.post("/login", data={"name":name,"student_id":student_id}, follow_redirects=True)
    if b"Save your student password" in response.data:
        match = re.search(rb'id="generated-password" type="text" value="([^"]+)"', response.data)
        password = match.group(1).decode()
        password_by_student[normalized_id] = password
        return client.post("/login/password", data={"saved_password":"yes","generated_password":password}, follow_redirects=True)
    if b"Enter your student password" in response.data:
        password = password_by_student[normalized_id]
        return client.post("/login/password", data={"password":password}, follow_redirects=True)
    return response

def admin_login(client, email, password):
    return client.post("/admin/login", data={"email":email,"password":password}, follow_redirects=True)

def test_create_account_does_not_send_signed_in_user_back_inside(client, app, student):
    login(client)

    registration_page = client.get("/register")
    assert registration_page.status_code == 200
    assert b"Create your account" in registration_page.data
    assert b"you\xe2\x80\x99ll be signed out" in registration_page.data

    response = client.post("/register", data={
        "name":"New Student",
        "student_id":"NEW-1",
        "college_name":"Example College",
        "course":"BCA",
        "semester":"1",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Account created. Please sign in." in response.data
    assert b"Welcome back" in response.data
    assert client.get("/student/dashboard").status_code == 302

    with app.app_context():
        created = db.session.scalar(db.select(User).where(User.student_id == "NEW-1"))
        assert created is not None
        assert created.role == "student"
        assert created.email is None
        assert created.college_name == "Example College"
    login(client, "New Student", "NEW-1")
    assert client.get("/student/dashboard").status_code == 200

def test_student_sign_in_uses_name_and_id_and_accepts_case_variants(client, app, student):
    page = client.get("/login")
    assert page.status_code == 200
    assert b'Student name' in page.data and b'Student ID / USN' in page.data
    assert b'name="email"' not in page.data and b'name="password"' not in page.data
    assert b'Administrator?' not in page.data
    registration_page = client.get("/register")
    assert b'name="email"' not in registration_page.data
    assert b'name="password"' not in registration_page.data

    response = login(client, "  test student ", " t-1 ")
    assert response.status_code == 200
    assert client.get("/student/dashboard").status_code == 200

def test_first_signin_shows_password_and_later_signin_requires_it(client, app, student):
    setup = client.post("/login", data={"name":"Test Student","student_id":"T-1"}, follow_redirects=True)
    assert b"Save your student password" in setup.data
    match = re.search(rb'id="generated-password" type="text" value="([^"]+)"', setup.data)
    assert match
    generated_password = match.group(1).decode()
    assert generated_password.startswith("TES2026001-")
    assert re.fullmatch(r"TES2026001-(?:[A-HJ-NP-Z2-9]{4}-){3}[A-HJ-NP-Z2-9]{4}", generated_password)

    saved = client.post("/login/password", data={"saved_password":"yes","generated_password":generated_password}, follow_redirects=True)
    assert saved.status_code == 200
    assert client.get("/student/dashboard").status_code == 200
    client.post("/logout")

    wrong_id = client.post("/login", data={"name":"Test Student","student_id":"T-9"}, follow_redirects=True)
    assert b"Student name or ID was not recognized" in wrong_id.data
    assert client.get("/student/dashboard").status_code == 302

    prompt = client.post("/login", data={"name":"Test Student","student_id":"T-1"}, follow_redirects=True)
    assert b"Enter your student password" in prompt.data
    rejected = client.post("/login/password", data={"password":"wrong-password"}, follow_redirects=True)
    assert b"That password was not recognized" in rejected.data
    assert client.get("/student/dashboard").status_code == 302
    accepted = client.post("/login/password", data={"password":generated_password}, follow_redirects=True)
    assert accepted.status_code == 200
    assert client.get("/student/dashboard").status_code == 200

def test_student_can_replace_forgotten_password_after_account_details_match(client, student):
    login(client)
    old_password = client._student_test_passwords["T-1"]
    client.post("/logout")

    prompt = client.post("/login", data={"name":"Test Student","student_id":"T-1"}, follow_redirects=True)
    assert b"Enter your student password" in prompt.data
    recovery = client.get("/login/forgot-password")
    assert recovery.status_code == 200 and b'Student name' in recovery.data and b'Student ID / USN' in recovery.data

    mismatch = client.post("/login/forgot-password", data={
        "name":"Test Student","student_id":"T-9",
    })
    assert mismatch.status_code == 200
    assert b"could not be verified" in mismatch.data

    reset = client.post("/login/forgot-password", data={
        "name":"Test Student","student_id":"T-1",
    })
    assert reset.status_code == 200 and b"Your new password is ready" in reset.data
    assert b'href="/login/password"' in reset.data
    assert b"Enter your student password" in client.get("/login/password").data
    match = re.search(rb'data-password="([^"]+)"', reset.data)
    assert match
    new_password = match.group(1).decode()
    assert new_password != old_password
    assert re.fullmatch(r"TES2026001-(?:[A-HJ-NP-Z2-9]{4}-){3}[A-HJ-NP-Z2-9]{4}", new_password)

    rejected = client.post("/login/password", data={"password":old_password}, follow_redirects=True)
    assert b"That password was not recognized" in rejected.data
    accepted = client.post("/login/password", data={"password":new_password}, follow_redirects=True)
    assert accepted.status_code == 200
    assert client.get("/student/dashboard").status_code == 200

def test_login_and_student_assessment_flow(client, app, student):
    response = login(client)
    assert response.status_code == 200
    response = client.post("/student/analyze", data={"confirm_review":"yes","request_key":"123e4567-e89b-42d3-a456-426614174000","subject[]":["Math","Science"],"obtained[]":["80","70"],"maximum[]":["100","100"],"passing[]":["40","40"],"semester":"1","label":"Midterm"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"75.00%" in response.data
    with app.app_context():
        item = db.session.scalar(db.select(Assessment))
        assert item and len(item.marks) == 2
        report_id = item.id
    pdf = client.get(f"/student/assessment/{report_id}/report.pdf")
    assert pdf.status_code == 200
    assert pdf.mimetype == "application/pdf"
    duplicate = client.post("/student/analyze", data={"confirm_review":"yes","request_key":"123e4567-e89b-42d3-a456-426614174000","subject[]":["Math","Science"],"obtained[]":["80","70"],"maximum[]":["100","100"],"passing[]":["40","40"],"semester":"1","label":"Midterm"}, follow_redirects=True)
    assert duplicate.status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Assessment.id))) == 1
    client.post("/logout")

def test_rejected_marks_remain_unchanged_in_analysis_form(client, app, student):
    login(client)
    response = client.post("/student/analyze", data={"confirm_review":"yes","request_key":"123e4567-e89b-42d3-a456-426614174013","subject[]":["Math"],"obtained[]":["99"],"maximum[]":["50"],"passing[]":["70"],"semester":"1","label":"Midterm"})
    assert response.status_code == 200
    assert b'value="99"' in response.data and b'value="50"' in response.data and b'value="70"' in response.data
    assert b"outside the valid range" in response.data

def test_student_can_modify_and_delete_owned_assessment(client, app, student):
    login(client)
    created = client.post("/student/analyze", data={"confirm_review":"yes","request_key":"123e4567-e89b-42d3-a456-426614174011","subject[]":["Math"],"obtained[]":["80"],"maximum[]":["100"],"passing[]":["40"],"semester":"1","label":"Midterm"})
    assert created.status_code == 302
    with app.app_context():
        record = db.session.scalar(db.select(Assessment))
        assessment_id = record.id
    history = client.get("/student/history")
    assert b"Modify" in history.data and b"Delete assessment" in history.data
    edit_page = client.get(f"/student/assessment/{assessment_id}/edit")
    assert edit_page.status_code == 200 and b'value="80.0"' in edit_page.data
    updated = client.post(f"/student/assessment/{assessment_id}/edit", data={"confirm_review":"yes","subject[]":["Math"],"obtained[]":["65"],"maximum[]":["100"],"passing[]":["40"],"semester":"2","label":"Corrected midterm"}, follow_redirects=True)
    assert updated.status_code == 200 and b"65.00%" in updated.data
    with app.app_context():
        record = db.session.get(Assessment, assessment_id)
        assert record.label == "Corrected midterm" and record.semester == 2
        assert record.total_obtained == 65 and len(record.marks) == 1
    deleted = client.post(f"/student/assessment/{assessment_id}/delete", follow_redirects=True)
    assert deleted.status_code == 200 and b"Assessment and its subject marks were deleted" in deleted.data
    with app.app_context():
        assert db.session.get(Assessment, assessment_id) is None

def test_account_popup_password_change_and_account_deletion(client, app, student):
    login(client)
    initial_password = client._student_test_passwords["T-1"]
    client.post("/student/analyze", data={"confirm_review":"yes","request_key":"123e4567-e89b-42d3-a456-426614174012","subject[]":["Math"],"obtained[]":["80"],"maximum[]":["100"],"passing[]":["40"],"semester":"1","label":"Midterm"})
    with app.app_context():
        db.session.add(AuditEvent(actor_id=None, action="student_account_edited", detail=f"user_id={student}"))
        db.session.commit()
    dashboard = client.get("/student/dashboard")
    assert b'id="account-dialog"' in dashboard.data
    assert b'id="account-menu-toggle"' in dashboard.data
    assert b"Student name" in dashboard.data and b"Student ID / USN" in dashboard.data
    assert initial_password.encode() not in dashboard.data
    new_password = "a-new-secure-password-234"
    changed = client.post("/student/account/password", data={"current_password":initial_password,"new_password":new_password,"confirm_password":new_password}, follow_redirects=True)
    assert changed.status_code == 200 and b"Secure password updated" in changed.data
    deleted = client.post("/student/account/delete", data={"current_password":new_password,"confirm_delete":"yes"}, follow_redirects=True)
    assert deleted.status_code == 200 and b"Your account and saved assessment data were deleted" in deleted.data
    with app.app_context():
        assert db.session.get(User, student) is None
        assert db.session.scalar(db.select(db.func.count(Assessment.id))) == 0
        assert db.session.scalar(db.select(db.func.count(AuditEvent.id))) == 0
    assert client.get("/student/dashboard").status_code == 302

def test_comparison_shows_real_delta_for_same_structure(client, app, student):
    login(client)
    for key, score, label in [("123e4567-e89b-42d3-a456-426614174001", "60", "Attempt one"), ("123e4567-e89b-42d3-a456-426614174002", "70", "Attempt two")]:
        client.post("/student/analyze", data={"confirm_review":"yes","request_key":key,"subject[]":["Math"],"obtained[]":[score],"maximum[]":["100"],"passing[]":["40"],"semester":"1","label":label})
    page = client.get("/student/compare")
    assert page.status_code == 200
    assert b"+10.00 pp" in page.data

def test_concurrent_student_assessments_remain_isolated(tmp_path):
    from app import create_app
    database_file = (tmp_path / "concurrent.db").as_posix()
    concurrent_app = create_app({"TESTING":True,"WTF_CSRF_ENABLED":False,"SECRET_KEY":"concurrency-test-secret","SQLALCHEMY_DATABASE_URI":f"sqlite:///{database_file}","SQLALCHEMY_ENGINE_OPTIONS":{"pool_size":5,"max_overflow":5}})
    with concurrent_app.app_context():
        db.create_all()
        for index in (1,2):
            user = User(name=f"Student {index}",student_id=f"C-{index}",email=f"c{index}@example.test",course="BCA",semester=index)
            user.set_password("concurrent-test-password")
            db.session.add(user)
        db.session.commit()

    def submit(index):
        client = concurrent_app.test_client()
        login(client, f"Student {index}", f"C-{index}")
        response = client.post("/student/analyze", data={"confirm_review":"yes","request_key":f"123e4567-e89b-42d3-a456-42661417400{index}","subject[]":[f"Subject {index}"],"obtained[]":[str(index*20)],"maximum[]":["50"],"passing[]":["10"],"semester":str(index),"label":f"Attempt {index}"})
        body = response.get_data(as_text=True)
        marker = body.find('class="messages"')
        return response.status_code, body[marker:marker+500]

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(submit, (1,2)))
    assert [status for status,_ in statuses] == [302,302], [body[-1000:] for _,body in statuses]
    with concurrent_app.app_context():
        items = db.session.scalars(db.select(Assessment).order_by(Assessment.student_id)).all()
        assert len(items) == 2
        assert [item.student.email for item in items] == ["c1@example.test","c2@example.test"]

def test_ownership_blocks_other_student(client, app, student):
    with app.app_context():
        other = User(name="Other",student_id="T-2",email="other@example.test",course="BCom",semester=1)
        other.set_password("a-long-test-password"); db.session.add(other); db.session.flush()
        record = Assessment(student_id=other.id,course="BCom",semester=1,label="Private",idempotency_key="x",percentage=88,grade="A",passed=True,total_obtained=88,total_maximum=100,rule_version=1,rule_snapshot={})
        db.session.add(record); db.session.commit(); record_id=record.id
    login(client)
    assert client.get(f"/student/assessment/{record_id}").status_code == 404
    assert client.get(f"/student/assessment/{record_id}/report.pdf").status_code == 404
    assert client.get(f"/student/assessment/{record_id}/edit").status_code == 404
    assert client.post(f"/student/assessment/{record_id}/delete").status_code == 404

def test_admin_route_requires_role(client, app, student):
    login(client)
    assert client.get("/admin/").status_code == 403
    client.post("/logout")
    admin_redirect = client.get("/admin/")
    assert admin_redirect.status_code == 302
    assert "/admin/login" in admin_redirect.headers["Location"]
    with app.app_context():
        admin = User(name="Admin",email="admin@example.test",role="admin")
        admin.set_password("another-long-test-password")
        db.session.add(admin); db.session.commit()
    assert admin_login(client,"admin@example.test","another-long-test-password").status_code == 200
    assert client.get("/admin/").status_code == 200
    assert client.get(f"/admin/students/{student}").status_code == 200
    created = client.post("/admin/students/new", data={"name":"Created Student","student_id":"C-NEW","college_name":"Example College","email":"created@example.test","course":"BCA","semester":"2"}, follow_redirects=True)
    assert created.status_code == 200 and b"Created Student" in created.data
    with app.app_context():
        managed = db.session.scalar(db.select(User).where(User.email == "created@example.test"))
        managed_id = managed.id
        assert managed.role == "student" and not managed.student_password_initialized
    edited = client.post(f"/admin/students/{managed_id}/edit", data={"name":"Edited Student","student_id":"C-NEW","college_name":"Example College","email":"created@example.test","course":"BCA","semester":"3"}, follow_redirects=True)
    assert edited.status_code == 200 and b"Edited Student" in edited.data
    reset = client.post(f"/admin/students/{managed_id}/reset-password", data={"new_password":"a-replacement-password-123"}, follow_redirects=True)
    assert reset.status_code == 200 and b"Password reset" in reset.data
    with app.app_context():
        assert db.session.get(User, managed_id).check_password("a-replacement-password-123")
        assert db.session.get(User, managed_id).student_password_initialized
    export = client.get("/admin/reports/aggregate.csv")
    assert export.status_code == 200
    assert b"assessment_count" in export.data
    assert b"student@example.test" not in export.data
    response = client.post("/admin/subjects", data={"course":"BCA","semester":"1","name":"Mathematics","maximum":"100","passing":"40"}, follow_redirects=True)
    assert response.status_code == 200 and b"Mathematics" in response.data
    client.post("/logout")
    login(client)
    form = client.get("/student/analyze")
    assert b'Mathematics' in form.data and b'data-maximum="100.0"' in form.data

def test_login_attempts_are_rate_limited_without_storing_email(client, app):
    for _ in range(10):
        response = client.post("/login", data={"name":"Unknown Student","student_id":"UNKNOWN-1"})
        assert response.status_code == 200
    limited = client.post("/login", data={"name":"Unknown Student","student_id":"UNKNOWN-1"})
    assert limited.status_code == 429
    with app.app_context():
        from app.models import LoginAttempt
        attempts = db.session.scalars(db.select(LoginAttempt)).all()
        assert len(attempts) == 10
        assert all("UNKNOWN-1" not in attempt.identity_hash and "Unknown Student" not in attempt.identity_hash for attempt in attempts)

def test_health_and_marksheet_upload_prefills_analysis(client, app, student):
    assert client.get("/health").json == {"status":"ok","database":"ok"}
    login(client)
    from openpyxl import Workbook
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Subject", "Marks Obtained", "Maximum Marks", "Pass Marks"])
    sheet.append(["Mathematics", 82, 100, 40])
    sheet.append(["Science", 18, 20, 8])
    marksheet = BytesIO()
    workbook.save(marksheet)
    marksheet.seek(0)
    response = client.post("/student/upload", data={"marksheet":(marksheet,"marksheet.xlsx")}, content_type="multipart/form-data", follow_redirects=True)
    assert response.status_code == 200
    assert b"Read 2 subject(s)" in response.data
    assert b'value="Mathematics"' in response.data and b'value="Science"' in response.data
    assert b'value="82.0"' in response.data and b'value="40.0"' in response.data
    assert b'value="18.0"' in response.data and b'value="8.0"' in response.data
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Assessment.id))) == 0
    upload_names = __import__("os").listdir(app.config["UPLOAD_FOLDER"])
    assert upload_names == []

def test_profile_update_is_validated_and_owned(client, app, student):
    login(client)
    dashboard = client.get("/student/dashboard")
    assert re.search(rb'class="workspace-profile" href="([^"]+)"', dashboard.data).group(1) == b"/student/profile"
    profile_page = client.get("/student/profile")
    assert re.search(rb'class="workspace-profile" href="([^"]+)"', profile_page.data).group(1) == b"/student/dashboard"
    response = client.post("/student/profile", data={"name":"Updated Student","email":"updated@example.test"}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Profile updated" in response.data
    with app.app_context():
        user = db.session.get(User, student)
        assert user.name == "Updated Student" and user.email == "updated@example.test"

def test_prediction_page_shows_fallback_without_validated_model(client, app, student):
    login(client)
    response = client.get("/student/prediction")
    assert response.status_code == 200
    assert b"No validated estimate is available" in response.data

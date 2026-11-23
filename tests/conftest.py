import pytest
from app import create_app, db
from app.models import User

@pytest.fixture
def app(tmp_path):
    app = create_app({"TESTING":True,"WTF_CSRF_ENABLED":False,"SECRET_KEY":"test-secret","SQLALCHEMY_DATABASE_URI":"sqlite:///:memory:","SQLALCHEMY_ENGINE_OPTIONS":{},"UPLOAD_FOLDER":str(tmp_path / "uploads")})
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove(); db.drop_all()

@pytest.fixture
def client(app): return app.test_client()

@pytest.fixture
def student(app):
    with app.app_context():
        user = User(name="Test Student", student_id="T-1", email="student@example.test", college_name="Example College", course="BCA", semester=1)
        user.set_password("a-long-test-password")
        db.session.add(user); db.session.commit()
        return user.id

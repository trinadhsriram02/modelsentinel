import pytest
import os
import tempfile
from src.data.memory_store import (
    init_db, save_scan, get_all_scans,
    create_user, get_user_by_username,
    verify_password, hash_password
)

@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    db = str(tmp_path / "test.db")
    monkeypatch.setattr("src.data.memory_store.DB_PATH", db)
    yield db

def test_init_db_creates_tables(temp_db):
    init_db()
    assert os.path.exists(temp_db)

def test_create_user(temp_db):
    result = create_user("testuser", "test@test.com",
                         "Test@1234!", "analyst", "Test", "User")
    assert "id" in result
    assert result["username"] == "testuser"

def test_duplicate_user_rejected(temp_db):
    create_user("dupuser", "dup@test.com",
                "Test@1234!", "analyst", "Dup", "User")
    result = create_user("dupuser", "dup@test.com",
                         "Test@1234!", "analyst", "Dup", "User")
    assert "error" in result

def test_get_user_by_username(temp_db):
    create_user("findme", "find@test.com",
                "Test@1234!", "readonly", "Find", "Me")
    user = get_user_by_username("findme")
    assert user is not None
    assert user["username"] == "findme"
    assert user["role"] == "readonly"

def test_password_hashing():
    hashed = hash_password("MyPassword@123")
    assert hashed != "MyPassword@123"
    assert ":" in hashed

def test_password_verification():
    hashed = hash_password("Secure@Pass1!")
    assert verify_password("Secure@Pass1!", hashed) == True
    assert verify_password("WrongPassword", hashed) == False
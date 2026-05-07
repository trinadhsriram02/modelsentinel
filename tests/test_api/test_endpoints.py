import pytest
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_root_returns_running():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "running"

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_signup_weak_password():
    response = client.post("/signup", json={
        "username": "testuser",
        "first_name": "Test",
        "last_name": "User",
        "email": "test@test.com",
        "password": "weak",
        "role": "analyst"
    })
    assert response.status_code == 422

def test_signup_password_contains_name():
    response = client.post("/signup", json={
        "username": "trinadh",
        "first_name": "Trinadh",
        "last_name": "Sriram",
        "email": "t@test.com",
        "password": "Trinadh@123",
        "role": "analyst"
    })
    assert response.status_code == 422

def test_login_unknown_user():
    response = client.post("/login", json={
        "username": "nobody",
        "password": "Test@1234!"
    })
    assert response.status_code == 401

def test_protected_route_without_token():
    response = client.get("/scans")
    assert response.status_code == 401

def test_scan_without_auth():
    response = client.post("/scan/test")
    assert response.status_code == 401
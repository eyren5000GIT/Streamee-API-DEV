import os
import sys
import uuid
import requests

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")


def main():
    username = f"test_{uuid.uuid4().hex[:8]}"
    email = f"{username}@example.com"
    password = "StrongPassword123!"

    # --------------------------------------------------
    # Register
    # --------------------------------------------------
    r = requests.post(
        f"{BASE_URL}/auth/register/",
        json={
            "username": username,
            "email": email,
            "password": password,
        },
        timeout=10,
    )
    assert r.status_code == 201, f"Register failed: {r.status_code} {r.text}"

    # --------------------------------------------------
    # Login (email + password)
    # --------------------------------------------------
    r = requests.post(
        f"{BASE_URL}/auth/login/",
        json={
            "email": email,
            "password": password,
        },
        timeout=10,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"

    tokens = r.json()
    access = tokens["access"]
    refresh = tokens["refresh"]

    # --------------------------------------------------
    # Me
    # --------------------------------------------------
    r = requests.get(
        f"{BASE_URL}/auth/me/",
        headers={"Authorization": f"Bearer {access}"},
        timeout=10,
    )
    assert r.status_code == 200, f"Me failed: {r.status_code} {r.text}"

    # --------------------------------------------------
    # Logout
    # --------------------------------------------------
    r = requests.post(
        f"{BASE_URL}/auth/logout/",
        headers={"Authorization": f"Bearer {access}"},
        json={"refresh": refresh},
        timeout=10,
    )
    assert r.status_code == 204, f"Logout failed: {r.status_code} {r.text}"

    print("AUTH SMOKE TEST OK")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(str(e))
        sys.exit(1)

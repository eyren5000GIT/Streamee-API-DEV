
#!/usr/bin/env python3
"""
Smoke test for Communities endpoints.

Behavior:
- Runs all steps best-effort (does not stop on first failure).
- Collects failures and prints a summary at the end.
- Attempts CREATE community (may be skipped if Twitch not configured).
- Subsequent tests use an EXISTING community first:
    1) Prefer the manually created community (default slug: "testcommunity")
    2) Otherwise pick the first community from GET /communities/
    3) Otherwise fallback to the created community (if available)
- PATCH is attempted only on a community where the current user is admin; otherwise PATCH is skipped.
- Generates a UNIQUE username + email per run to ensure fresh test data.
"""

import os
import sys
import json
import random
import string
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Callable, List

import requests


def _rand_suffix(n: int = 8) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))


def _pretty(obj: Any) -> str:
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False)
    except Exception:
        return str(obj)


def make_unique_identity(base_username: str, base_email: str) -> tuple[str, str]:
    suffix = _rand_suffix(10)
    username = f"{base_username}_{suffix}"

    if "@" not in base_email:
        return username, f"{base_email}_{suffix}"

    local, domain = base_email.split("@", 1)
    email = f"{local}+{suffix}@{domain}"
    return username, email


@dataclass
class Config:
    base_url: str
    username: str
    email: str
    password: str
    timeout_s: int = 20
    smoke_twitch: str = "https://twitch.tv/handofblood"

    # Preferred existing community slug (your manually created one)
    testcommunity_slug: str = "testcommunity"


class SmokeFail(RuntimeError):
    pass


@dataclass
class StepResult:
    name: str
    status: str  # OK | FAIL | SKIP
    detail: str = ""


def request_json(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    timeout_s: int = 20,
) -> Tuple[int, Any]:
    hdrs = {**(headers or {}), "Accept": "application/json"}
    resp = requests.request(method, url, headers=hdrs, json=json_body, timeout=timeout_s)
    try:
        data = resp.json()
    except Exception:
        data = resp.text
    return resp.status_code, data


def auth_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def is_twitch_not_configured(sc: int, data: Any) -> bool:
    if isinstance(data, dict):
        msg = _pretty(data).lower()
        if "twitch" in msg and (
            "not configured" in msg
            or "missing twitch_client_id" in msg
            or "missing twitch_client_secret" in msg
        ):
            return True
        if "missing twitch_client_id" in msg or "missing twitch_client_secret" in msg:
            return True

    if isinstance(data, str):
        s = data.lower()
        if "twitchconfigerror" in s and "missing twitch_client_id" in s:
            return True
        if "missing twitch_client_id" in s or "missing twitch_client_secret" in s:
            return True

    if sc == 503:
        return True

    return False


def run_step(results: List[StepResult], name: str, fn: Callable[[], Any]) -> Any:
    try:
        out = fn()
        results.append(StepResult(name=name, status="OK"))
        return out
    except SmokeFail as e:
        results.append(StepResult(name=name, status="FAIL", detail=str(e)))
        return None
    except Exception as e:
        results.append(StepResult(name=name, status="FAIL", detail=f"{type(e).__name__}: {e}"))
        return None


def mark_skip(results: List[StepResult], name: str, detail: str) -> None:
    results.append(StepResult(name=name, status="SKIP", detail=detail))


# -------------------------
# API calls
# -------------------------

def register_user(cfg: Config) -> None:
    url = f"{cfg.base_url}/auth/register/"
    payload = {"username": cfg.username, "email": cfg.email, "password": cfg.password}
    sc, data = request_json("POST", url, json_body=payload, timeout_s=cfg.timeout_s)
    if sc in (201, 400, 409):
        return
    raise SmokeFail(f"Register unexpected status {sc}\n{_pretty(data)}")


def login(cfg: Config) -> str:
    url = f"{cfg.base_url}/auth/login/"
    payload = {"email": cfg.email, "password": cfg.password}
    sc, data = request_json("POST", url, json_body=payload, timeout_s=cfg.timeout_s)
    if sc != 200 or not isinstance(data, dict) or "access" not in data:
        raise SmokeFail(f"Login failed {sc}\n{_pretty(data)}")
    return data["access"]


def list_communities(cfg: Config) -> Any:
    url = f"{cfg.base_url}/communities/"
    sc, data = request_json("GET", url, timeout_s=cfg.timeout_s)
    if sc != 200:
        raise SmokeFail(f"GET /communities/ failed {sc}\n{_pretty(data)}")
    return data


def create_community(cfg: Config, token: str) -> Optional[Dict[str, Any]]:
    url = f"{cfg.base_url}/communities/"
    payload = {
        "twitch": cfg.smoke_twitch,
        "description": f"smoke test create ({_rand_suffix(6)})",
        "name": f"Smoke Community {_rand_suffix(6)}",
    }
    sc, data = request_json(
        "POST", url, headers=auth_headers(token), json_body=payload, timeout_s=cfg.timeout_s
    )

    if sc == 201 and isinstance(data, dict) and "id" in data and "slug" in data:
        return data

    if is_twitch_not_configured(sc, data):
        return None  # signal: create skipped due to config

    raise SmokeFail(f"POST /communities/ failed {sc}\n{_pretty(data)}")


def get_community_by_slug(cfg: Config, slug: str, token: str) -> Dict[str, Any]:
    url = f"{cfg.base_url}/communities/slug/{slug}/"
    sc, data = request_json("GET", url, headers=auth_headers(token), timeout_s=cfg.timeout_s)
    if sc != 200 or not isinstance(data, dict):
        raise SmokeFail(f"GET /communities/slug/{slug}/ failed {sc}\n{_pretty(data)}")
    return data


def patch_community(cfg: Config, token: str, community_id: int) -> Dict[str, Any]:
    url = f"{cfg.base_url}/communities/{community_id}/"
    payload = {"description": "smoke test patched"}
    sc, data = request_json(
        "PATCH", url, headers=auth_headers(token), json_body=payload, timeout_s=cfg.timeout_s
    )
    if sc != 200:
        raise SmokeFail(f"PATCH /communities/{community_id}/ failed {sc}\n{_pretty(data)}")
    return data if isinstance(data, dict) else {"raw": data}


def join_community(cfg: Config, token: str, community_id: int) -> None:
    url = f"{cfg.base_url}/communities/{community_id}/join/"
    sc, data = request_json("POST", url, headers=auth_headers(token), timeout_s=cfg.timeout_s)
    if sc not in (200, 201):
        raise SmokeFail(f"POST /communities/{community_id}/join/ failed {sc}\n{_pretty(data)}")


def leave_community(cfg: Config, token: str, community_id: int) -> None:
    url = f"{cfg.base_url}/communities/{community_id}/leave/"
    sc, data = request_json("POST", url, headers=auth_headers(token), timeout_s=cfg.timeout_s)
    if sc == 400:
        return  # last admin guard etc. -> not a hard fail for smoke
    if sc != 200:
        raise SmokeFail(f"POST /communities/{community_id}/leave/ failed {sc}\n{_pretty(data)}")


def me_communities(cfg: Config, token: str) -> Any:
    url = f"{cfg.base_url}/me/communities/"
    sc, data = request_json("GET", url, headers=auth_headers(token), timeout_s=cfg.timeout_s)
    if sc != 200:
        raise SmokeFail(f"GET /me/communities/ failed {sc}\n{_pretty(data)}")
    return data


# -------------------------
# selection logic
# -------------------------

def pick_existing_community_from_list(list_data: Any) -> Optional[Dict[str, Any]]:
    """Pick the first item with id+slug from GET /communities/."""
    if not isinstance(list_data, list):
        return None
    for c in list_data:
        if isinstance(c, dict) and c.get("id") is not None and c.get("slug"):
            return c
    return None


def select_target_community(
    cfg: Config,
    token: str,
    list_data: Any,
    created: Optional[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Select community for the main flow (get/join/leave/me).

    Priority:
      1) Your manually created community by slug (cfg.testcommunity_slug)
      2) First community from GET /communities/
      3) Created community (if available)
    """
    # 1) testcommunity as preferred existing fallback target
    if cfg.testcommunity_slug:
        try:
            detail = get_community_by_slug(cfg, cfg.testcommunity_slug, token)
            if detail.get("id") and detail.get("slug"):
                return {"id": detail["id"], "slug": detail["slug"]}, f"preferred slug '{cfg.testcommunity_slug}'"
        except Exception:
            pass

    # 2) any existing community from list
    existing = pick_existing_community_from_list(list_data)
    if existing:
        return {"id": existing.get("id"), "slug": existing.get("slug")}, "first existing from /communities/"

    # 3) created fallback
    if created and created.get("id") and created.get("slug"):
        return {"id": created.get("id"), "slug": created.get("slug")}, "created community fallback"

    return None, "no community available"


def find_admin_candidate(
    cfg: Config,
    token: str,
    list_data: Any,
    created: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Try to find a community where current user is admin to attempt PATCH.
    Strategy:
      1) If created exists, it's admin -> prefer it.
      2) Otherwise, scan up to N existing communities:
         - GET detail by slug with auth and check my_role == "admin"
    """
    if created and created.get("id") and created.get("slug"):
        return created

    candidates: List[Dict[str, Any]] = []
    if isinstance(list_data, list):
        for c in list_data[:10]:
            if isinstance(c, dict) and c.get("id") and c.get("slug"):
                candidates.append(c)

    for c in candidates:
        try:
            detail = get_community_by_slug(cfg, c["slug"], token)
            if detail.get("my_role") == "admin":
                return {"id": detail.get("id"), "slug": detail.get("slug")}
        except Exception:
            continue

    return None


# -------------------------
# summary
# -------------------------

def summarize(results: List[StepResult]) -> int:
    print("\n=== SUMMARY ===")
    ok = sum(1 for r in results if r.status == "OK")
    skip = sum(1 for r in results if r.status == "SKIP")
    fail = sum(1 for r in results if r.status == "FAIL")

    for r in results:
        print(f"{r.status:4}  {r.name}")
        if r.detail and r.status in ("FAIL", "SKIP"):
            print(f"      {r.detail}")

    print(f"\nTotals: OK={ok}  SKIP={skip}  FAIL={fail}")
    return 1 if fail > 0 else 0


def main() -> int:
    cfg = Config(
        base_url=os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
        username=os.getenv("USERNAME", "testuser_1"),
        email=os.getenv("EMAIL", "testuser_1@example.com"),
        password=os.getenv("PASSWORD", "StrongPassword123!"),
        timeout_s=int(os.getenv("TIMEOUT_S", "20")),
        smoke_twitch=os.getenv("SMOKE_TWITCH", "https://twitch.tv/handofblood"),
        testcommunity_slug=os.getenv("TESTCOMMUNITY_SLUG", "testcommunity"),
    )

    cfg.username, cfg.email = make_unique_identity(cfg.username, cfg.email)

    results: List[StepResult] = []

    print("=== Smoke Communities (testcommunity fallback) ===")
    print(f"BASE_URL:         {cfg.base_url}")
    print(f"USERNAME:         {cfg.username}")
    print(f"EMAIL:            {cfg.email}")
    print(f"TWITCH:           {cfg.smoke_twitch}")
    print(f"TESTCOMMUNITY:    {cfg.testcommunity_slug}\n")

    run_step(results, "Register", lambda: register_user(cfg))

    token = run_step(results, "Login", lambda: login(cfg))
    if not token:
        for name in [
            "List communities",
            "Create community (optional)",
            "Select community",
            "Selected community info",
            "Get by slug",
            "Patch by id",
            "Join",
            "Me communities",
            "Me communities returns list",
            "Leave",
        ]:
            mark_skip(results, name, "Skipped because Login failed")
        return summarize(results)

    list_data = run_step(results, "List communities", lambda: list_communities(cfg))

    # Create is optional (may be skipped if Twitch not configured)
    created = run_step(results, "Create community (optional)", lambda: create_community(cfg, token))
    if created is None:
        last = results[-1]
        if last.name == "Create community (optional)" and last.status == "OK":
            last.status = "SKIP"
            last.detail = "Skipped because Twitch client credentials are not configured (or create disabled)"

    selected_tuple = run_step(
        results,
        "Select community",
        lambda: select_target_community(cfg, token, list_data, created if isinstance(created, dict) else None),
    )

    if not selected_tuple or not isinstance(selected_tuple, tuple):
        for name in ["Selected community info", "Get by slug", "Patch by id", "Join", "Me communities", "Me communities returns list", "Leave"]:
            mark_skip(results, name, "Skipped because no community is available")
        return summarize(results)

    selected, reason = selected_tuple
    if not selected:
        for name in ["Selected community info", "Get by slug", "Patch by id", "Join", "Me communities", "Me communities returns list", "Leave"]:
            mark_skip(results, name, f"Skipped: {reason}")
        return summarize(results)

    results.append(
        StepResult(
            name="Selected community info",
            status="OK",
            detail=f"Using id={selected.get('id')} slug={selected.get('slug')} ({reason})",
        )
    )

    community_id = int(selected["id"])
    slug = str(selected["slug"])

    detail = run_step(results, "Get by slug", lambda: get_community_by_slug(cfg, slug, token))
    if isinstance(detail, dict):
        print(f"[INFO] Selected community id={community_id}, slug={slug}")
        print(f"[INFO] is_member={detail.get('is_member')} my_role={detail.get('my_role')}")

    # PATCH: only if we can find a community where current user is admin
    admin_target = find_admin_candidate(cfg, token, list_data, created if isinstance(created, dict) else None)
    if not admin_target:
        mark_skip(results, "Patch by id", "No admin community found for this user (expected with fresh user)")
    else:
        run_step(results, "Patch by id", lambda: patch_community(cfg, token, int(admin_target["id"])))

    # Join/Leave should operate on the selected community (testcommunity preferred)
    run_step(results, "Join", lambda: join_community(cfg, token, community_id))

    mine = run_step(results, "Me communities", lambda: me_communities(cfg, token))

    def _assert_me_list() -> None:
        if not isinstance(mine, list):
            raise SmokeFail("Expected list response from /me/communities/")
    run_step(results, "Me communities returns list", _assert_me_list)

    run_step(results, "Leave", lambda: leave_community(cfg, token, community_id))

    return summarize(results)


if __name__ == "__main__":
    sys.exit(main())


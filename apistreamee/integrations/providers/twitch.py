import os
import time
from dataclasses import dataclass
from typing import Optional

import requests


TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")


@dataclass
class TwitchUser:
    id: str
    login: str
    display_name: str
    profile_image_url: str


# Simple in-memory cache (process lifetime)
_APP_TOKEN: Optional[str] = None
_APP_TOKEN_EXPIRES_AT: float = 0.0


class TwitchConfigError(RuntimeError):
    pass


class TwitchNotFoundError(RuntimeError):
    pass


def _require_creds() -> None:
    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET:
        raise TwitchConfigError("Missing TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET env vars.")


def _get_app_access_token() -> str:
    """
    Client Credentials flow token (App Access Token).
    Cached in-memory with expiry buffer.
    """
    global _APP_TOKEN, _APP_TOKEN_EXPIRES_AT
    _require_creds()

    now = time.time()
    if _APP_TOKEN and now < (_APP_TOKEN_EXPIRES_AT - 30):
        return _APP_TOKEN

    r = requests.post(
        "https://id.twitch.tv/oauth2/token",
        params={
            "client_id": TWITCH_CLIENT_ID,
            "client_secret": TWITCH_CLIENT_SECRET,
            "grant_type": "client_credentials",
        },
        timeout=20,
    )
    r.raise_for_status()
    payload = r.json()
    _APP_TOKEN = payload["access_token"]
    # expires_in is seconds
    _APP_TOKEN_EXPIRES_AT = now + int(payload.get("expires_in", 0))
    return _APP_TOKEN


def resolve_user_by_login(login: str) -> TwitchUser:
    """
    Helix: GET /users?login=<login>
    Returns TwitchUser or raises TwitchNotFoundError.
    """
    token = _get_app_access_token()

    r = requests.get(
        "https://api.twitch.tv/helix/users",
        params={"login": login},
        headers={
            "Authorization": f"Bearer {token}",
            "Client-Id": TWITCH_CLIENT_ID,
        },
        timeout=20,
    )
    r.raise_for_status()
    data = r.json().get("data", [])
    if not data:
        raise TwitchNotFoundError(f"Twitch user not found for login={login}")

    u = data[0]
    return TwitchUser(
        id=str(u["id"]),
        login=u["login"],
        display_name=u["display_name"],
        profile_image_url=u.get("profile_image_url", ""),
    )

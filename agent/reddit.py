"""Minimal app-only OAuth adapter for a read-only connectivity check."""
import base64
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

class RedditError(Exception):
    pass

def _request_json(request):
    try:
        with urlopen(request, timeout=15) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RedditError(f"Reddit returned HTTP {exc.code}; check app type, credentials, and access.") from None
    except (URLError, TimeoutError, OSError):
        raise RedditError("Could not reach Reddit. Check your network and try again.") from None
    except (ValueError, UnicodeDecodeError):
        raise RedditError("Reddit returned an invalid response.") from None

def check_connection(config):
    basic = base64.b64encode(f"{config.client_id}:{config.client_secret}".encode()).decode()
    request = Request("https://www.reddit.com/api/v1/access_token", data=urlencode({"grant_type": "client_credentials"}).encode(), headers={"Authorization": "Basic " + basic, "User-Agent": config.user_agent}, method="POST")
    token = _request_json(request).get("access_token")
    if not isinstance(token, str) or not token:
        raise RedditError("Reddit did not issue an app-only token; check the app type and credentials.")
    # App-only tokens have no user identity. Use an application-readable endpoint instead.
    request = Request("https://oauth.reddit.com/api/v1/scopes", headers={"Authorization": "Bearer " + token, "User-Agent": config.user_agent})
    result = _request_json(request)
    if not isinstance(result, dict) or not result:
        raise RedditError("Reddit returned an unexpected scopes response.")
    return True

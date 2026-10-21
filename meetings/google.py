"""The Google side of the meetings app.

The token endpoints of Google and the Meet REST API are plain https
endpoints that speak json, so this module talks to them with the standard
library alone (urllib.request). Nothing here is a real dependency of the
page itself: when no credential exists every function says so, and the
page still works - the call happens in the browser.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from django.conf import settings as django_settings
from django.urls import reverse

from settings.models import GoogleCredential

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
SPACES_URL = 'https://meet.googleapis.com/v2/spaces'

# creating a space is the only Meet REST call the app makes
SCOPE = 'https://www.googleapis.com/auth/meetings.space.created'


class GoogleNotConnected(Exception):
    """There is no Google credential with a refresh token."""


class GoogleError(Exception):
    """Google refused something (bad code, dead token, denied space)."""


def credential():
    """The stored credential row, or None when it has no secrets yet."""
    return GoogleCredential.objects.first()


def connected():
    row = credential()
    return bool(row and row.refresh_token)


def redirect_uri(request):
    """The callback url of this app, as Google has to be told it."""
    build = request.build_absolute_uri(reverse('meetings_callback'))
    if django_settings.DEBUG:
        # the dev server answers on 127.0.0.1:8000 behind the test runner
        return build.replace('testserver', '127.0.0.1:8000')
    return build


def authorize_url(request, state):
    """The consent screen, with offline access so the server can renew."""
    client = credential()
    if client is None or not client.client_id or not client.client_secret:
        raise GoogleNotConnected
    query = urllib.parse.urlencode({
        'response_type': 'code',
        'client_id': client.client_id,
        'redirect_uri': redirect_uri(request),
        'scope': SCOPE,
        'access_type': 'offline',
        'prompt': 'consent',
        'include_granted_scopes': 'true',
        'state': state,
    })
    return f'{AUTH_URL}?{query}'


def exchange_code(request, code):
    """An authorization code as the stored tokens."""
    client = credential()
    if client is None:
        raise GoogleNotConnected
    body = urllib.parse.urlencode({
        'code': code,
        'client_id': client.client_id,
        'client_secret': client.client_secret,
        'redirect_uri': redirect_uri(request),
        'grant_type': 'authorization_code',
    }).encode()
    data = _post(TOKEN_URL, body)
    client.refresh_token = data.get('refresh_token') or ''
    client.access_token = data.get('access_token') or ''
    _store_expiry(client, data)
    client.save()
    return client


def _post(url, body, bearer=None, json_body=False):
    headers = {}
    if json_body:
        headers['Content-Type'] = 'application/json'
    else:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'
    if bearer:
        headers['Authorization'] = f'Bearer {bearer}'
    request = urllib.request.Request(url, data=body, headers=headers, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=25) as answer:
            return json.loads(answer.read())
    except urllib.error.HTTPError as exc:
        detail = ''
        try:
            detail = json.loads(exc.read()).get('error_description', '')
        except Exception:
            pass
        raise GoogleError(detail or f'Google replied {exc.code}') from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise GoogleError(f'Could not reach Google: {exc}') from exc


def _store_expiry(client, data):
    seconds = data.get('expires_in')
    try:
        client.access_token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=int(seconds)
        )
    except (TypeError, ValueError):
        client.access_token_expires_at = None


def access_token(client=None):
    """A bearer token that is surely good for a few more minutes."""
    client = client or credential()
    if client is None or not client.refresh_token:
        raise GoogleNotConnected
    fresh = datetime.now(timezone.utc)
    if client.access_token and (
        client.access_token_expires_at is None
        or client.access_token_expires_at > fresh + timedelta(seconds=60)
    ):
        return client.access_token
    body = urllib.parse.urlencode({
        'client_id': client.client_id,
        'client_secret': client.client_secret,
        'refresh_token': client.refresh_token,
        'grant_type': 'refresh_token',
    }).encode()
    data = _post(TOKEN_URL, body)
    client.access_token = data.get('access_token') or ''
    _store_expiry(client, data)
    client.save()
    return client.access_token


def create_space():
    """A meeting space with a real meet.google.com link of its own."""
    token = access_token()
    data = _post(SPACES_URL, b'{}', bearer=token, json_body=True)
    return {
        'uri': data.get('meetingUri') or '',
        'code': data.get('meetingCode') or '',
        'name': data.get('name') or '',
    }

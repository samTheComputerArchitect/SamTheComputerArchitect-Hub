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
API_URL = 'https://meet.googleapis.com/v2'
SPACES_URL = 'https://meet.googleapis.com/v2/spaces'

# creating a space is the *only* change the app makes on Google; the read
# scope comes along so the hub can peek at the facts Meet is willing to
# say about a space - is a conference live there right now, how many
# people are in it. The streams themselves are never served to the api.
SCOPE = ' '.join([
    'https://www.googleapis.com/auth/meetings.space.created',
    'https://www.googleapis.com/auth/meetings.space.readonly',
])


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


def _refusal(exc):
    """The sentence Google put inside its error response, or a code."""
    detail = ''
    try:
        body = json.loads(exc.read())
        # the token endpoint speaks error_description, the rest apis
        # speak error.message - both deserve to be seen on the page
        detail = body.get('error_description') or ''
        if not detail and isinstance(body.get('error'), dict):
            detail = body['error'].get('message') or ''
        if not detail and isinstance(body.get('error'), str):
            detail = body['error']
    except Exception:
        detail = ''
    return detail or f'Google replied {exc.code}'


def _get(url, bearer):
    request = urllib.request.Request(url, headers={'Authorization': f'Bearer {bearer}'})
    try:
        with urllib.request.urlopen(request, timeout=25) as answer:
            return json.loads(answer.read())
    except urllib.error.HTTPError as exc:
        raise GoogleError(_refusal(exc)) from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise GoogleError(f'Could not reach Google: {exc}') from exc


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
        raise GoogleError(_refusal(exc)) from exc
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
    """A meeting space with a real meet.google.com link of its own.

    The space is created open on purpose: a person who has the link can
    walk in without knocking, and the knock request would otherwise be
    handed to the organizer inside Meet itself - a window that, unless
    the owner opens the call in person, stays empty forever.
    """
    token = access_token()
    body = json.dumps({'config': {'accessType': 'OPEN'}}).encode()
    data = _post(SPACES_URL, body, bearer=token, json_body=True)
    return {
        'uri': data.get('meetingUri') or '',
        'code': data.get('meetingCode') or '',
        'name': data.get('name') or '',
    }


def space_peek(name):
    """The facts Meet publishes about a space through the api.

    One GET tells whether a conference is live in the space this second;
    a second GET switches on the live conference and counts the people
    in it. That is the whole catalogue of what the REST side knows: the
    cameras and the microphones of a Meet call are never served here,
    which is exactly why the hub can only look through a keyhole.
    """
    token = access_token()
    path = name if name.startswith('spaces/') else f'spaces/{name}'
    space = _get(f'{API_URL}/{path}', token)
    record = (space.get('activeConference') or {}).get('conferenceRecord') or ''
    if not record:
        return {'live': False, 'people': 0}
    try:
        people = _get(f'{API_URL}/{record}/participants', token)
    except GoogleError:
        # the conference is live, but the list of people is not served -
        # the liveness still holds, so the page says the room is busy
        return {'live': True, 'people': None}
    return {'live': True, 'people': len(people.get('participants') or [])}

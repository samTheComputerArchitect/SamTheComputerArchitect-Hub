"""The meetings page.

The list of meetings, the call page with the WebRTC pieces, and two
small endpoints that carry the browser-to-browser signalling over plain
http: every page on the call posts the messages it wants to send and
takes the ones addressed to it, about once a second.
"""

import json
import threading
import time
import uuid
from urllib.parse import quote_plus

from django.core.signing import BadSignature, SignatureExpired, dumps, loads
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from . import google
from .models import Meeting

# how long a page counts as part of the call without a heartbeat
PRESENCE_SECONDS = 10.0
# the board of a meeting never holds more than this per peer
MAX_MESSAGES = 400


def meetings_page(request):
    """Every meeting, newest first, with the connect state of Google."""
    return render(request, 'meetings/meetings.html', {
        'meetings': Meeting.objects.all(),
        'google_connected': google.connected(),
        'hint': (request.GET.get('hint') or '')[:200],
    })


@require_GET
def meetings_peek(request):
    """What Google says about every row'sMeet space, as one small json.

    A page asks every so often; the answer carries only what the Meet
    REST API publishes: whether a conference is live in the space and
    how many people are in it. Nothing here pipes the media.
    """
    out = {}
    for meeting in Meeting.objects.exclude(space_name=''):
        try:
            out[str(meeting.pk)] = google.space_peek(meeting.space_name)
        except google.GoogleNotConnected:
            return JsonResponse({'ok': False, 'reason': 'not-connected'})
        except google.GoogleError as exc:
            return JsonResponse({'ok': False, 'reason': str(exc)})
    return JsonResponse({'ok': True, 'rooms': out})


@require_POST
def create_meeting(request):
    """A new meeting row, dressed with a Meet link when Google allows it."""
    title = (request.POST.get('title') or '').strip()[:200]
    if not title:
        return redirect(f"{reverse('meetings')}?hint=Title+is+required")

    meeting = Meeting.objects.create(title=title)
    if google.connected():
        try:
            space = google.create_space()
        except google.GoogleError as exc:
            # the meeting exists either way; the link can be retried later
            return redirect(f"{reverse('meetings')}?hint={quote_plus(str(exc))}")
        meeting.meet_uri = space['uri']
        meeting.meet_code = space['code']
        meeting.space_name = space['name']
        meeting.save()
    return redirect(reverse('meetings'))


@require_POST
def create_meet_link(request, pk):
    """Try the Meet link again on a meeting row that has none."""
    meeting = Meeting.objects.filter(pk=pk).first()
    if meeting is None:
        return redirect(reverse('meetings'))
    if not google.connected():
        return redirect(f"{reverse('meetings')}?hint=missing-client")
    try:
        space = google.create_space()
    except google.GoogleError as exc:
        return redirect(f"{reverse('meetings')}?hint={quote_plus(str(exc))}")
    meeting.meet_uri = space['uri']
    meeting.meet_code = space['code']
    meeting.space_name = space['name']
    meeting.save()
    return redirect(reverse('meetings'))


@require_POST
def delete_meeting(request, pk):
    meeting = Meeting.objects.filter(pk=pk).first()
    if meeting:
        meeting.delete()
    return redirect(reverse('meetings'))


def meeting_page(request, pk):
    """The call: one video grid, one row of buttons, the meet link."""
    meeting = Meeting.objects.filter(pk=pk).first()
    if meeting is None:
        return redirect(reverse('meetings'))
    return render(request, 'meetings/meeting.html', {'meeting': meeting})


def connect_google(request):
    """The consent screen of Google, carrying a signed state."""
    try:
        url = google.authorize_url(request, dumps('meetings-connect', salt='meetings'))
    except google.GoogleNotConnected:
        # the client id and secret come from the settings page first
        return redirect(f"{reverse('settings')}?tab=api_keys&hint=missing-client")
    except Exception:
        return redirect(f"{reverse('meetings')}?hint=connect-error")
    return redirect(url)


def oauth_callback(request):
    """Google comes back with a code; the tokens get stored."""
    problem = request.GET.get('error') or ''
    code = request.GET.get('code') or ''
    state = request.GET.get('state') or ''
    if not problem and code and state:
        try:
            loads(state, salt='meetings')
        except (BadSignature, SignatureExpired):
            problem = 'bad-state'
        else:
            try:
                google.exchange_code(request, code)
            except google.GoogleError as exc:
                problem = str(exc)
            except google.GoogleNotConnected:
                problem = 'no-client'
    elif not problem:
        problem = 'empty-code'
    if problem:
        return redirect(f"{reverse('meetings')}?hint={problem}")
    return redirect(f"{reverse('meetings')}?hint=connected")


@require_POST
def disconnect_google(request):
    """Forget the tokens; the client id and secret stay for next time."""
    row = google.credential()
    if row:
        row.refresh_token = ''
        row.access_token = ''
        row.access_token_expires_at = None
        row.save()
    return redirect(f"{reverse('meetings')}?hint=disconnected")


@require_GET
def meeting_signal(request, pk):
    """Everything new since the cursor of the page, and the roster."""
    me = (request.GET.get('me') or '').strip()
    try:
        uuid.UUID(me)
    except ValueError:
        return JsonResponse({'error': 'A client id is required'}, status=400)
    with _lock:
        room = _room(str(pk))
        seen = room['seen']
        seen[me] = time.monotonic()
        # every page owns a queue of its own: the delivery of a send drops
        # the message into each queue that a peer lives there, and reading
        # is a walk through this page's own queue with its own cursor
        room['inbox'].setdefault(me, [])
        mine = room['inbox'][me]
        cursor = (request.GET.get('cursor') or '').strip()
        try:
            after = int(cursor)
        except ValueError:
            after = 0
        fresh = [
            message
            for message in mine
            if message['id'] > after and message['to'] in (me, None)
        ]
        _forget_ancient(room)
        roster = sorted(
            client_id
            for client_id in room['inbox']
            if time.monotonic() - seen.get(client_id, 0) <= PRESENCE_SECONDS
        )
    return JsonResponse({'messages': fresh, 'roster': roster})


@require_POST
def meeting_send(request, pk):
    """One message of the signalling, onto the meeting's board."""
    me = (request.POST.get('me') or '').strip()
    try:
        uuid.UUID(me)
    except ValueError:
        return JsonResponse({'error': 'A client id is required'}, status=400)
    try:
        payload = json.loads((request.POST.get('payload') or '{}')[:1800])
    except ValueError:
        return JsonResponse({'error': 'The payload has to be json'}, status=400)
    if not isinstance(payload, dict):
        payload = {}
    message_type = (request.POST.get('type') or '')[:40]
    to = (request.POST.get('to') or '').strip() or None
    with _lock:
        room = _room(str(pk))
        room['seen'][me] = time.monotonic()
        room['inbox'].setdefault(me, [])
        next_id = 1
        for inbox in room['inbox'].values():
            if inbox:
                next_id = max(next_id, inbox[-1]['id'] + 1)
        message = {
            'id': next_id,
            'from': me,
            'to': to,
            'type': message_type,
            'payload': payload,
        }
        for client_id in room['inbox']:
            if client_id == me:
                continue  # a page never reads its own offer twice
            if to is not None and client_id != to:
                continue  # or an answer meant for someone else
            room['inbox'][client_id].append(message)
            if len(room['inbox'][client_id]) > MAX_MESSAGES:
                del room['inbox'][client_id][: -MAX_MESSAGES]
    return JsonResponse({'id': message['id']})


# the signalling lives in the process: the hub is one small local server
# and a call is a handful of pages that visit it, so a lock and a couple
# of dictionaries serve instead of a database
_live = {}
_lock = threading.RLock()


def _room(pk):
    """The store of a meeting, created empty when nobody has touched it."""
    if pk not in _live:
        _live[pk] = {'inbox': {}, 'seen': {}}
    return _live[pk]


def _forget_ancient(room):
    """Drop anything from a page that stopped beating its heart."""
    now = time.monotonic()
    for client_id in list(room['inbox']):
        if now - room['seen'].get(client_id, 0) > PRESENCE_SECONDS:
            room['inbox'].pop(client_id, None)
            room['seen'].pop(client_id, None)

"""The calendar page.

Everything is rendered on the server; the browser only tells us which time
zone it is in (as the offset it sends with every request), so the grid and
the event times are shown in the time zone of the person looking at them.
"""

from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from urllib.parse import urlencode

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import Event

# The week starts on a Monday.
WEEK_START = 0
WEEKDAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
]
# The agenda looks this far ahead.
AGENDA_DAYS = 30
# The hour the week and day grid starts at.
GRID_START_HOUR = 0
GRID_END_HOUR = 24
# How tall one hour is in the week grid.
HOUR_HEIGHT = 44


def client_tz(request):
    """The time zone of the browser, as a fixed offset.

    The browser sends the offset of `Date.getTimezoneOffset()` (the
    difference between UTC and its own time, in minutes). Without a usable
    value the page falls back to UTC.
    """
    raw = request.POST.get('tz') or request.GET.get('tz') or ''
    try:
        offset = int(raw)
    except (TypeError, ValueError):
        offset = 0
    if not -14 * 60 <= offset <= 14 * 60:
        offset = 0
    return dt_timezone(timedelta(minutes=-offset))


def parse_date(raw):
    """A `YYYY-MM-DD` string as a date, or None."""
    parts = (raw or '').strip().split('-')
    if len(parts) != 3:
        return None
    try:
        year, month, day = (int(part) for part in parts)
        return date(year, month, day)
    except (TypeError, ValueError):
        return None


def parse_time(raw):
    """A `HH:MM` string as a time, or None."""
    parts = (raw or '').strip().split(':')
    if len(parts) != 2:
        return None
    try:
        hour, minute = (int(part) for part in parts)
    except (TypeError, ValueError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return time(hour, minute)


def to_local(value, tz):
    """A stored (UTC) datetime as the local time of the browser."""
    if value is None:
        return None
    return value.astimezone(tz)


def from_local(day, start_time, end_time, tz):
    """A local date and time as the UTC value that gets stored."""
    if day is None or start_time is None or end_time is None:
        return None, None
    start = datetime.combine(day, start_time, tzinfo=tz)
    end = datetime.combine(day, end_time, tzinfo=tz)
    # an event that ends before it starts is an event that runs over midnight
    if end <= start:
        end += timedelta(days=1)
    return start.astimezone(dt_timezone.utc), end.astimezone(dt_timezone.utc)


def month_grid(anchor):
    """The weeks of the month `anchor` falls in, as a list of date lists.

    The grid starts on the Monday of the week the first of the month is in
    and ends with the week the last of the month is in - five or six weeks.
    """
    first = anchor.replace(day=1)
    next_month = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    last = next_month - timedelta(days=1)
    lead = (first.weekday() - WEEK_START) % 7
    start = first - timedelta(days=lead)

    weeks = []
    for index in range(0, (last - start).days + 1, 7):
        week_start = start + timedelta(days=index)
        weeks.append([week_start + timedelta(days=day) for day in range(7)])
    return weeks


def instances(event, range_start, range_end, tz):
    """The occurrences of an event that fall into the given local range.

    A repeating event is walked forward from its first date, so the same
    event shows up on every day (or every week) it covers.
    """
    start = to_local(event.start, tz)
    end = to_local(event.end, tz)
    if start is None or end is None:
        return []
    duration = end - start
    if duration < timedelta(0):
        duration = timedelta(0)

    if event.repeat == Event.REPEAT_NONE:
        if start < range_end and end > range_start:
            return [(start, end)]
        return []

    step = timedelta(days=1 if event.repeat == Event.REPEAT_DAILY else 7)
    current = start
    if current < range_start:
        # skip the occurrences that are already past
        missed = (range_start - current) // step
        current += missed * step
        while current < range_start:
            current += step
    found = []
    while current < range_end:
        occurrence_end = current + duration
        if occurrence_end > range_start:
            found.append((current, occurrence_end))
        current += step
        if len(found) > 400:
            break
    return found


def events_in(range_start, range_end, tz):
    """Every occurrence between two local moments, grouped by day."""
    grouped = {}
    for event in Event.objects.all():
        for start, end in instances(event, range_start, range_end, tz):
            grouped.setdefault(start.date(), []).append({
                'event': event,
                'start': start,
                'end': end,
            })
    for day in grouped:
        grouped[day].sort(key=lambda item: item['start'])
    return grouped


def events_json(events, tz):
    """The events of the page, in the local time of the browser.

    The client needs them to fill the edit dialog: the title, the day and
    the times of the event as they are shown here. The template puts the
    result into a json script tag, so it is a plain dictionary.
    """
    data = {}
    for event in events:
        start = to_local(event.start, tz)
        end = to_local(event.end, tz)
        if start is None or end is None:
            continue
        # the wall clock of the browser, without a time zone
        start = start.replace(tzinfo=None)
        end = end.replace(tzinfo=None)
        data[str(event.pk)] = {
            'pk': event.pk,
            'title': event.title,
            'url': event.url or '',
            'date': start.date().isoformat(),
            'start': start.strftime('%H:%M'),
            'end': end.strftime('%H:%M'),
            'repeat': event.repeat,
        }
    return data


def items_for_day(grouped, day):
    """The events of one day, with the position the week view needs."""
    items = []
    for item in grouped.get(day, []):
        # naive local times: the date filter of the template would convert
        # them back to the time zone of the server
        start = item['start'].replace(tzinfo=None)
        end = item['end'].replace(tzinfo=None)
        minutes = (start.hour * 60 + start.minute) - GRID_START_HOUR * 60
        height = max(18, int((end - start).total_seconds() / 3600 * HOUR_HEIGHT))
        items.append({
            'event': item['event'],
            'start': start,
            'end': end,
            'top': int(minutes / 60 * HOUR_HEIGHT),
            'height': height,
        })
    return items


def format_time(value):
    """A time as `14:30`."""
    return value.strftime('%H:%M')


def calendar_page(request):
    """The calendar: month, week or agenda."""
    tz = client_tz(request)
    view = (request.GET.get('view') or 'month').strip().lower()
    if view not in ('month', 'week', 'agenda'):
        view = 'month'

    today = datetime.now(tz).date()
    anchor = parse_date(request.GET.get('date')) or today

    context = {
        'view': view,
        'today': today,
        'tz_offset': request.GET.get('tz', ''),
        'weekday_names': WEEKDAY_NAMES,
        'anchor_date': anchor.isoformat(),
    }

    mini_weeks = [
        [
            {
                'day': day,
                'outside': day.month != anchor.month or day.year != anchor.year,
            }
            for day in week
        ]
        for week in month_grid(anchor)
    ]
    context['mini_weeks'] = mini_weeks

    if view == 'week':
        lead = (anchor.weekday() - WEEK_START) % 7
        first = anchor - timedelta(days=lead)
        days = [first + timedelta(days=i) for i in range(7)]
        range_start = datetime.combine(days[0], time.min, tzinfo=tz)
        range_end = datetime.combine(days[-1] + timedelta(days=1), time.min, tzinfo=tz)
        grouped = events_in(range_start, range_end, tz)
        context.update({
            'week_days': [
                {
                    'day': day,
                    'name': WEEKDAY_NAMES[index],
                    'is_today': day == today,
                    'items': items_for_day(grouped, day),
                }
                for index, day in enumerate(days)
            ],
            'hours': list(range(GRID_START_HOUR, GRID_END_HOUR)),
            'hour_height': HOUR_HEIGHT,
            'title': f"{MONTH_NAMES[first.month - 1]} {first.year}",
            'previous_date': (first - timedelta(days=7)).isoformat(),
            'next_date': (first + timedelta(days=7)).isoformat(),
            'events_json': events_json(Event.objects.all(), tz),
        })
        return render(request, 'calendar/calendar.html', context)

    if view == 'agenda':
        range_start = datetime.combine(today, time.min, tzinfo=tz)
        range_end = range_start + timedelta(days=AGENDA_DAYS)
        grouped = events_in(range_start, range_end, tz)
        context.update({
            'agenda_days': [
                {
                    'day': day,
                    'is_today': day == today,
                    'items': items_for_day(grouped, day),
                }
                for day in sorted(grouped)
            ],
            'title': f'Next {AGENDA_DAYS} days',
            'previous_date': (today - timedelta(days=AGENDA_DAYS)).isoformat(),
            'next_date': (today + timedelta(days=AGENDA_DAYS)).isoformat(),
            'events_json': events_json(Event.objects.all(), tz),
        })
        return render(request, 'calendar/calendar.html', context)

    # the month view
    weeks = month_grid(anchor)
    first = weeks[0][0]
    last = weeks[-1][-1]
    range_start = datetime.combine(first, time.min, tzinfo=tz)
    range_end = datetime.combine(last + timedelta(days=1), time.min, tzinfo=tz)
    grouped = events_in(range_start, range_end, tz)
    context.update({
        'cells': [
            {
                'day': day,
                'is_today': day == today,
                'outside': day.month != anchor.month or day.year != anchor.year,
                'items': items_for_day(grouped, day),
            }
            for week in weeks
            for day in week
        ],
        'weekday_names': WEEKDAY_NAMES,
        'title': f"{MONTH_NAMES[anchor.month - 1]} {anchor.year}",
        'previous_date': (anchor.replace(day=1) - timedelta(days=1)).isoformat(),
        'next_date': (anchor.replace(day=1) + timedelta(days=32)).replace(day=1).isoformat(),
        'events_json': events_json(Event.objects.all(), tz),
    })
    return render(request, 'calendar/calendar.html', context)


def clean_url(value):
    """The link of an event, or None when it is not a link we trust.

    Only http and https are allowed: the url ends up in the href of an
    anchor, and a `javascript:` url would run in the page.
    """
    text = (value or '').strip()
    if not text:
        return ''
    if len(text) > 500:
        return None
    if not text.lower().startswith(('http://', 'https://')):
        return None
    return text


def _event_form(request):
    """The values of the create/edit form, as local strings."""
    tz = client_tz(request)
    day = parse_date(request.POST.get('date'))
    start_time = parse_time(request.POST.get('start'))
    end_time = parse_time(request.POST.get('end'))
    repeat = (request.POST.get('repeat') or Event.REPEAT_NONE).strip()
    if repeat not in dict(Event.REPEAT_CHOICES):
        repeat = Event.REPEAT_NONE
    url = clean_url(request.POST.get('url'))
    return tz, day, start_time, end_time, repeat, url


@require_POST
def create_event(request):
    """A new event, created from a click on a day or a time."""
    tz, day, start_time, end_time, repeat, url = _event_form(request)
    title = (request.POST.get('title') or '').strip()[:200]
    if not title or day is None or start_time is None or end_time is None:
        return JsonResponse({'error': 'Title, date and times are required'}, status=400)
    if url is None:
        return JsonResponse(
            {'error': 'The link has to start with http:// or https://'}, status=400
        )
    start, end = from_local(day, start_time, end_time, tz)
    Event.objects.create(
        title=title,
        start=start,
        end=end,
        repeat=repeat,
        url=url,
    )
    return redirect(_back_to(request))


@require_POST
def update_event(request, pk):
    """Change an event, or delete it."""
    event = Event.objects.filter(pk=pk).first()
    if event is None:
        return JsonResponse({'error': 'Event not found'}, status=404)

    if (request.POST.get('delete') or '').strip():
        event.delete()
        return redirect(_back_to(request))

    tz, day, start_time, end_time, repeat, url = _event_form(request)
    title = (request.POST.get('title') or '').strip()[:200]
    if not title or day is None or start_time is None or end_time is None:
        return JsonResponse({'error': 'Title, date and times are required'}, status=400)
    if url is None:
        return JsonResponse(
            {'error': 'The link has to start with http:// or https://'}, status=400
        )
    start, end = from_local(day, start_time, end_time, tz)
    event.title = title
    event.start = start
    event.end = end
    event.repeat = repeat
    event.url = url
    event.save()
    return redirect(_back_to(request))


def _back_to(request):
    """The calendar page the user came from."""
    view = (request.POST.get('view') or 'month').strip().lower()
    if view not in ('month', 'week', 'agenda'):
        view = 'month'
    date_value = request.POST.get('back_date') or ''
    query = {'view': view, 'tz': request.POST.get('tz', '')}
    if date_value:
        query['date'] = date_value
    return f"{reverse('calendar')}?{urlencode(query)}"

from datetime import date, datetime, timedelta, timezone

from django.test import TestCase
from django.urls import reverse

from .models import Event


class CalendarPageTests(TestCase):
    """The calendar page: month, week and agenda."""

    def setUp(self):
        self.url = reverse('calendar')

    def test_the_page_loads(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'cal-grid')

    def test_the_month_view_is_the_default(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context['view'], 'month')

    def test_the_week_view_shows_seven_days(self):
        response = self.client.get(self.url, {'view': 'week', 'date': '2026-10-20'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['week_days']), 7)

    def test_the_agenda_view_lists_the_days_with_events(self):
        Event.objects.create(
            title='Kickoff',
            start=datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc),
        )
        response = self.client.get(self.url, {'view': 'agenda', 'date': '2026-10-20'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kickoff')

    def test_an_unknown_view_falls_back_to_the_month(self):
        response = self.client.get(self.url, {'view': 'year'})
        self.assertEqual(response.context['view'], 'month')

    def test_a_junk_date_falls_back_to_today(self):
        response = self.client.get(self.url, {'date': 'not-a-date'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['today'], date.today())

    def test_the_grid_covers_the_whole_month(self):
        response = self.client.get(self.url, {'date': '2026-10-20'})
        cells = response.context['cells']
        # the month of october 2026 needs five weeks
        self.assertEqual(len(cells), 35)
        self.assertEqual(cells[0]['day'], date(2026, 9, 28))
        self.assertEqual(cells[-1]['day'], date(2026, 11, 1))
        # the days of the month itself are not marked as outside
        october = [cell for cell in cells if cell['day'].month == 10]
        self.assertEqual(len(october), 31)
        self.assertFalse(any(cell['outside'] for cell in october))

    def test_the_sidebar_has_a_mini_month(self):
        response = self.client.get(self.url, {'date': '2026-10-20'})
        self.assertTrue(response.context['mini_weeks'])


class CalendarTimeZoneTests(TestCase):
    """The times are shown in the time zone of the browser."""

    def setUp(self):
        self.event = Event.objects.create(
            title='Standup',
            start=datetime(2026, 10, 20, 5, 30, tzinfo=timezone.utc),
            end=datetime(2026, 10, 20, 6, 0, tzinfo=timezone.utc),
        )

    def times_on_the_page(self, offset):
        response = self.client.get(
            reverse('calendar'), {'view': 'month', 'date': '2026-10-20', 'tz': offset}
        )
        self.assertEqual(response.status_code, 200)
        items = [item for cell in response.context['cells'] for item in cell['items']]
        return [item['start'].strftime('%H:%M') for item in items]

    def test_utc_shows_the_stored_time(self):
        self.assertEqual(self.times_on_the_page(0), ['05:30'])

    def test_the_browser_offset_shifts_the_time(self):
        # india is utc+5:30, the browser sends -330
        self.assertEqual(self.times_on_the_page(-330), ['11:00'])

    def test_a_junk_offset_falls_back_to_utc(self):
        self.assertEqual(self.times_on_the_page('abc'), ['05:30'])

    def test_the_event_lands_on_the_right_day(self):
        # 23:30 utc is already the next day in india
        self.event.start = datetime(2026, 10, 20, 19, 30, tzinfo=timezone.utc)
        self.event.end = datetime(2026, 10, 20, 20, 0, tzinfo=timezone.utc)
        self.event.save()
        response = self.client.get(
            reverse('calendar'), {'view': 'month', 'date': '2026-10-20', 'tz': '-330'}
        )
        days = [cell['day'] for cell in response.context['cells'] if cell['items']]
        self.assertEqual(days, [date(2026, 10, 21)])


class CalendarEventTests(TestCase):
    """Creating, changing and removing events."""

    def setUp(self):
        self.create_url = reverse('calendar_event_create')

    def post(self, data):
        return self.client.post(self.create_url, data)

    def test_an_event_is_created_and_stored_in_utc(self):
        response = self.post({
            'title': 'Design review',
            'date': '2026-10-21',
            'start': '11:00',
            'end': '12:30',
            'repeat': 'none',
            'tz': '-330',
            'view': 'month',
        })
        self.assertEqual(response.status_code, 302)
        event = Event.objects.get()
        self.assertEqual(event.title, 'Design review')
        self.assertEqual(event.start, datetime(2026, 10, 21, 5, 30, tzinfo=timezone.utc))
        self.assertEqual(event.end, datetime(2026, 10, 21, 7, 0, tzinfo=timezone.utc))

    def test_the_page_the_user_came_from_is_the_target(self):
        response = self.post({
            'title': 'Something',
            'date': '2026-10-21',
            'start': '11:00',
            'end': '12:00',
            'repeat': 'none',
            'tz': '-330',
            'view': 'week',
            'back_date': '2026-10-19',
        })
        self.assertRedirects(
            response,
            f"{reverse('calendar')}?view=week&tz=-330&date=2026-10-19",
            fetch_redirect_response=False,
        )

    def test_an_event_without_a_title_is_refused(self):
        response = self.post({
            'title': '  ',
            'date': '2026-10-21',
            'start': '11:00',
            'end': '12:00',
            'repeat': 'none',
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Event.objects.count(), 0)

    def test_an_event_without_a_date_is_refused(self):
        response = self.post({
            'title': 'Something',
            'date': '',
            'start': '11:00',
            'end': '12:00',
            'repeat': 'none',
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Event.objects.count(), 0)

    def test_an_unknown_repeat_falls_back_to_none(self):
        self.post({
            'title': 'Something',
            'date': '2026-10-21',
            'start': '11:00',
            'end': '12:00',
            'repeat': 'yearly',
        })
        self.assertEqual(Event.objects.get().repeat, Event.REPEAT_NONE)

    def test_an_event_that_ends_before_it_starts_runs_over_midnight(self):
        self.post({
            'title': 'Night shift',
            'date': '2026-10-21',
            'start': '23:00',
            'end': '01:00',
            'repeat': 'none',
            'tz': '0',
        })
        event = Event.objects.get()
        self.assertEqual(event.end - event.start, timedelta(hours=2))

    def test_an_event_is_changed(self):
        event = Event.objects.create(
            title='Old',
            start=datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 10, 21, 11, 0, tzinfo=timezone.utc),
        )
        response = self.client.post(reverse('calendar_event_update', args=[event.pk]), {
            'title': 'New',
            'date': '2026-10-22',
            'start': '09:00',
            'end': '10:00',
            'repeat': 'daily',
            'tz': '0',
        })
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.title, 'New')
        self.assertEqual(event.start, datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc))
        self.assertEqual(event.repeat, Event.REPEAT_DAILY)

    def test_an_event_is_deleted(self):
        event = Event.objects.create(
            title='Gone',
            start=datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 10, 21, 11, 0, tzinfo=timezone.utc),
        )
        response = self.client.post(
            reverse('calendar_event_update', args=[event.pk]),
            {'delete': '1', 'tz': '0', 'view': 'month'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Event.objects.count(), 0)

    def test_changing_an_event_that_does_not_exist_says_so(self):
        response = self.client.post(reverse('calendar_event_update', args=[999]), {
            'title': 'Nothing',
            'date': '2026-10-22',
            'start': '09:00',
            'end': '10:00',
        })
        self.assertEqual(response.status_code, 404)

    def test_the_endpoints_only_answer_to_a_post(self):
        self.assertEqual(self.client.get(self.create_url).status_code, 405)


class CalendarRepeatTests(TestCase):
    """A repeating event shows up on every day it covers."""

    def setUp(self):
        self.url = reverse('calendar')

    def count_on_the_page(self, offset=0):
        response = self.client.get(
            self.url, {'view': 'month', 'date': '2026-10-20', 'tz': offset}
        )
        return sum(len(cell['items']) for cell in response.context['cells'])

    def test_a_daily_event_repeats_every_day_of_the_month(self):
        Event.objects.create(
            title='Standup',
            start=datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 10, 1, 9, 15, tzinfo=timezone.utc),
            repeat=Event.REPEAT_DAILY,
        )
        # the grid runs from the 28th of september to the 1st of november,
        # the event starts on the 1st of october: 32 days
        self.assertEqual(self.count_on_the_page(), 32)

    def test_a_weekly_event_repeats_on_the_same_weekday(self):
        Event.objects.create(
            title='Review',
            start=datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc),
            repeat=Event.REPEAT_WEEKLY,
        )
        # the 5th, the 12th, the 19th and the 26th of october
        self.assertEqual(self.count_on_the_page(), 4)

    def test_a_repeating_event_does_not_reach_back_before_its_first_date(self):
        Event.objects.create(
            title='Later',
            start=datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc),
            repeat=Event.REPEAT_DAILY,
        )
        # from the 15th to the 1st of november: 18 days
        self.assertEqual(self.count_on_the_page(), 18)

    def test_an_event_that_does_not_repeat_shows_up_once(self):
        Event.objects.create(
            title='Once',
            start=datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc),
            end=datetime(2026, 10, 5, 10, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(self.count_on_the_page(), 1)


class CalendarClientDataTests(TestCase):
    """The data the client needs to open the dialogs.

    The island used to hold a json *string* instead of the object, so
    `EVENTS[id]` was a single character and every click on an event did
    nothing.
    """

    def setUp(self):
        self.event = Event.objects.create(
            title='Reading group',
            start=datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 10, 2, 11, 0, tzinfo=timezone.utc),
        )

    def test_the_island_holds_the_events_as_an_object(self):
        import json

        response = self.client.get(reverse('calendar'), {'date': '2026-10-20', 'tz': '-330'})
        raw = response.content.decode()
        self.assertIn('id="calendar-events"', raw)
        start = raw.index('id="calendar-events"')
        snippet = raw[start:start + 400]
        payload = snippet[snippet.index('>') + 1:snippet.index('</script>')]
        data = json.loads(payload)
        self.assertIsInstance(data, dict)
        self.assertIn(str(self.event.pk), data)
        self.assertEqual(data[str(self.event.pk)]['title'], 'Reading group')

    def test_the_island_carries_the_local_time(self):
        import json

        response = self.client.get(reverse('calendar'), {'date': '2026-10-20', 'tz': '-330'})
        raw = response.content.decode()
        start = raw.index('id="calendar-events"')
        snippet = raw[start:start + 400]
        payload = snippet[snippet.index('>') + 1:snippet.index('</script>')]
        data = json.loads(payload)
        entry = data[str(self.event.pk)]
        # 10:00 utc is 15:30 in india
        self.assertEqual(entry['start'], '15:30')
        self.assertEqual(entry['date'], '2026-10-02')
        self.assertEqual(entry['repeat'], 'none')

    def test_the_dialog_carries_the_csrf_token(self):
        response = self.client.get(reverse('calendar'), {'date': '2026-10-20'})
        self.assertContains(response, 'csrfmiddlewaretoken')
        self.assertContains(response, 'name="csrf-token"')


class CalendarEventLinkTests(TestCase):
    """Every event can carry a link that opens in a new tab."""

    def setUp(self):
        self.url = reverse('calendar')
        self.create_url = reverse('calendar_event_create')

    def create(self, **extra):
        data = {
            'title': 'Reading group',
            'date': '2026-10-02',
            'start': '10:00',
            'end': '11:00',
            'repeat': 'none',
            'tz': '0',
        }
        data.update(extra)
        return self.client.post(self.create_url, data)

    def test_an_event_can_have_a_link(self):
        response = self.create(url='https://example.org/paper')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Event.objects.get().url, 'https://example.org/paper')

    def test_the_link_is_optional(self):
        self.create()
        self.assertEqual(Event.objects.get().url, '')

    def test_a_javascript_url_is_refused(self):
        response = self.create(url='javascript:alert(1)')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Event.objects.count(), 0)

    def test_a_link_without_a_scheme_is_refused(self):
        response = self.create(url='example.org')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Event.objects.count(), 0)

    def test_an_overlong_link_is_refused(self):
        response = self.create(url='https://example.org/' + 'x' * 600)
        self.assertEqual(response.status_code, 400)

    def test_the_link_can_be_changed(self):
        event = Event.objects.create(
            title='Old',
            start=datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 10, 2, 11, 0, tzinfo=timezone.utc),
        )
        response = self.client.post(reverse('calendar_event_update', args=[event.pk]), {
            'title': 'Old',
            'date': '2026-10-02',
            'start': '10:00',
            'end': '11:00',
            'repeat': 'none',
            'url': 'https://example.org/new',
            'tz': '0',
        })
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.url, 'https://example.org/new')

    def test_the_link_can_be_removed(self):
        event = Event.objects.create(
            title='Old',
            start=datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 10, 2, 11, 0, tzinfo=timezone.utc),
            url='https://example.org/old',
        )
        self.client.post(reverse('calendar_event_update', args=[event.pk]), {
            'title': 'Old',
            'date': '2026-10-02',
            'start': '10:00',
            'end': '11:00',
            'repeat': 'none',
            'url': '',
            'tz': '0',
        })
        event.refresh_from_db()
        self.assertEqual(event.url, '')

    def test_the_link_opens_in_a_new_tab(self):
        Event.objects.create(
            title='Reading group',
            start=datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 10, 2, 11, 0, tzinfo=timezone.utc),
            url='https://example.org/paper',
        )
        response = self.client.get(self.url, {'date': '2026-10-20'})
        self.assertContains(response, 'target="_blank"')
        self.assertContains(response, 'rel="noopener noreferrer"')
        self.assertContains(response, 'https://example.org/paper')
        self.assertContains(response, 'cal-eventlink')

    def test_an_event_without_a_link_has_no_arrow(self):
        Event.objects.create(
            title='Plain',
            start=datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 10, 2, 11, 0, tzinfo=timezone.utc),
        )
        response = self.client.get(self.url, {'date': '2026-10-20'})
        # the class is defined in the css, but no event carries the arrow
        self.assertNotContains(response, '<a class="cal-eventlink"')


class CalendarLinkMarkupTests(TestCase):
    """The arrow of a link and the dialog must not fight over a click."""

    def test_the_link_click_does_not_open_the_dialog(self):
        response = self.client.get(reverse('calendar'), {'date': '2026-10-20'})
        html = response.content.decode()
        self.assertIn("if (e.target.closest('.cal-eventlink')) return;", html)

    def test_the_events_are_focusable(self):
        # the chips became divs, so the keyboard needs its own way in
        Event.objects.create(
            title='Something',
            start=datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 10, 20, 11, 0, tzinfo=timezone.utc),
        )
        response = self.client.get(reverse('calendar'), {'date': '2026-10-20'})
        html = response.content.decode()
        self.assertIn('role="button" tabindex="0"', html)
        self.assertIn("chip.addEventListener('keydown'", html)


class CalendarSaveFeedbackTests(TestCase):
    """A failed save has to say what happened.

    The form used to be posted as a plain form, so a rejected request
    (a stale csrf token, a server error) landed on a bare "Forbidden"
    page with no hint of what to do.
    """

    def test_the_form_is_posted_with_fetch(self):
        response = self.client.get(reverse('calendar'), {'date': '2026-10-20'})
        html = response.content.decode()
        self.assertIn('function submitForm(form)', html)
        self.assertIn("form.addEventListener('submit'", html)
        self.assertIn('response.status === 403', html)
        self.assertIn('This page is out of date', html)
        # the message has to live outside the modal: the site modal closes
        # itself as soon as a button is clicked
        self.assertIn('cal-toast', html)
        self.assertIn("toast.classList.add('show')", html)

    def test_the_hint_is_part_of_the_form(self):
        response = self.client.get(reverse('calendar'), {'date': '2026-10-20'})
        self.assertContains(response, 'id="cal-hint"')
        self.assertContains(response, '.cal-toast')

    def test_the_delete_button_goes_through_the_form(self):
        response = self.client.get(reverse('calendar'), {'date': '2026-10-20'})
        html = response.content.decode()
        self.assertIn('form.requestSubmit()', html)

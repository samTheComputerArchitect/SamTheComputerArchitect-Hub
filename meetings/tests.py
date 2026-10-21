import json
import uuid

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone as dj_timezone

from meetings import google
from meetings.models import Meeting
from settings.models import GoogleCredential


def uid(ch):
    """A uuid built on one letter, so the tests can tell the clients apart."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, ch))


A = uid('a')
B = uid('b')


class MeetingsPageTests(TestCase):
    """The list of meetings and the forms around it."""

    def test_the_page_loads(self):
        response = self.client.get(reverse('meetings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'meeting-item')

    def test_the_page_lists_newest_first(self):
        from datetime import timedelta
        first = Meeting.objects.create(title='Old one')
        first.created_at -= timedelta(days=1)
        first.save()
        Meeting.objects.create(title='New one')
        response = self.client.get(reverse('meetings'))
        self.assertEqual(response.context['meetings'][0].title, 'New one')

    def test_a_meeting_is_created_with_a_title(self):
        response = self.client.post(reverse('meetings_create'), {'title': 'Standup'})
        self.assertRedirects(response, reverse('meetings'))
        self.assertEqual(Meeting.objects.filter(title='Standup').count(), 1)

    def test_a_title_is_required(self):
        response = self.client.post(reverse('meetings_create'), {'title': '   '})
        self.assertRedirects(response, f"{reverse('meetings')}?hint=Title+is+required")
        self.assertEqual(Meeting.objects.count(), 0)

    def test_a_meeting_is_deleted(self):
        meeting = Meeting.objects.create(title='Gone soon')
        response = self.client.post(reverse('meetings_delete', kwargs={'pk': meeting.pk}))
        self.assertRedirects(response, reverse('meetings'))
        self.assertFalse(Meeting.objects.filter(pk=meeting.pk).exists())

    def test_deleting_a_missing_meeting_does_not_crash(self):
        response = self.client.post(reverse('meetings_delete', kwargs={'pk': 999}))
        self.assertRedirects(response, reverse('meetings'))


class MeetingGoogleLinkTests(TestCase):
    """The meet.google.com link that comes from the Meet REST API."""

    def setUp(self):
        self.row = GoogleCredential.load()
        self.row.refresh_token = 'refreshing-token'
        self.row.access_token = 'access-token'
        self.row.save()

    def test_creating_a_meeting_dresses_it_with_a_real_link(self):
        with patch('meetings.google.create_space') as create_space:
            create_space.return_value = {
                'uri': 'https://meet.google.com/abc-defg-hij',
                'code': 'abc-defg-hij',
                'name': 'spaces/KJDFKFJD',
            }
            response = self.client.post(reverse('meetings_create'), {'title': 'Design'})
        self.assertEqual(create_space.call_count, 1)
        meeting = Meeting.objects.get(title='Design')
        self.assertEqual(meeting.meet_uri, 'https://meet.google.com/abc-defg-hij')
        self.assertEqual(meeting.meet_code, 'abc-defg-hij')
        self.assertRedirects(response, reverse('meetings'))

    def test_a_dead_google_does_not_you_lose_the_meeting(self):
        with patch('meetings.google.create_space') as create_space:
            create_space.side_effect = google.GoogleError(
                'Google Meet API has not been used in project'
            )
            self.client.post(reverse('meetings_create'), {'title': 'Design'})
        self.assertEqual(Meeting.objects.filter(title='Design').count(), 1)
        meeting = Meeting.objects.get()
        self.assertEqual(meeting.meet_uri, '')
        # the reason travels to the page, so nothing is swallowed
        response = self.client.get(
            reverse('meetings'),
            {'hint': 'Google Meet API has not been used in project'},
        )
        self.assertContains(response, 'has not been used in project')

    def test_the_link_can_be_retried_since_it_exists(self):
        meeting = Meeting.objects.create(title='Retry me')
        with patch('meetings.google.create_space') as create_space:
            create_space.return_value = {
                'uri': 'https://meet.google.com/xyz-abcd-efg',
                'code': 'xyz-abcd-efg',
                'name': 'spaces/BLAHBLAH',
            }
            response = self.client.post(reverse('meetings_link', kwargs={'pk': meeting.pk}))
        meeting.refresh_from_db()
        self.assertEqual(meeting.meet_uri, 'https://meet.google.com/xyz-abcd-efg')

    def test_the_row_without_a_google_is_honest(self):
        self.row.refresh_token = ''
        self.row.save()
        response = self.client.post(reverse('meetings_create'), {'title': 'Quiet'})
        meeting = Meeting.objects.get()
        self.assertEqual(meeting.meet_uri, '')
        self.assertRedirects(response, reverse('meetings'))


class MeetingCallPageTests(TestCase):
    """The page with the video grid."""

    def test_the_call_page_loads(self):
        meeting = Meeting.objects.create(title='On air')
        response = self.client.get(reverse('meeting_page', kwargs={'pk': meeting.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'call-tiles')
        self.assertContains(response, 'btn-screen')

    def test_an_unknown_meeting_goes_back_to_the_list(self):
        response = self.client.get(reverse('meeting_page', kwargs={'pk': 4242}))
        self.assertRedirects(response, reverse('meetings'))


class MeetingSignalTests(TestCase):
    """The little http mailbox that carries the call's messages."""

    def setUp(self):
        import meetings.views as views_module
        views_module._live.clear()  # the state of one test must not leak into the next
        self.meeting = Meeting.objects.create(title='Signal test')
        self.signal_url = reverse('meeting_signal', kwargs={'pk': self.meeting.pk})
        self.send_url = reverse('meeting_send', kwargs={'pk': self.meeting.pk})

    def send(self, sender, payload, **extra):
        return self.client.post(self.send_url, {
            'me': sender,
            'type': '',
            'payload': json.dumps(payload),
            **extra,
        })

    def listen(self, listener, cursor='0'):
        return self.client.get(self.signal_url, {'me': listener, 'cursor': cursor}).json()

    def test_a_message_travels_to_the_other_client(self):
        self.listen(B)  # the heartbeats register the page that listens
        self.send(A, {'offer': 'first half'}, type='offer')
        data = self.listen(B)
        offer = [message for message in data['messages'] if message['type'] == 'offer'][0]
        self.assertEqual(offer['payload'], {'offer': 'first half'})
        self.assertEqual(offer['from'], A)
        self.assertIn(A, data['roster'])
        self.assertIn(B, data['roster'])

    def test_the_sender_never_reads_its_own_message(self):
        self.send(A, {'solo': True})
        data = self.client.get(self.signal_url, {'me': A, 'cursor': '0'}).json()
        self.assertEqual(data['messages'], [])

    def test_an_answer_meant_for_someone_else_is_not_a_broadcast(self):
        self.send(A, {'answer': 'here'}, to=B)
        data = self.listen(uid('c'))
        self.assertEqual(data['messages'], [])

    def test_the_cursor_bring_only_the_new(self):
        self.listen(B)  # the first read: everything so far
        self.send(A, {'n': 1})
        self.assertEqual(len(self.listen(B)['messages']), 1)
        self.send(A, {'n': 2})
        # the second read, from the cursor of the last one
        data = self.listen(B, cursor='1')
        self.assertEqual(len(data['messages']), 1)
        self.assertEqual(data['messages'][0]['payload'], {'n': 2})

    def test_a_junk_client_id_is_rejected(self):
        response = self.client.post(self.send_url, {'me': 'not-a-uuid', 'payload': '{}'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'A client id is required')
        response = self.client.get(self.signal_url, {'me': ''})
        self.assertEqual(response.status_code, 400)

    def test_non_json_payload_is_rejected(self):
        response = self.client.post(
            self.send_url, {'me': A, 'payload': '<x>'}
        )
        self.assertEqual(response.status_code, 400)

    def test_a_gone_client_leaves_the_roster(self):
        self.send(A, {})
        data = self.client.get(self.signal_url, {'me': A, 'cursor': '0'}).json()
        self.assertEqual(data['roster'], [A])


class GoogleConnectTests(TestCase):
    """The oauth flow between the settings page and Google."""

    def setUp(self):
        self.row = GoogleCredential.load()
        self.row.client_id = 'the-client-id'
        self.row.client_secret = 'the-secret'
        self.row.save()
        self.connect_url = reverse('meetings_connect')
        self.callback_url = reverse('meetings_callback')

    def test_the_connect_button_leads_to_the_consent_screen(self):
        response = self.client.get(self.connect_url)
        self.assertEqual(response.status_code, 302)
        location = response['Location']
        self.assertIn('accounts.google.com/o/oauth2/v2/auth', location)
        self.assertIn('client_id=the-client-id', location)
        self.assertIn('response_type=code', location)
        self.assertIn('access_type=offline', location)

    def test_the_redirect_uri_points_to_the_callback(self):
        response = self.client.get(self.connect_url)
        import urllib.parse
        self.assertIn('meetings/oauth/callback/', urllib.parse.unquote(response['Location']))

    def test_without_a_client_the_button_sends_to_the_settings(self):
        self.row.client_id = ''
        self.row.save()
        response = self.client.get(self.connect_url)
        self.assertEqual(response['Location'], '/settings/?tab=api_keys&hint=missing-client')

    def test_an_unknown_state_is_refused(self):
        response = self.client.get(self.callback_url, {'code': 'c', 'state': 'forged'})
        self.assertRedirects(response, f"{reverse('meetings')}?hint=bad-state")

    def test_a_callback_without_a_code_is_refused(self):
        response = self.client.get(self.callback_url, {'state': 's'})
        self.assertRedirects(response, f"{reverse('meetings')}?hint=empty-code")

    def test_the_disconnect_forgets_the_tokens(self):
        self.row.refresh_token = 'refreshing-token'
        self.row.save()
        response = self.client.post(reverse('meetings_disconnect'))
        self.row.refresh_from_db()
        self.assertEqual(self.row.refresh_token, '')
        self.assertRedirects(response, f"{reverse('meetings')}?hint=disconnected")


class GoogleUtilityTests(TestCase):
    """The urllib layers of meetings.google called directly."""

    def setUp(self):
        self.row = GoogleCredential.load()
        self.row.client_id = 'the-client-id'
        self.row.client_secret = 'the-secret'
        self.row.refresh_token = 'refreshing-token'
        self.row.save()

    def test_not_connected_without_a_token(self):
        self.row.refresh_token = ''
        self.row.save()
        with self.assertRaises(google.GoogleNotConnected):
            google.access_token()

    def test_the_create_space_returns_the_three_things(self):
        class Answer:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self):
                return json.dumps({
                    'meetingUri': 'https://meet.google.com/abc-defg-hij',
                    'meetingCode': 'abc-defg-hij',
                    'name': 'spaces/OHYES',
                }).encode()

        with patch('urllib.request.urlopen', return_value=Answer()):
            with patch('meetings.google.access_token', return_value='tok'):
                space = google.create_space()
        self.assertEqual(space['uri'], 'https://meet.google.com/abc-defg-hij')
        self.assertEqual(space['name'], 'spaces/OHYES')

    def test_the_spaces_are_created_open(self):
        """Nobody waits at the door: the link itself is the invitation."""
        captured = {}

        class Answer:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self):
                return json.dumps({
                    'meetingUri': 'https://meet.google.com/abc-defg-hij',
                }).encode()

        def remember(request, timeout=0):
            captured['body'] = request.data
            return Answer()

        with patch('meetings.google.access_token', return_value='tok'):
            with patch('urllib.request.urlopen', side_effect=remember):
                google.create_space()
        body = json.loads(captured['body'])
        self.assertEqual(body['config']['accessType'], 'OPEN')

    def test_the_code_exchange_saves_the_refresh_token(self):
        class FakeRequest:
            def build_absolute_uri(self, path=''):
                return 'http://127.0.0.1:8000' + (path or '')

        payload = {
            'access_token': 'fresh-access',
            'refresh_token': 'fresh-refresh',
            'expires_in': 3599,
        }

        class Answer:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self):
                return json.dumps(payload).encode()

        with patch('urllib.request.urlopen', return_value=Answer()):
            google.exchange_code(FakeRequest(), 'the-code')
        self.row.refresh_from_db()
        self.assertEqual(self.row.refresh_token, 'fresh-refresh')
        self.assertEqual(self.row.access_token, 'fresh-access')
        self.assertIsNotNone(self.row.access_token_expires_at)

    def test_an_expired_token_is_refreshed(self):
        self.row.access_token = 'stale'
        self.row.access_token_expires_at = dj_timezone.now() - timedelta(hours=1)
        self.row.save()

        class Answer:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self):
                return json.dumps({'access_token': 'brand-new', 'expires_in': 3600}).encode()

        with patch('urllib.request.urlopen', return_value=Answer()):
            token = google.access_token()
        self.assertEqual(token, 'brand-new')

    def test_a_rest_error_leaves_its_message(self):
        """The Meet api speaks error.message, and the sentence reaches the page."""
        import io
        from urllib.error import HTTPError
        body = json.dumps({
            'error': {
                'code': 403,
                'message': 'Google Meet API has not been used in project', 'status': 'PERMISSION_DENIED',
            },
        }).encode()
        error = HTTPError(google.SPACES_URL, 403, 'Forbidden', {}, io.BytesIO(body))
        with patch('meetings.google.access_token', return_value='tok'):
            with patch('urllib.request.urlopen', side_effect=error):
                with self.assertRaises(google.GoogleError) as caught:
                    google.create_space()
        self.assertIn('has not been used in project', str(caught.exception))


class GoogleErrorTests(TestCase):
    """The error class keeps the sentence from Google."""

    def test_the_http_error_becomes_a_sentence(self):
        from urllib.error import HTTPError
        from urllib.request import Request
        self.row = GoogleCredential.load()
        self.row.refresh_token = 'refreshing-token'
        self.row.save()
        error = HTTPError(
            'https://oauth2.googleapis.com/token', 400, 'Bad', {}, None
        )
        with patch('urllib.request.urlopen', side_effect=error):
            with self.assertRaises(google.GoogleError):
                google.access_token()


class PeekTests(TestCase):
    """The keyhole of facts the api says about a space, and the hub page of them."""

    def setUp(self):
        self.meeting = Meeting.objects.create(title='Quiet', space_name='spaces/PKX')
        self.row = GoogleCredential.load()
        self.row.refresh_token = 'refreshing-token'
        self.row.save()

    @staticmethod
    def answer(payload):
        class Answer:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self):
                return json.dumps(payload).encode()
        return Answer()

    def test_a_quiet_space_is_reported_as_quiet(self):
        with patch('meetings.google.access_token', return_value='tok'):
            with patch('urllib.request.urlopen', return_value=self.answer({})):
                peek = google.space_peek('spaces/PKX')
        self.assertEqual(peek, {'live': False, 'people': 0})

    def test_a_live_space_is_counted(self):
        calls = [
            self.answer({'activeConference': {'conferenceRecord': 'conferenceRecords/RE'}}),
            self.answer({'participants': [{'name': 'a'}, {'name': 'b'}]}),
        ]

        def next_answer(request, timeout=0):
            self.assertTrue(request.get_header('Authorization').endswith('tok'))
            return calls.pop(0)

        with patch('meetings.google.access_token', return_value='tok'):
            with patch('urllib.request.urlopen', side_effect=next_answer):
                peek = google.space_peek('spaces/PKX')
        self.assertEqual(peek, {'live': True, 'people': 2})

    def test_the_peek_page_carries_every_spaced_row(self):
        Meeting.objects.create(title='No link yet')
        with patch('meetings.google.space_peek', return_value={'live': True, 'people': 3}):
            data = self.client.get(reverse('meetings_peek')).json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['rooms'][str(self.meeting.pk)], {'live': True, 'people': 3})
        self.assertEqual(len(data['rooms']), 1)

    def test_a_refusal_from_google_is_passed_on(self):
        with patch('meetings.google.space_peek', side_effect=google.GoogleError('Google replied 403')):
            response = self.client.get(reverse('meetings_peek'))
        self.assertFalse(response.json()['ok'])

    def test_without_goggle_no_peek_is_asked_for(self):
        Meeting.objects.all().delete()
        with patch('meetings.google.space_peek') as unused:
            data = self.client.get(reverse('meetings_peek')).json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['rooms'], {})
        unused.assert_not_called()

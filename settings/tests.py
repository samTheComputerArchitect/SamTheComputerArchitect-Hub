from django.test import TestCase
from django.urls import reverse

from .models import APIKey, EditorSetting, GoogleCredential


class ApiKeyTests(TestCase):
    """Regression tests for the settings app hardening."""

    def test_save_api_key_strips_whitespace(self):
        response = self.client.post(reverse('save_api_key'), {
            'provider': '  OllamaCloud ', 'key': ' key-with-spaces ',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(APIKey.objects.count(), 1)
        stored = APIKey.objects.get()
        self.assertEqual(stored.provider, 'OllamaCloud')
        self.assertEqual(stored.key, 'key-with-spaces')

    def test_save_api_key_updates_existing_provider(self):
        self.client.post(reverse('save_api_key'), {'provider': 'OllamaCloud', 'key': 'one'})
        self.client.post(reverse('save_api_key'), {'provider': 'OllamaCloud', 'key': 'two'})
        self.assertEqual(APIKey.objects.count(), 1)
        self.assertEqual(APIKey.objects.get().key, 'two')

    def test_save_api_key_requires_both_fields(self):
        response = self.client.post(reverse('save_api_key'), {'provider': ' '})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(APIKey.objects.count(), 0)

    def test_save_api_key_rejects_oversized_key(self):
        response = self.client.post(reverse('save_api_key'), {
            'provider': 'OllamaCloud', 'key': 'k' * 501,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'API key is too long')
        self.assertEqual(APIKey.objects.count(), 0)

    def test_save_api_key_rejects_get(self):
        response = self.client.get(reverse('save_api_key'))
        self.assertEqual(response.status_code, 405)

    def test_get_api_keys_returns_json(self):
        self.client.post(reverse('save_api_key'), {'provider': 'OllamaCloud', 'key': 'test-key'})
        response = self.client.get(reverse('get_api_keys'))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]['provider'], 'OllamaCloud')

    def test_settings_page_does_not_store_keys_in_dom_attributes(self):
        self.client.post(reverse('save_api_key'), {'provider': 'OllamaCloud', 'key': 'supersecret'})
        response = self.client.get(reverse('settings'))
        self.assertEqual(response.status_code, 200)
        # The cleartext key must not be serialised into data-* attributes;
        # the field value is the one and only copy on the page.
        self.assertNotIn('dataset.realValue', response.content.decode())

    def test_settings_falls_back_to_api_keys_tab_for_unknown_tab(self):
        response = self.client.get(reverse('settings'), {'tab': 'garbage'})
        self.assertEqual(response.status_code, 200)
        # Both tab sections used to stay display:none for unknown tabs,
        # rendering a blank page instead of the default tab.
        self.assertContains(response, 'id="api_keys" class="tab-content active"')
        self.assertNotContains(response, 'id="models" class="tab-content active"')


class EditorSettingTests(TestCase):
    """The paper editor's vim toggles live here and keep their state until
    the user changes them."""

    def test_the_editor_tab_is_a_valid_tab(self):
        response = self.client.get(reverse('settings'), {'tab': 'editor'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="editor" class="tab-content active"')
        self.assertContains(response, 'setting-vim')
        self.assertContains(response, 'setting-hjkl')

    def test_the_editor_settings_default_to_vim_on(self):
        payload = self.client.get(reverse('get_editor_settings')).json()
        self.assertEqual(payload, {'vim': True, 'hjkl': True})

    def test_saving_the_editor_settings_roundtrip_through_the_defaults(self):
        response = self.client.post(reverse('save_editor_settings'), {
            'vim': 'true', 'hjkl': 'false',
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['vim'], True)
        self.assertEqual(payload['hjkl'], False)
        stored = EditorSetting.load()
        self.assertTrue(stored.vim_mode)
        self.assertFalse(stored.keep_hjkl)

    def test_saving_without_a_value_turns_the_toggle_off(self):
        response = self.client.post(reverse('save_editor_settings'), {'hjkl': 'false'})
        self.assertEqual(response.status_code, 200)
        stored = EditorSetting.load()
        self.assertFalse(stored.vim_mode)
        self.assertFalse(stored.keep_hjkl)

    def test_saving_the_editor_settings_requires_post(self):
        self.assertEqual(self.client.get(reverse('save_editor_settings')).status_code, 405)
        self.assertEqual(self.client.post(reverse('save_api_key'), {'provider': 'X', 'key': 'k'}).status_code, 200)


class GoogleClientTests(TestCase):
    """The oauth client of the hub saved on the settings page."""

    def test_saving_the_client_stores_both_parts(self):
        response = self.client.post(reverse('save_google_client'), {
            'client_id': '123.apps.googleusercontent.com',
            'client_secret': 'GOCSPX-secret',
        })
        self.assertEqual(response.json()['status'], 'success')
        row = GoogleCredential.objects.get()
        self.assertEqual(row.client_id, '123.apps.googleusercontent.com')
        self.assertEqual(row.client_secret, 'GOCSPX-secret')

    def test_saving_the_client_overwrites_the_old_one(self):
        self.client.post(reverse('save_google_client'), {
            'client_id': 'a.apps.googleusercontent.com', 'client_secret': 'one',
        })
        self.client.post(reverse('save_google_client'), {
            'client_id': 'b.apps.googleusercontent.com', 'client_secret': 'two',
        })
        self.assertEqual(GoogleCredential.objects.count(), 1)
        self.assertTrue(GoogleCredential.objects.get().client_id.startswith('b'))

    def test_both_fields_are_required(self):
        response = self.client.post(
            reverse('save_google_client'), {'client_id': 'only-the-id'}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error'], 'The client id and the secret are both required')

    def test_the_status_reports_what_is_stored(self):
        response = self.client.get(reverse('get_google_status'))
        self.assertEqual(response.json(), {
            'client_id': False, 'client_secret': False, 'connected': False,
        })
        GoogleCredential.load()
        response = self.client.post(reverse('save_google_client'), {
            'client_id': 'a.apps.googleusercontent.com', 'client_secret': 'one',
        })
        response = self.client.get(reverse('get_google_status'))
        self.assertTrue(response.json()['client_id'])
        row = GoogleCredential.objects.get()
        row.refresh_token = 'connected-token'
        row.save()
        self.assertTrue(self.client.get(reverse('get_google_status')).json()['connected'])

    def test_the_saving_requires_post(self):
        self.assertEqual(self.client.get(reverse('save_google_client')).status_code, 405)

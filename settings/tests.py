from django.test import TestCase
from django.urls import reverse

from .models import APIKey, EditorSetting


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

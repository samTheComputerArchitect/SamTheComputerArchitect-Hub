import os

from django.conf import settings
from django.test import TestCase


class FaviconTests(TestCase):
    """The logo is the favicon of every page.

    The browser shows the icon at 16-32 px, so the shipped file is a
    downscaled copy of the logo - the full size one is 218 KB and would
    be downloaded for nothing.
    """

    def test_every_page_links_the_favicon(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'rel="icon"')
        self.assertContains(response, '/static/favicon.png')
        self.assertContains(response, 'rel="apple-touch-icon"')

    def test_the_icon_files_are_there(self):
        static_root = os.path.join(settings.BASE_DIR, 'static')
        for name in ('favicon.png', 'apple-touch-icon.png'):
            path = os.path.join(static_root, name)
            self.assertTrue(os.path.exists(path), f'{name} is missing')
            self.assertGreater(os.path.getsize(path), 0)

    def test_the_favicon_is_the_logo(self):
        from PIL import Image

        static_root = os.path.join(settings.BASE_DIR, 'static')
        logo = Image.open(os.path.join(static_root, 'Logo.png')).convert('RGBA')
        icon = Image.open(os.path.join(static_root, 'favicon.png')).convert('RGBA')
        self.assertEqual(icon.size, (64, 64))
        # the same picture, only smaller
        resized = logo.resize(icon.size, Image.LANCZOS)
        self.assertEqual(
            list(icon.getdata())[:64],
            list(resized.getdata())[:64],
        )

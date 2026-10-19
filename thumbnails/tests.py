import io
import json
import os
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Thumbnail, ThumbnailElement


class TempMediaRootMixin:
    """Keep the test uploads out of the real media folder."""

    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp(prefix='hub-test-media-')
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)


def png_bytes():
    """Smallest valid PNG that Pillow can open."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new('RGB', (64, 32), (120, 80, 40)).save(buffer, format='PNG')
    return buffer.getvalue()


class ThumbnailViewTests(TempMediaRootMixin, TestCase):
    def setUp(self):
        self.thumb = Thumbnail.objects.create(name='Original', background_color='#112233')

    def post(self, url, data=None, **kwargs):
        return self.client.post(url, data or {}, **kwargs)

    # ------------------------------------------------------------------ CRUD
    def test_create_thumbnail(self):
        response = self.post(reverse('create_thumbnail'), {'name': 'Fresh'})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(Thumbnail.objects.filter(name='Fresh').exists())
        self.assertIn(str(payload['id']), payload['url'])

    def test_create_thumbnail_requires_a_name(self):
        response = self.post(reverse('create_thumbnail'), {'name': '   '})
        self.assertEqual(response.status_code, 400)

    def test_rename_thumbnail(self):
        response = self.post(reverse('rename_thumbnail'), {'id': self.thumb.pk, 'name': 'Renamed'})
        self.assertEqual(response.status_code, 200)
        self.thumb.refresh_from_db()
        self.assertEqual(self.thumb.name, 'Renamed')

    def test_rename_unknown_thumbnail(self):
        response = self.post(reverse('rename_thumbnail'), {'id': 999999, 'name': 'Nope'})
        self.assertEqual(response.status_code, 404)

    def test_delete_thumbnail(self):
        response = self.post(reverse('delete_thumbnail'), {'id': self.thumb.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Thumbnail.objects.filter(pk=self.thumb.pk).exists())

    def test_duplicate_thumbnail_copies_background_and_elements(self):
        element = ThumbnailElement.objects.create(
            thumbnail=self.thumb,
            kind=ThumbnailElement.KIND_SHAPE,
            shape='rectangle',
            x=10,
            y=20,
            width=100,
            height=50,
            z_index=3,
        )
        response = self.post(reverse('duplicate_thumbnail'), {'id': self.thumb.pk})
        self.assertEqual(response.status_code, 200)
        duplicate = Thumbnail.objects.exclude(pk=self.thumb.pk).get()
        self.assertEqual(duplicate.background_color, '#112233')
        copied = duplicate.elements.get()
        self.assertEqual(copied.shape, 'rectangle')
        self.assertEqual(copied.x, element.x)
        self.assertEqual(copied.z_index, element.z_index)

    def test_background_update(self):
        response = self.post(
            reverse('background_update'),
            {'thumbnail': self.thumb.pk, 'background_color': '#abcdef'},
        )
        self.assertEqual(response.status_code, 200)
        self.thumb.refresh_from_db()
        self.assertEqual(self.thumb.background_color, '#abcdef')

    def test_background_update_rejects_invalid_color(self):
        response = self.post(
            reverse('background_update'),
            {'thumbnail': self.thumb.pk, 'background_color': 'red; background:url(x)'},
        )
        self.assertEqual(response.status_code, 400)

    def test_background_update_rejects_broken_hex(self):
        response = self.post(
            reverse('background_update'),
            {'thumbnail': self.thumb.pk, 'background_color': '#fffff'},
        )
        self.assertEqual(response.status_code, 400)

    def test_editor_redirects_for_missing_thumbnail(self):
        response = self.client.get(reverse('thumbnail_editor', args=[999999]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('thumbnails'))

    # --------------------------------------------------------------- elements
    def test_create_text_element(self):
        response = self.post(
            reverse('element_create'),
            {
                'thumbnail': self.thumb.pk,
                'kind': 'text',
                'text': 'Hello',
                'x': 100,
                'y': 200,
                'width': 300,
                'font_size': 64,
                'align': 'center',
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['text'], 'Hello')
        self.assertEqual(payload['x'], 100)
        self.assertEqual(payload['align'], 'center')
        # the first element of a thumbnail gets the first free layer slot
        self.assertEqual(payload['z'], 1)

    def test_create_text_element_requires_text(self):
        response = self.post(
            reverse('element_create'),
            {'thumbnail': self.thumb.pk, 'kind': 'text', 'text': '  '},
        )
        self.assertEqual(response.status_code, 400)

    def test_create_shape_uses_per_shape_default_size(self):
        response = self.post(
            reverse('element_create'),
            {'thumbnail': self.thumb.pk, 'kind': 'shape', 'shape': 'line'},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['width'], 400)
        self.assertEqual(payload['height'], 6)

    def test_create_shape_keeps_requested_size(self):
        response = self.post(
            reverse('element_create'),
            {
                'thumbnail': self.thumb.pk,
                'kind': 'shape',
                'shape': 'square',
                'width': '180',
                'height': '180',
            },
        )
        payload = response.json()
        self.assertEqual(payload['width'], 180)
        self.assertEqual(payload['height'], 180)

    def test_create_element_rejects_invalid_color(self):
        response = self.post(
            reverse('element_create'),
            {
                'thumbnail': self.thumb.pk,
                'kind': 'shape',
                'shape': 'rectangle',
                'color': '"><script>alert(1)</script>',
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertNotIn('<script>', payload['color'])
        self.assertEqual(payload['color'], '#5294e2')

    def test_create_element_accepts_transparent_fill(self):
        response = self.post(
            reverse('element_create'),
            {
                'thumbnail': self.thumb.pk,
                'kind': 'shape',
                'shape': 'rectangle',
                'color': 'transparent',
            },
        )
        self.assertEqual(response.json()['color'], 'transparent')

    def test_create_image_element_scales_to_canvas(self):
        upload = SimpleUploadedFile('shot.png', png_bytes(), content_type='image/png')
        response = self.post(
            reverse('element_create'),
            {'thumbnail': self.thumb.pk, 'kind': 'image', 'image': upload},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['width'], 64)
        self.assertEqual(payload['height'], 32)
        self.assertTrue(payload['image_url'])

    def test_create_image_element_survives_unreadable_file(self):
        """A corrupt upload must not raise a ZeroDivisionError."""
        upload = SimpleUploadedFile('broken.png', b'not an image', content_type='image/png')
        response = self.post(
            reverse('element_create'),
            {'thumbnail': self.thumb.pk, 'kind': 'image', 'image': upload},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreater(payload['width'], 0)
        self.assertGreater(payload['height'], 0)

    def test_create_element_with_explicit_id(self):
        response = self.post(
            reverse('element_create'),
            {'thumbnail': self.thumb.pk, 'kind': 'text', 'text': 'Restored', 'id': '4242'},
        )
        self.assertEqual(response.json()['id'], 4242)

    def test_create_element_does_not_steal_an_existing_id(self):
        existing = ThumbnailElement.objects.create(
            thumbnail=self.thumb, kind=ThumbnailElement.KIND_TEXT, text='Original'
        )
        response = self.post(
            reverse('element_create'),
            {'thumbnail': self.thumb.pk, 'kind': 'text', 'text': 'New', 'id': str(existing.pk)},
        )
        self.assertNotEqual(response.json()['id'], existing.pk)
        existing.refresh_from_db()
        self.assertEqual(existing.text, 'Original')

    def test_update_element(self):
        element = ThumbnailElement.objects.create(
            thumbnail=self.thumb, kind=ThumbnailElement.KIND_TEXT, text='Before'
        )
        response = self.post(
            reverse('element_update'),
            {'id': element.pk, 'text': 'After', 'x': 42, 'z': 7},
        )
        self.assertEqual(response.status_code, 200)
        element.refresh_from_db()
        self.assertEqual(element.text, 'After')
        self.assertEqual(element.x, 42)
        self.assertEqual(element.z_index, 7)

    def test_update_unknown_element(self):
        response = self.post(reverse('element_update'), {'id': 999999, 'x': 5})
        self.assertEqual(response.status_code, 404)

    def test_update_element_rejects_invalid_color(self):
        element = ThumbnailElement.objects.create(
            thumbnail=self.thumb, kind=ThumbnailElement.KIND_SHAPE, color='#111111'
        )
        response = self.post(
            reverse('element_update'),
            {'id': element.pk, 'color': '</style><script>alert(1)</script>'},
        )
        self.assertEqual(response.status_code, 400)
        element.refresh_from_db()
        self.assertEqual(element.color, '#111111')

    def test_update_element_cannot_touch_another_thumbnail(self):
        other = Thumbnail.objects.create(name='Other')
        element = ThumbnailElement.objects.create(
            thumbnail=other, kind=ThumbnailElement.KIND_TEXT, text='Other text'
        )
        response = self.post(
            reverse('element_update'),
            {'id': element.pk, 'thumbnail': self.thumb.pk, 'text': 'Hijacked'},
        )
        self.assertEqual(response.status_code, 404)
        element.refresh_from_db()
        self.assertEqual(element.text, 'Other text')

    def test_delete_element(self):
        element = ThumbnailElement.objects.create(
            thumbnail=self.thumb, kind=ThumbnailElement.KIND_TEXT, text='Bye'
        )
        response = self.post(reverse('element_delete'), {'id': element.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ThumbnailElement.objects.filter(pk=element.pk).exists())

    def test_endpoints_reject_get(self):
        for name in ('create_thumbnail', 'rename_thumbnail', 'delete_thumbnail',
                     'duplicate_thumbnail', 'element_create', 'element_update',
                     'element_delete', 'background_update'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 405, name)

    def test_editor_page_renders_elements_as_json(self):
        ThumbnailElement.objects.create(
            thumbnail=self.thumb, kind=ThumbnailElement.KIND_TEXT, text='Visible'
        )
        response = self.client.get(reverse('thumbnail_editor', args=[self.thumb.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'elements-data')
        self.assertContains(response, 'Visible')

    def test_thumbnail_list_exposes_preview(self):
        ThumbnailElement.objects.create(
            thumbnail=self.thumb,
            kind=ThumbnailElement.KIND_IMAGE,
            image=SimpleUploadedFile('shot.png', png_bytes(), content_type='image/png'),
        )
        response = self.client.get(reverse('thumbnails'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'thumbnail_elements')


class ElementFileTests(TempMediaRootMixin, TestCase):
    def test_deleting_an_element_keeps_a_file_another_element_uses(self):
        thumb = Thumbnail.objects.create(name='Shared')
        upload = SimpleUploadedFile('shared.png', b'shared bytes', content_type='image/png')
        first = ThumbnailElement.objects.create(
            thumbnail=thumb, kind=ThumbnailElement.KIND_IMAGE, image=upload
        )
        second = ThumbnailElement.objects.create(
            thumbnail=thumb, kind=ThumbnailElement.KIND_IMAGE, image=first.image.name
        )
        path = first.image.path
        first.delete()
        self.assertTrue(os.path.exists(path), 'the file was removed while another element still uses it')
        second.refresh_from_db()
        self.assertTrue(os.path.exists(second.image.path))

    def test_deleting_the_last_element_removes_the_file(self):
        thumb = Thumbnail.objects.create(name='Lonely')
        upload = SimpleUploadedFile('lonely.png', b'bytes', content_type='image/png')
        element = ThumbnailElement.objects.create(
            thumbnail=thumb, kind=ThumbnailElement.KIND_IMAGE, image=upload
        )
        path = element.image.path
        element.delete()
        self.assertFalse(os.path.exists(path))

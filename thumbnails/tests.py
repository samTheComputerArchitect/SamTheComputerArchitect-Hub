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


class PkGuardTests(TempMediaRootMixin, TestCase):
    """Non-numeric ids must answer 404/400 JSON, not raise ValueError (500).

    Audit regression tests: every POST endpoint used to look the row up
    with the raw form string, which crashes with
    "ValueError: Field 'id' expected a number" for any junk value.
    """

    def setUp(self):
        self.thumb = Thumbnail.objects.create(name='Guarded')

    def post(self, url_name, data):
        return self.client.post(reverse(url_name), data)

    def test_rename_rejects_garbage_id(self):
        response = self.post('rename_thumbnail', {'id': 'zzz', 'name': 'X'})
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Thumbnail.objects.filter(pk=self.thumb.pk).exists())

    def test_background_rejects_garbage_id(self):
        response = self.post('background_update', {'id': 'zzz', 'background_color': '#101010'})
        self.assertEqual(response.status_code, 404)
        self.thumb.refresh_from_db()
        self.assertEqual(self.thumb.background_color, '#ffffff')

    def test_background_accepts_thumbnail_field_for_backward_compat(self):
        response = self.post('background_update', {
            'thumbnail': self.thumb.pk, 'background_color': '#101010',
        })
        self.assertEqual(response.status_code, 200)
        self.thumb.refresh_from_db()
        self.assertEqual(self.thumb.background_color, '#101010')

    def test_delete_rejects_garbage_id(self):
        response = self.post('delete_thumbnail', {'id': 'zzz'})
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Thumbnail.objects.filter(pk=self.thumb.pk).exists())

    def test_duplicate_rejects_garbage_id(self):
        response = self.post('duplicate_thumbnail', {'id': 'zzz'})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Thumbnail.objects.count(), 1)

    def test_element_create_rejects_garbage_thumbnail(self):
        response = self.post('element_create', {'thumbnail': 'zzz', 'kind': 'text', 'text': 'o'})
        self.assertEqual(response.status_code, 404)

    def test_element_update_rejects_garbage_id(self):
        response = self.post('element_update', {'id': 'zzz', 'width': 40})
        self.assertEqual(response.status_code, 404)

    def test_element_update_rejects_garbage_thumbnail_filter(self):
        upload = SimpleUploadedFile('g.png', png_bytes(), content_type='image/png')
        element = ThumbnailElement.objects.create(
            thumbnail=self.thumb, kind=ThumbnailElement.KIND_IMAGE, image=upload
        )
        response = self.post('element_update', {'id': element.pk, 'thumbnail': 'zzz', 'width': 40})
        self.assertEqual(response.status_code, 404)
        response = self.post('element_delete', {'id': element.pk, 'thumbnail': 'zzz'})
        self.assertEqual(response.status_code, 404)
        element.refresh_from_db()
        self.assertEqual(element.width, 200)

    def test_element_update_accepts_valid_thumbnail_filter(self):
        upload = SimpleUploadedFile('g.png', png_bytes(), content_type='image/png')
        element = ThumbnailElement.objects.create(
            thumbnail=self.thumb, kind=ThumbnailElement.KIND_IMAGE, image=upload
        )
        response = self.post('element_update', {
            'id': element.pk, 'thumbnail': self.thumb.pk, 'width': 55,
        })
        self.assertEqual(response.status_code, 200)
        element.refresh_from_db()
        self.assertEqual(element.width, 55)

    def test_element_delete_rejects_garbage_id(self):
        response = self.post('element_delete', {'id': 'zzz'})
        self.assertEqual(response.status_code, 404)

    def test_endpoints_still_work_with_numeric_ids(self):
        response = self.post('rename_thumbnail', {'id': self.thumb.pk, 'name': 'Renamed'})
        self.assertEqual(response.status_code, 200)
        response = self.post('delete_thumbnail', {'id': self.thumb.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Thumbnail.objects.count(), 0)

    def test_rename_rejects_empty_name(self):
        response = self.post('rename_thumbnail', {'id': self.thumb.pk, 'name': '   '})
        self.assertEqual(response.status_code, 400)
        self.thumb.refresh_from_db()
        self.assertEqual(self.thumb.name, 'Guarded')


class GalleryPreviewTests(TempMediaRootMixin, TestCase):
    """The gallery used to run one elements query per card (N+1) just to
    pick a preview image; the view now fetches the topmost image for all
    thumbnails in a single query and keeps the same pick order."""

    def setUp(self):
        self.thumb = Thumbnail.objects.create(name='Gallery')

    def test_query_count_is_bounded(self):
        for i in range(4):
            Thumbnail.objects.create(name=f'T{i}')
        with self.assertNumQueries(2):
            self.assertEqual(self.client.get(reverse('thumbnails')).status_code, 200)

    def test_topmost_image_is_picked_as_preview(self):
        upload = SimpleUploadedFile('a.png', png_bytes(), content_type='image/png')
        image = ThumbnailElement.objects.create(
            thumbnail=self.thumb,
            kind=ThumbnailElement.KIND_IMAGE,
            image=upload,
            z_index=7,
        )
        response = self.client.get(reverse('thumbnails'))
        self.assertContains(response, image.image.url)

    def test_text_only_thumbnail_shows_no_preview(self):
        ThumbnailElement.objects.create(
            thumbnail=self.thumb, kind=ThumbnailElement.KIND_TEXT, text='hi'
        )
        response = self.client.get(reverse('thumbnails'))
        self.assertContains(response, 'Empty thumbnail')


class NumericGuardTests(TempMediaRootMixin, TestCase):
    """Round two: the number parsers must survive hostile values.

    `int(float('inf'))` raises OverflowError, and `float('nan')` poisons
    every comparison that follows it - both reached the database through
    the element endpoints and turned into HTTP 500s or NaN geometry.
    """

    def setUp(self):
        self.thumb = Thumbnail.objects.create(name='Numbers')

    def create_element(self, **data):
        payload = {'thumbnail': self.thumb.pk, 'kind': 'text', 'text': 'hello'}
        payload.update(data)
        return self.client.post(reverse('element_create'), payload)

    def test_an_infinite_brightness_does_not_crash_the_create(self):
        response = self.create_element(brightness='inf')
        self.assertEqual(response.status_code, 200)
        element = ThumbnailElement.objects.get(pk=response.json()['id'])
        self.assertTrue(-1e9 < element.brightness < 1e9)

    def test_an_infinite_brightness_does_not_crash_the_update(self):
        element = ThumbnailElement.objects.create(
            thumbnail=self.thumb, kind=ThumbnailElement.KIND_TEXT, text='x',
        )
        response = self.client.post(
            reverse('element_update'),
            {'id': element.pk, 'brightness': '1e400'},
        )
        self.assertEqual(response.status_code, 200)

    def test_nan_geometry_is_never_stored(self):
        response = self.create_element(width='nan', height='nan', x='nan', y='nan')
        self.assertEqual(response.status_code, 200)
        element = ThumbnailElement.objects.get(pk=response.json()['id'])
        for value in (element.width, element.height, element.x, element.y):
            self.assertEqual(value, value)  # not NaN
            self.assertNotEqual(str(value), 'nan')

    def test_infinite_geometry_is_never_stored(self):
        response = self.create_element(width='inf', opacity='inf', rotation='-inf')
        self.assertEqual(response.status_code, 200)
        element = ThumbnailElement.objects.get(pk=response.json()['id'])
        self.assertLessEqual(element.width, 20000)
        self.assertGreaterEqual(element.opacity, 0)
        self.assertLessEqual(element.opacity, 1)

    def test_nan_geometry_is_rejected_on_update(self):
        element = ThumbnailElement.objects.create(
            thumbnail=self.thumb, kind=ThumbnailElement.KIND_TEXT, text='x',
        )
        response = self.client.post(
            reverse('element_update'), {'id': element.pk, 'width': 'nan'},
        )
        self.assertEqual(response.status_code, 200)
        element.refresh_from_db()
        self.assertNotEqual(str(element.width), 'nan')

    def test_an_oversized_element_text_is_rejected(self):
        response = self.create_element(text='x' * 2001)
        self.assertEqual(response.status_code, 400)
        self.assertIn('too long', response.json()['error'])

    def test_an_oversized_element_text_is_rejected_on_update(self):
        element = ThumbnailElement.objects.create(
            thumbnail=self.thumb, kind=ThumbnailElement.KIND_TEXT, text='x',
        )
        response = self.client.post(
            reverse('element_update'), {'id': element.pk, 'text': 'y' * 5000},
        )
        self.assertEqual(response.status_code, 400)
        element.refresh_from_db()
        self.assertEqual(element.text, 'x')

    def test_the_font_size_is_clamped_on_create(self):
        response = self.create_element(font_size='100000')
        self.assertEqual(response.status_code, 200)
        element = ThumbnailElement.objects.get(pk=response.json()['id'])
        self.assertLessEqual(element.font_size, 400)

    def test_a_huge_width_is_clamped_on_create(self):
        response = self.create_element(width='999999999')
        self.assertEqual(response.status_code, 200)
        element = ThumbnailElement.objects.get(pk=response.json()['id'])
        self.assertLessEqual(element.width, 20000)

    def test_a_huge_width_is_clamped_on_update(self):
        element = ThumbnailElement.objects.create(
            thumbnail=self.thumb, kind=ThumbnailElement.KIND_TEXT, text='x',
        )
        response = self.client.post(
            reverse('element_update'), {'id': element.pk, 'width': '999999999'},
        )
        self.assertEqual(response.status_code, 200)
        element.refresh_from_db()
        self.assertLessEqual(element.width, 20000)


class EditorClientGuardTests(TempMediaRootMixin, TestCase):
    """Round two: the editor may not show a name the server refused."""

    def setUp(self):
        self.thumb = Thumbnail.objects.create(name='Client')

    def test_a_refused_rename_puts_the_old_name_back(self):
        response = self.client.get(
            reverse('thumbnail_editor', args=[self.thumb.pk]),
        )
        html = response.content.decode()
        self.assertIn('post(RENAME_URL', html)
        self.assertIn('nameEl.textContent = original', html)


class EditorClientGuardTests2(TempMediaRootMixin, TestCase):
    """Round two: the editor client must survive a non-json answer."""

    def setUp(self):
        self.thumb = Thumbnail.objects.create(name='Guard2')

    def editor_html(self):
        response = self.client.get(reverse('thumbnail_editor', args=[self.thumb.pk]))
        return response.content.decode()

    def test_the_post_helpers_parse_the_body_defensively(self):
        html = self.editor_html()
        self.assertIn('JSON.parse(text)', html)
        self.assertNotIn('return response.json().then(function (data) {', html)

    def test_the_number_fields_are_clamped_to_their_range(self):
        html = self.editor_html()
        self.assertIn('const clamp = function (value) {', html)
        self.assertIn('MAX_ELEMENT_SIZE = 20000', html)
        self.assertIn('MAX_ELEMENT_TEXT = 2000', html)

    def test_bring_to_front_takes_a_free_slot(self):
        html = self.editor_html()
        self.assertIn('const target = nextZ();', html)

    def test_the_gallery_cards_can_be_opened_with_the_keyboard(self):
        response = self.client.get(reverse('thumbnails'))
        html = response.content.decode()
        self.assertIn('tabindex="0"', html)
        self.assertIn("e.key !== 'Enter' && e.key !== ' '", html)

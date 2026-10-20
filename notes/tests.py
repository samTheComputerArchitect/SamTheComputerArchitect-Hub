from django.test import TestCase
from django.urls import reverse

from .models import CanvasImage, Drawing, Note, Notebook, Section, Tab


def post(url_name, data):
    return {
        'method': 'post',
        'url': reverse(url_name),
        'data': data,
    }


class NotesApiGuardTests(TestCase):
    """The notes endpoints must survive non-numeric ids and numbers.

    Every lookup used to hand raw form strings to .filter(pk=...), which
    raises ValueError (-> HTTP 500) for junk ids; numeric fields crashed the
    same way when a client shipped a malformed float. Regression tests for
    the 2026-10 bug audit.
    """

    def setUp(self):
        self.notebook = Notebook.objects.create(name='Hub')
        self.section = Section.objects.create(notebook=self.notebook, name='Work')
        self.tab = Tab.objects.create(section=self.section, name='Ideas')

    def post(self, url_name, data):
        return self.client.post(reverse(url_name), data)

    # ------------------------------------------------------- page (GET)
    def test_notes_page_survives_garbage_notebook(self):
        response = self.client.get(reverse('notes'), {'notebook': 'zzz'})
        self.assertEqual(response.status_code, 200)

    def test_notes_page_survives_garbage_section(self):
        response = self.client.get(
            reverse('notes'), {'notebook': self.notebook.pk, 'section': 'zzz'}
        )
        self.assertEqual(response.status_code, 200)

    def test_notes_page_survives_garbage_tab(self):
        response = self.client.get(
            reverse('notes'),
            {
                'notebook': self.notebook.pk,
                'section': self.section.pk,
                'tab': 'zzz',
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_notes_page_filters_still_select_the_requested_tab(self):
        response = self.client.get(
            reverse('notes'), {'notebook': self.notebook.pk, 'tab': self.tab.pk}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_tab'], self.tab)

    # ------------------------------------------------------------- notes
    def test_save_note_updates_kind_on_existing_note(self):
        note = Note.objects.create(tab=self.tab, kind=Note.KIND_NOTE, text='Alpha')
        response = self.post('save_note', {
            'id': note.pk, 'kind': 'h2', 'text': 'Alpha', 'x': 5, 'y': 6,
        })
        self.assertEqual(response.status_code, 200)
        note.refresh_from_db()
        self.assertEqual(note.kind, 'h2')

    def test_save_note_downgrades_unknown_kind(self):
        note = Note.objects.create(tab=self.tab, kind=Note.KIND_NOTE, text='Beta')
        response = self.post('save_note', {
            'id': note.pk, 'kind': 'evil', 'text': 'Beta', 'x': 1, 'y': 1,
        })
        self.assertEqual(response.status_code, 200)
        note.refresh_from_db()
        self.assertEqual(note.kind, Note.KIND_NOTE)

    def test_save_note_with_garbage_id_is_404_not_500(self):
        response = self.post('save_note', {'id': 'zzz', 'text': 'x'})
        self.assertEqual(response.status_code, 404)

    def test_save_note_keeps_working_without_id(self):
        response = self.post('save_note', {'tab': self.tab.pk, 'text': 'Gamma'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Note.objects.filter(text='Gamma').exists())

    def test_delete_note_with_garbage_id_oks_and_deletes_nothing(self):
        note = Note.objects.create(tab=self.tab, text='Keep me')
        response = self.post('delete_note', {'id': 'not-a-number'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Note.objects.filter(pk=note.pk).exists())

    def test_delete_note_still_deletes(self):
        note = Note.objects.create(tab=self.tab, text='Bye')
        response = self.post('delete_note', {'id': note.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Note.objects.filter(pk=note.pk).exists())

    # ---------------------------------------------------------- sections
    def test_create_section_with_missing_notebook_redirects_home(self):
        response = self.post('create_section', {'notebook': 'zzz', 'name': 'S'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('notes'))

    def test_create_section_still_creates_and_redirects_to_notebook(self):
        response = self.post('create_section', {
            'notebook': self.notebook.pk, 'name': 'Fresh',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'notebook={self.notebook.pk}', response['Location'])
        self.assertTrue(Section.objects.filter(name='Fresh').exists())

    def test_rename_section_garbage_id_is_404(self):
        response = self.post('rename_section', {'id': 'zzz', 'name': 'x'})
        self.assertEqual(response.status_code, 404)

    def test_delete_section_garbage_id_oks_and_deletes_nothing(self):
        response = self.post('delete_section', {'id': 'zzz'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Section.objects.filter(pk=self.section.pk).exists())

    # -------------------------------------------------------------- tabs
    def test_create_tab_with_garbage_section_redirects_home(self):
        response = self.post('create_tab', {'section': 'zzz', 'name': 'T'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('notes'))

    def test_rename_tab_garbage_id_is_404(self):
        response = self.post('rename_tab', {'id': 'zzz', 'name': 'x'})
        self.assertEqual(response.status_code, 404)

    def test_delete_tab_garbage_id_oks_and_deletes_nothing(self):
        response = self.post('delete_tab', {'id': 'zzz'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Tab.objects.filter(pk=self.tab.pk).exists())

    def test_tab_pan_garbage_id_is_404(self):
        response = self.post('update_tab_pan', {'id': 'zzz', 'pan_x': 1, 'pan_y': 1})
        self.assertEqual(response.status_code, 404)

    def test_tab_pan_rejects_nan_and_stores_numbers(self):
        response = self.post('update_tab_pan', {
            'id': self.tab.pk, 'pan_x': 'NaN', 'pan_y': '-2.5',
        })
        self.assertEqual(response.status_code, 400)
        self.tab.refresh_from_db()
        self.assertEqual(self.tab.pan_x, 0)

    def test_tab_pan_accepts_finite_floats(self):
        response = self.post('update_tab_pan', {
            'id': self.tab.pk, 'pan_x': '-4.25', 'pan_y': '6.5',
        })
        self.assertEqual(response.status_code, 200)
        self.tab.refresh_from_db()
        self.assertEqual(self.tab.pan_x, -4.25)
        self.assertEqual(self.tab.pan_y, 6.5)

    # ---------------------------------------------------------- drawings
    def test_save_drawing_defaults_malformed_width(self):
        response = self.post('save_drawing', {
            'tab': self.tab.pk, 'path': 'M0 0', 'color': '#e25252', 'width': 'thick',
        })
        self.assertEqual(response.status_code, 200)
        drawing = Drawing.objects.get()
        self.assertEqual(drawing.width, 2)
        self.assertEqual(drawing.color, '#e25252')

    def test_save_drawing_rejects_a_colour_that_is_not_hex(self):
        """Round two: a colour that is not a hex value is refused, not cut.

        The value lands in a `style="stroke: ..."` attribute, so anything
        but a plain hex colour has no business in the database.
        """
        response = self.post('save_drawing', {
            'tab': self.tab.pk, 'path': 'M0 0', 'color': '#e25252overflowing',
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Drawing.objects.count(), 0)

    def test_save_note_does_not_duplicate_when_id_is_garbage(self):
        response = self.post('save_note', {'id': 'zzz', 'text': 'x', 'tab': self.tab.pk})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Note.objects.filter(tab=self.tab, text='x').count(), 0)

    def test_update_drawing_garbage_id_is_404(self):
        response = self.post('update_drawing', {'id': 'zzz', 'width': 3})
        self.assertEqual(response.status_code, 404)

    def test_update_drawing_keeps_width_when_malformed(self):
        drawing = Drawing.objects.create(tab=self.tab, path='M0 0', width=3)
        response = self.post('update_drawing', {'id': drawing.pk, 'width': 'zzz'})
        self.assertEqual(response.status_code, 200)
        drawing.refresh_from_db()
        self.assertEqual(drawing.width, 3)

    def test_update_drawing_accepts_numeric_width(self):
        drawing = Drawing.objects.create(tab=self.tab, path='M0 0', width=3)
        response = self.post('update_drawing', {'id': drawing.pk, 'width': '7.5'})
        self.assertEqual(response.status_code, 200)
        drawing.refresh_from_db()
        self.assertEqual(drawing.width, 7.5)

    def test_delete_drawing_garbage_id_oks_and_deletes_nothing(self):
        drawing = Drawing.objects.create(tab=self.tab, path='M0 0')
        response = self.post('delete_drawing', {'id': 'zzz'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Drawing.objects.filter(pk=drawing.pk).exists())

    # ------------------------------------------------------------ images
    def test_save_image_defaults_malformed_numbers(self):
        response = self.post('save_image', {
            'tab': self.tab.pk, 'data': 'data:image/png;base64,AAAA',
            'width': 'wide', 'height': 'tall',
        })
        self.assertEqual(response.status_code, 200)
        image = CanvasImage.objects.get()
        self.assertEqual(image.width, 200)
        self.assertEqual(image.height, 200)

    def test_save_image_still_saves_numbers(self):
        response = self.post('save_image', {
            'tab': self.tab.pk, 'data': 'data:image/png;base64,AAAA',
            'width': '120.75', 'height': '80.5', 'x': '10', 'y': '20',
            'rotation': '-90',
        })
        self.assertEqual(response.status_code, 200)
        image = CanvasImage.objects.get()
        self.assertEqual(image.width, 120.75)
        self.assertEqual(image.height, 80.5)
        self.assertEqual(image.rotation, -90)

    def test_save_image_persists_the_z_index_on_update(self):
        payload = 'data:image/png;base64,AAAA'
        response = self.post('save_image', {'tab': self.tab.pk, 'data': payload, 'z': '4'})
        self.assertEqual(response.status_code, 200)
        image = CanvasImage.objects.get()
        response = self.post('save_image', {'id': image.pk, 'data': payload, 'z': '0'})
        self.assertEqual(response.status_code, 200)
        image.refresh_from_db()
        self.assertEqual(image.z, 0)

    def test_save_image_create_honours_posted_z(self):
        CanvasImage.objects.create(tab=self.tab, data='older', z=9)
        response = self.post('save_image', {
            'tab': self.tab.pk, 'data': 'data:image/png;base64,AAAA',
            'z': '12', 'width': '50', 'height': '50',
        })
        self.assertEqual(response.json()['z'], 12)

    def test_save_image_rejects_non_finite_size(self):
        response = self.post('save_image', {
            'tab': self.tab.pk, 'data': 'data:image/png;base64,AAAA',
            'width': 'Infinity',
        })
        self.assertEqual(response.status_code, 400)

    def test_delete_image_garbage_id_oks_and_deletes_nothing(self):
        image = CanvasImage.objects.create(tab=self.tab, data='dd')
        response = self.post('delete_image', {'id': 'zzz'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(CanvasImage.objects.filter(pk=image.pk).exists())

    # -------------------------------------------------- payload guards
    def test_save_note_rejects_oversized_text(self):
        response = self.post('save_note', {
            'tab': self.tab.pk, 'text': 'x' * 20001,
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Note.objects.exists())

    def test_save_drawing_rejects_oversized_path(self):
        response = self.post('save_drawing', {
            'tab': self.tab.pk, 'path': 'M0 0' * 50001,
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Drawing.objects.exists())

    def test_save_image_rejects_oversized_data(self):
        response = self.post('save_image', {
            'tab': self.tab.pk, 'data': 'a' * (6 * 1024 * 1024 + 1),
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CanvasImage.objects.exists())

    def test_save_note_rejects_nan_coordinates(self):
        response = self.post('save_note', {'tab': self.tab.pk, 'text': 'x', 'x': 'NaN'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Note.objects.exists())

    def test_save_drawing_rejects_nan_width(self):
        response = self.post('save_drawing', {
            'tab': self.tab.pk, 'path': 'M0 0', 'width': 'NaN',
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Drawing.objects.exists())

    def test_update_drawing_rejects_nan_width(self):
        drawing = Drawing.objects.create(tab=self.tab, path='M0 0', width=3)
        response = self.post('update_drawing', {'id': drawing.pk, 'width': 'Infinity'})
        self.assertEqual(response.status_code, 400)
        drawing.refresh_from_db()
        self.assertEqual(drawing.width, 3)

    def test_save_image_rejects_nan_position(self):
        response = self.post('save_image', {
            'tab': self.tab.pk, 'data': 'data:image/png;base64,AAAA', 'x': 'NaN',
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CanvasImage.objects.exists())


class NotesPayloadGuardTests(TestCase):
    """Round two: the canvas payloads need bounds of their own.

    The drawing colour ended up inside a `style="stroke: ..."` attribute,
    the image data ended up as the src of an <img> and the coordinates
    could place a note a million pixels outside the canvas.
    """

    def setUp(self):
        self.notebook = Notebook.objects.create(name='Guards')
        self.section = Section.objects.create(notebook=self.notebook, name='Work')
        self.tab = Tab.objects.create(section=self.section, name='Ideas')

    def post(self, url_name, data):
        return self.client.post(reverse(url_name), data)

    # ------------------------------------------------------------ colour
    def test_a_drawing_with_a_junk_colour_is_rejected(self):
        response = self.post('save_drawing', {
            'tab': self.tab.pk, 'path': 'M 0 0 L 10 10',
            'color': 'red;position:fixed', 'width': 2,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Drawing.objects.count(), 0)

    def test_a_drawing_with_a_hex_colour_is_still_accepted(self):
        response = self.post('save_drawing', {
            'tab': self.tab.pk, 'path': 'M 0 0 L 10 10',
            'color': '#3fa34d', 'width': 2,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Drawing.objects.get().color, '#3fa34d')

    def test_a_short_hex_colour_is_accepted(self):
        response = self.post('save_drawing', {
            'tab': self.tab.pk, 'path': 'M 0 0', 'color': '#abc', 'width': 2,
        })
        self.assertEqual(response.status_code, 200)

    def test_updating_a_drawing_with_a_junk_colour_is_rejected(self):
        drawing = Drawing.objects.create(tab=self.tab, path='M 0 0', color='#111111', width=2)
        response = self.post('update_drawing', {
            'id': drawing.pk, 'color': 'expression(alert(1))',
        })
        self.assertEqual(response.status_code, 400)
        drawing.refresh_from_db()
        self.assertEqual(drawing.color, '#111111')

    # ------------------------------------------------------------- width
    def test_a_negative_drawing_width_is_rejected(self):
        response = self.post('save_drawing', {
            'tab': self.tab.pk, 'path': 'M 0 0', 'width': -50,
        })
        self.assertEqual(response.status_code, 400)

    def test_a_huge_drawing_width_is_rejected(self):
        response = self.post('save_drawing', {
            'tab': self.tab.pk, 'path': 'M 0 0', 'width': 100000,
        })
        self.assertEqual(response.status_code, 400)

    def test_a_huge_drawing_width_is_rejected_on_update(self):
        drawing = Drawing.objects.create(tab=self.tab, path='M 0 0', color='#111111', width=2)
        response = self.post('update_drawing', {'id': drawing.pk, 'width': 1e9})
        self.assertEqual(response.status_code, 400)
        drawing.refresh_from_db()
        self.assertEqual(drawing.width, 2)

    # -------------------------------------------------------------- name
    def test_renaming_a_tab_to_nothing_is_rejected(self):
        response = self.post('rename_tab', {'id': self.tab.pk, 'name': '   '})
        self.assertEqual(response.status_code, 400)
        self.tab.refresh_from_db()
        self.assertEqual(self.tab.name, 'Ideas')

    def test_renaming_a_section_to_nothing_is_rejected(self):
        response = self.post('rename_section', {'id': self.section.pk, 'name': ''})
        self.assertEqual(response.status_code, 400)
        self.section.refresh_from_db()
        self.assertEqual(self.section.name, 'Work')

    def test_renaming_a_tab_still_works(self):
        response = self.post('rename_tab', {'id': self.tab.pk, 'name': 'Fresh'})
        self.assertEqual(response.status_code, 200)
        self.tab.refresh_from_db()
        self.assertEqual(self.tab.name, 'Fresh')

    # --------------------------------------------------------- image data
    def test_image_data_must_be_an_image_payload(self):
        response = self.post('save_image', {
            'tab': self.tab.pk, 'x': 0, 'y': 0, 'width': 10, 'height': 10,
            'data': 'https://example.com/tracker.gif',
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CanvasImage.objects.count(), 0)

    def test_a_base64_image_payload_is_accepted(self):
        payload = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=='
        response = self.post('save_image', {
            'tab': self.tab.pk, 'x': 0, 'y': 0, 'width': 10, 'height': 10,
            'data': payload,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CanvasImage.objects.get().data, payload)

    # -------------------------------------------------------- coordinates
    def test_a_note_cannot_be_saved_far_outside_the_canvas(self):
        response = self.post('save_note', {
            'tab': self.tab.pk, 'text': 'lost', 'x': 10 ** 9, 'y': 0,
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Note.objects.count(), 0)

    def test_a_note_inside_the_canvas_is_still_saved(self):
        response = self.post('save_note', {
            'tab': self.tab.pk, 'text': 'here', 'x': 120, 'y': 240,
        })
        self.assertEqual(response.status_code, 200)
        note = Note.objects.get()
        self.assertEqual(note.x, 120)
        self.assertEqual(note.y, 240)


class NotesClientGuardTests(TestCase):
    """Round two: the canvas client must not pretend a save worked.

    There is no javascript in the test runner, so these tests pin the
    error handling in the template: a failed save has to be visible and a
    failed delete must not remove the element from the canvas.
    """

    def setUp(self):
        self.notebook = Notebook.objects.create(name='Client')
        self.section = Section.objects.create(notebook=self.notebook, name='Work')
        self.tab = Tab.objects.create(section=self.section, name='Ideas')

    def canvas(self):
        return self.client.get(reverse('notes')).content.decode()

    def test_a_failed_note_save_is_reported(self):
        html = self.canvas()
        self.assertIn('Note save failed', html)
        self.assertIn('Image save failed', html)
        self.assertIn('Drawing save failed', html)

    def test_a_failed_delete_keeps_the_element_on_the_canvas(self):
        html = self.canvas()
        self.assertIn('Note delete failed', html)
        self.assertIn('Image delete failed', html)
        self.assertIn('Drawing delete failed', html)
        # the element may only go away when the server confirmed it
        self.assertNotIn('.then(function () { note.remove(); });', html)
        self.assertNotIn('.then(function () { box.remove(); });', html)

    def test_a_failed_rename_puts_the_old_name_back(self):
        html = self.canvas()
        self.assertIn('Section rename failed', html)
        self.assertIn('Tab rename failed', html)

    def test_the_pan_is_only_saved_when_it_moved(self):
        html = self.canvas()
        self.assertIn('panX !== baseX || panY !== baseY', html)

    def test_pasting_inside_a_note_does_not_drop_a_canvas_image(self):
        html = self.canvas()
        self.assertIn('active.isContentEditable', html)


class NotesBodyLimitTests(TestCase):
    """Round two: django's own body limit was below the app's own cap.

    The canvas posts pictures as base64 data urls and the app allows 6 MB
    per image - but django stopped the request at 2.5 MB with an opaque
    400 before the view could even look at it.
    """

    def setUp(self):
        self.notebook = Notebook.objects.create(name='Body')
        self.section = Section.objects.create(notebook=self.notebook, name='Work')
        self.tab = Tab.objects.create(section=self.section, name='Ideas')

    def test_a_three_megabyte_image_reaches_the_view(self):
        payload = 'data:image/png;base64,' + ('A' * (3 * 1024 * 1024))
        response = self.client.post(reverse('save_image'), {
            'tab': self.tab.pk, 'x': 0, 'y': 0, 'width': 10, 'height': 10,
            'data': payload,
        })
        self.assertEqual(response.status_code, 200)
        image = CanvasImage.objects.get()
        self.assertEqual(len(image.data), len(payload))

    def test_the_body_limit_covers_the_image_cap(self):
        from django.conf import settings as django_settings

        self.assertGreater(
            django_settings.DATA_UPLOAD_MAX_MEMORY_SIZE,
            6 * 1024 * 1024,
        )


class NotesImageGuardTests(TestCase):
    """Round two: an image without a size cannot be worked with."""

    def setUp(self):
        self.notebook = Notebook.objects.create(name='Images')
        self.section = Section.objects.create(notebook=self.notebook, name='Work')
        self.tab = Tab.objects.create(section=self.section, name='Ideas')
        self.payload = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=='

    def test_a_zero_sized_image_is_raised_to_a_usable_size(self):
        response = self.client.post(reverse('save_image'), {
            'tab': self.tab.pk, 'data': self.payload, 'width': 0, 'height': 0,
        })
        self.assertEqual(response.status_code, 200)
        image = CanvasImage.objects.get()
        self.assertGreaterEqual(image.width, 1)
        self.assertGreaterEqual(image.height, 1)

    def test_an_image_outside_the_canvas_is_pulled_back(self):
        response = self.client.post(reverse('save_image'), {
            'tab': self.tab.pk, 'data': self.payload,
            'x': 10 ** 9, 'y': -(10 ** 9), 'width': 10, 'height': 10,
        })
        self.assertEqual(response.status_code, 200)
        image = CanvasImage.objects.get()
        self.assertLessEqual(abs(image.x), 100000)
        self.assertLessEqual(abs(image.y), 100000)

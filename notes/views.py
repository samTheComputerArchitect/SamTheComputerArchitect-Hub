import math
import re

from django.db import models
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from .models import CanvasImage, Drawing, Note, Notebook, Section, Tab

MAX_NAME_LENGTH = 100
# Payload guards for the free-form canvas fields (TextField has no bound).
MAX_NOTE_TEXT_LENGTH = 20000
MAX_DRAWING_PATH_LENGTH = 200000
MAX_IMAGE_DATA_LENGTH = 6 * 1024 * 1024
# The canvas is a page, not a planet: coordinates outside this range are
# notes the user can never find again.
MAX_CANVAS_COORDINATE = 100000
MAX_IMAGE_SIZE = 20000
MIN_DRAWING_WIDTH = 0.5
MAX_DRAWING_WIDTH = 200
HEX_COLOR_RE = re.compile(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6})$')
IMAGE_DATA_RE = re.compile(r'^data:image/(png|jpe?g|gif|webp|svg\+xml);base64,[A-Za-z0-9+/=]+$')


def clean_color(value, default=None):
    """Return a hex colour or None when the value is not one.

    The colour ends up inside a `style="stroke: ..."` attribute, so it has
    to be a plain hex value - the seven character truncation alone still
    let values like `red;pos` through.
    """
    text = (value or '').strip()
    if not text:
        return default
    if HEX_COLOR_RE.match(text):
        return text
    return None


def safe_pk(value):
    """Parse a form/GET value into an integer pk, or None when it is junk.

    Every lookup in this app used to hand the raw string to .filter(pk=...),
    which raises ValueError (-> 500) for anything non-numeric.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def notes(request):
    notebooks = Notebook.objects.all()

    selected_notebook = None
    requested_notebook = safe_pk(request.GET.get('notebook'))
    if requested_notebook:
        selected_notebook = notebooks.filter(pk=requested_notebook).first()
    if selected_notebook is None:
        selected_notebook = notebooks.first()

    sections = (
        selected_notebook.sections.all()
        if selected_notebook
        else Section.objects.none()
    )

    selected_section = None
    requested_section = safe_pk(request.GET.get('section'))
    if requested_section:
        selected_section = sections.filter(pk=requested_section).first()
    if selected_section is None:
        selected_section = sections.first()

    tabs = (
        selected_section.tabs.all()
        if selected_section
        else Tab.objects.none()
    )

    selected_tab = None
    requested_tab = safe_pk(request.GET.get('tab'))
    if requested_tab:
        selected_tab = tabs.filter(pk=requested_tab).first()
    if selected_tab is None:
        selected_tab = tabs.first()

    note_items = (
        selected_tab.notes.all()
        if selected_tab
        else Note.objects.none()
    )

    drawing_items = (
        selected_tab.drawings.all()
        if selected_tab
        else Drawing.objects.none()
    )

    image_items = (
        selected_tab.images.all()
        if selected_tab
        else CanvasImage.objects.none()
    )

    return render(request, 'notes/notes.html', {
        'notebooks': notebooks,
        'selected': selected_notebook,
        'sections': sections,
        'selected_section': selected_section,
        'tabs': tabs,
        'selected_tab': selected_tab,
        'note_items': note_items,
        'drawing_items': drawing_items,
        'image_items': image_items,
        'pan_x': selected_tab.pan_x if selected_tab else 0,
        'pan_y': selected_tab.pan_y if selected_tab else 0,
    })



def create_section(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    notebook_id = request.POST.get('notebook')
    name = (request.POST.get('name') or '').strip()[:MAX_NAME_LENGTH]

    notebook = Notebook.objects.filter(pk=safe_pk(notebook_id)).first()
    if notebook and name:
        section, _ = notebook.sections.get_or_create(name=name)
        section.tabs.get_or_create(name='Untitled')

    if notebook is None:
        return redirect(reverse('notes'))

    return redirect(f"{reverse('notes')}?notebook={notebook.pk}")


def create_tab(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    section_id = request.POST.get('section')
    section = Section.objects.filter(pk=safe_pk(section_id)).first()
    if section is None:
        return redirect(reverse('notes'))

    name = (request.POST.get('name') or '').strip()[:MAX_NAME_LENGTH]
    tab = None
    if name:
        tab, _ = section.tabs.get_or_create(name=name)

    url = f"{reverse('notes')}?notebook={section.notebook_id}&section={section.pk}"
    if tab is not None:
        url += f"&tab={tab.pk}"
    return redirect(url)


def save_note(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    text = (request.POST.get('text') or '').strip()
    note_id = safe_pk(request.POST.get('id'))
    tab_id = safe_pk(request.POST.get('tab'))
    kind = request.POST.get('kind') or Note.KIND_NOTE
    x = parse_float(request.POST.get('x'), 0)
    y = parse_float(request.POST.get('y'), 0)

    if kind not in dict(Note.KIND_CHOICES):
        kind = Note.KIND_NOTE

    if len(text) > MAX_NOTE_TEXT_LENGTH:
        return JsonResponse({'error': 'text too long'}, status=400)
    if not (math.isfinite(x) and math.isfinite(y)):
        return JsonResponse({'error': 'invalid coordinates'}, status=400)
    if not (-MAX_CANVAS_COORDINATE <= x <= MAX_CANVAS_COORDINATE):
        return JsonResponse({'error': 'invalid coordinates'}, status=400)
    if not (-MAX_CANVAS_COORDINATE <= y <= MAX_CANVAS_COORDINATE):
        return JsonResponse({'error': 'invalid coordinates'}, status=400)

    if request.POST.get('id'):
        # A client that sends `id` means it wants to update an existing
        # note; an unparseable or stale id must not silently become a
        # fresh note (that used to duplicate notes instead of failing).
        note = Note.objects.filter(pk=note_id).first() if note_id else None
        if note is None:
            return JsonResponse({'error': 'not found'}, status=404)
        note.text = text
        note.x = x
        note.y = y
        note.kind = kind
        note.save()
    else:
        tab = Tab.objects.filter(pk=tab_id).first()
        if tab is None:
            return JsonResponse({'error': 'no tab'}, status=400)
        note = Note.objects.create(tab=tab, kind=kind, text=text, x=x, y=y)

    return JsonResponse({
        'id': note.pk,
        'date': f"{note.date.strftime('%b')} {note.date.day}",
    })


def delete_note(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    note_id = safe_pk(request.POST.get('id'))
    if note_id:
        Note.objects.filter(pk=note_id).delete()

    return JsonResponse({'ok': True})


def save_drawing(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    tab_id = safe_pk(request.POST.get('tab'))
    path = (request.POST.get('path') or '').strip()
    color = clean_color(request.POST.get('color'))
    width = parse_float(request.POST.get('width'), Drawing._meta.get_field('width').default)

    tab = Tab.objects.filter(pk=tab_id).first()
    if tab is None or not path:
        return JsonResponse({'error': 'no tab or path'}, status=400)
    if len(path) > MAX_DRAWING_PATH_LENGTH:
        return JsonResponse({'error': 'path too long'}, status=400)
    if not math.isfinite(width):
        return JsonResponse({'error': 'invalid width'}, status=400)
    if not (MIN_DRAWING_WIDTH <= width <= MAX_DRAWING_WIDTH):
        return JsonResponse({'error': 'invalid width'}, status=400)
    if request.POST.get('color') and color is None:
        return JsonResponse({'error': 'invalid color'}, status=400)

    drawing = Drawing.objects.create(
        tab=tab,
        path=path,
        color=color or Drawing._meta.get_field('color').default,
        width=width,
    )
    return JsonResponse({'id': drawing.pk, 'color': drawing.color, 'width': drawing.width})


def update_drawing(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    drawing = Drawing.objects.filter(pk=safe_pk(request.POST.get('id'))).first()
    if drawing is None:
        return JsonResponse({'error': 'not found'}, status=404)

    color = clean_color(request.POST.get('color'))
    if request.POST.get('color') and color is None:
        return JsonResponse({'error': 'invalid color'}, status=400)
    if color:
        drawing.color = color
    width = parse_float(request.POST.get('width'), None)
    if width is not None:
        if not math.isfinite(width):
            return JsonResponse({'error': 'invalid width'}, status=400)
        if not (MIN_DRAWING_WIDTH <= width <= MAX_DRAWING_WIDTH):
            return JsonResponse({'error': 'invalid width'}, status=400)
        drawing.width = width
    drawing.save()

    return JsonResponse({'id': drawing.pk, 'color': drawing.color, 'width': drawing.width})


def rename_tab(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    tab = Tab.objects.filter(pk=safe_pk(request.POST.get('id'))).first()
    if tab is None:
        return JsonResponse({'error': 'not found'}, status=404)

    name = (request.POST.get('name') or '').strip()[:MAX_NAME_LENGTH]
    if not name:
        # An empty name used to answer 200 without renaming anything, so
        # the caller could not tell the rename failed.
        return JsonResponse({'error': 'name is required'}, status=400)
    tab.name = name
    tab.save()

    return JsonResponse({'id': tab.pk, 'name': tab.name})


def update_tab_pan(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    tab = Tab.objects.filter(pk=safe_pk(request.POST.get('id'))).first()
    if tab is None:
        return JsonResponse({'error': 'not found'}, status=404)

    pan_x = parse_float(request.POST.get('pan_x'), 0)
    pan_y = parse_float(request.POST.get('pan_y'), 0)
    if not (math.isfinite(pan_x) and math.isfinite(pan_y)):
        return JsonResponse({'error': 'invalid coordinates'}, status=400)
    tab.pan_x = pan_x
    tab.pan_y = pan_y
    tab.save()

    return JsonResponse({'ok': True})


def delete_tab(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    tab_id = safe_pk(request.POST.get('id'))
    if tab_id:
        Tab.objects.filter(pk=tab_id).delete()

    return JsonResponse({'ok': True})


def rename_section(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    section = Section.objects.filter(pk=safe_pk(request.POST.get('id'))).first()
    if section is None:
        return JsonResponse({'error': 'not found'}, status=404)

    name = (request.POST.get('name') or '').strip()[:MAX_NAME_LENGTH]
    if not name:
        return JsonResponse({'error': 'name is required'}, status=400)
    section.name = name
    section.save()

    return JsonResponse({'id': section.pk, 'name': section.name})


def delete_section(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    section_id = safe_pk(request.POST.get('id'))
    if section_id:
        Section.objects.filter(pk=section_id).delete()

    return JsonResponse({'ok': True})


def create_notebook(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    name = (request.POST.get('name') or '').strip()[:MAX_NAME_LENGTH]
    if not name:
        return JsonResponse({'error': 'name is required'}, status=400)

    notebook, created = Notebook.objects.get_or_create(name=name)
    if not created:
        return JsonResponse({'error': 'notebook already exists'}, status=400)

    return JsonResponse({'id': notebook.pk, 'name': notebook.name})


def delete_drawing(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    drawing_id = safe_pk(request.POST.get('id'))
    if drawing_id:
        Drawing.objects.filter(pk=drawing_id).delete()

    return JsonResponse({'ok': True})


def save_image(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    data = (request.POST.get('data') or '').strip()
    if not data:
        return JsonResponse({'error': 'no image data'}, status=400)
    if len(data) > MAX_IMAGE_DATA_LENGTH:
        return JsonResponse({'error': 'image too large'}, status=400)
    if not IMAGE_DATA_RE.match(data):
        # Only a base64 image payload may be stored: the value is rendered
        # as the src of an <img>, so an arbitrary url would turn the canvas
        # into a loader for remote content.
        return JsonResponse({'error': 'invalid image data'}, status=400)

    image_id = safe_pk(request.POST.get('id'))
    tab_id = safe_pk(request.POST.get('tab'))
    tab = Tab.objects.filter(pk=tab_id).first() if tab_id else None
    if tab is None and not image_id:
        return JsonResponse({'error': 'no tab'}, status=400)

    width = parse_float(request.POST.get('width'), 200)
    height = parse_float(request.POST.get('height'), 200)
    x = parse_float(request.POST.get('x'), 0)
    y = parse_float(request.POST.get('y'), 0)
    rotation = parse_float(request.POST.get('rotation'), 0)
    # The client sends z for layering (bring to front / send to back); it
    # used to be ignored completely, so stacking resets on every reload.
    raw_z = request.POST.get('z')
    parsed_z = parse_float(raw_z, None)
    if raw_z and parsed_z is not None and math.isfinite(parsed_z):
        z = max(0, int(parsed_z))
    else:
        z = None

    if not (math.isfinite(width) and math.isfinite(height)):
        return JsonResponse({'error': 'invalid dimensions'}, status=400)
    if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(rotation)):
        return JsonResponse({'error': 'invalid coordinates'}, status=400)
    # An image without a size cannot be grabbed or resized on the canvas
    # (the client divides by the height), and a huge one pushes everything
    # else off the board.
    width = min(max(width, 1), MAX_IMAGE_SIZE)
    height = min(max(height, 1), MAX_IMAGE_SIZE)
    x = min(max(x, -MAX_CANVAS_COORDINATE), MAX_CANVAS_COORDINATE)
    y = min(max(y, -MAX_CANVAS_COORDINATE), MAX_CANVAS_COORDINATE)

    if image_id:
        image = CanvasImage.objects.filter(pk=image_id).first()
        if image is None:
            return JsonResponse({'error': 'not found'}, status=404)
        image.data = data
        image.x = x
        image.y = y
        image.width = width
        image.height = height
        image.rotation = rotation
        if z is not None:
            image.z = z
        image.save()
    else:
        max_z = CanvasImage.objects.aggregate(models.Max('z'))['z__max'] or 0
        image = CanvasImage.objects.create(
            tab=tab,
            data=data,
            x=x,
            y=y,
            width=width,
            height=height,
            rotation=rotation,
            z=z if z is not None else max_z + 1,
        )

    return JsonResponse({
        'id': image.pk,
        'x': image.x,
        'y': image.y,
        'width': image.width,
        'height': image.height,
        'z': image.z,
    })


def delete_image(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    image_id = safe_pk(request.POST.get('id'))
    if image_id:
        CanvasImage.objects.filter(pk=image_id).delete()

    return JsonResponse({'ok': True})
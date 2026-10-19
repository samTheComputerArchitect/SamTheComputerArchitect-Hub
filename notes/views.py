from django.db import models
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from .models import CanvasImage, Drawing, Note, Notebook, Section, Tab

MAX_NAME_LENGTH = 100


def notes(request):
    notebooks = Notebook.objects.all()

    selected_notebook = None
    requested_notebook = request.GET.get('notebook')
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
    requested_section = request.GET.get('section')
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
    requested_tab = request.GET.get('tab')
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

    notebook = Notebook.objects.filter(pk=notebook_id).first()
    if notebook and name:
        section, _ = notebook.sections.get_or_create(name=name)
        section.tabs.get_or_create(name='Untitled')

    return redirect(f"{reverse('notes')}?notebook={notebook_id}")


def create_tab(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    section_id = request.POST.get('section')
    section = Section.objects.filter(pk=section_id).first()
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
    note_id = request.POST.get('id')
    tab_id = request.POST.get('tab')
    kind = request.POST.get('kind') or Note.KIND_NOTE
    x = request.POST.get('x') or 0
    y = request.POST.get('y') or 0

    if kind not in dict(Note.KIND_CHOICES):
        kind = Note.KIND_NOTE

    if note_id:
        note = Note.objects.filter(pk=note_id).first()
        if note is None:
            return JsonResponse({'error': 'not found'}, status=404)
        note.text = text
        note.x = x
        note.y = y
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

    note_id = request.POST.get('id')
    if note_id:
        Note.objects.filter(pk=note_id).delete()

    return JsonResponse({'ok': True})


def save_drawing(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    tab_id = request.POST.get('tab')
    path = (request.POST.get('path') or '').strip()
    color = (request.POST.get('color') or '').strip()
    width = request.POST.get('width') or Drawing._meta.get_field('width').default

    tab = Tab.objects.filter(pk=tab_id).first()
    if tab is None or not path:
        return JsonResponse({'error': 'no tab or path'}, status=400)

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

    drawing = Drawing.objects.filter(pk=request.POST.get('id')).first()
    if drawing is None:
        return JsonResponse({'error': 'not found'}, status=404)

    color = (request.POST.get('color') or '').strip()
    if color:
        drawing.color = color
    if request.POST.get('width'):
        drawing.width = request.POST.get('width')
    drawing.save()

    return JsonResponse({'id': drawing.pk, 'color': drawing.color, 'width': drawing.width})


def rename_tab(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    tab = Tab.objects.filter(pk=request.POST.get('id')).first()
    if tab is None:
        return JsonResponse({'error': 'not found'}, status=404)

    name = (request.POST.get('name') or '').strip()[:MAX_NAME_LENGTH]
    if name:
        tab.name = name
        tab.save()

    return JsonResponse({'id': tab.pk, 'name': tab.name})


def update_tab_pan(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    tab = Tab.objects.filter(pk=request.POST.get('id')).first()
    if tab is None:
        return JsonResponse({'error': 'not found'}, status=404)

    try:
        tab.pan_x = float(request.POST.get('pan_x', 0))
        tab.pan_y = float(request.POST.get('pan_y', 0))
        tab.save()
    except ValueError:
        return JsonResponse({'error': 'invalid coordinates'}, status=400)

    return JsonResponse({'ok': True})


def delete_tab(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    tab_id = request.POST.get('id')
    if tab_id:
        Tab.objects.filter(pk=tab_id).delete()

    return JsonResponse({'ok': True})


def rename_section(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    section = Section.objects.filter(pk=request.POST.get('id')).first()
    if section is None:
        return JsonResponse({'error': 'not found'}, status=404)

    name = (request.POST.get('name') or '').strip()[:MAX_NAME_LENGTH]
    if name:
        section.name = name
        section.save()

    return JsonResponse({'id': section.pk, 'name': section.name})


def delete_section(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    section_id = request.POST.get('id')
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

    drawing_id = request.POST.get('id')
    if drawing_id:
        Drawing.objects.filter(pk=drawing_id).delete()

    return JsonResponse({'ok': True})


def save_image(request):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    data = (request.POST.get('data') or '').strip()
    if not data:
        return JsonResponse({'error': 'no image data'}, status=400)

    image_id = request.POST.get('id')
    tab_id = request.POST.get('tab')
    tab = Tab.objects.filter(pk=tab_id).first() if tab_id else None
    if tab is None and not image_id:
        return JsonResponse({'error': 'no tab'}, status=400)

    width = float(request.POST.get('width') or 200)
    height = float(request.POST.get('height') or 200)
    x = float(request.POST.get('x') or 0)
    y = float(request.POST.get('y') or 0)
    rotation = float(request.POST.get('rotation') or 0)

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
            z=max_z + 1,
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

    image_id = request.POST.get('id')
    if image_id:
        CanvasImage.objects.filter(pk=image_id).delete()

    return JsonResponse({'ok': True})
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
import base64
import os
import re
import uuid

from .models import Thumbnail, ThumbnailElement

CANVAS_W = 1280
CANVAS_H = 720

MAX_NAME_LENGTH = 255
MAX_UPLOAD_BYTES = 12 * 1024 * 1024

MEDIA_PATH_RE = re.compile(r'^(thumbnail_elements|thumbnails)/([A-Za-z0-9_.-]+)$')
SNAPSHOT_IMAGE_RE = re.compile(r'^data:image/(png|jpe?g|webp);base64,([A-Za-z0-9+/=]+)$')

HEX_COLOR_RE = re.compile(r'^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$')
TRANSPARENT = 'transparent'

# Fallback natural size used when the uploaded file cannot be inspected.
FALLBACK_IMAGE_SIZE = (400, 400)

SHAPE_DEFAULT_SIZES = {
    'rectangle': (320, 200),
    'square': (180, 180),
    'circle': (180, 180),
    'triangle': (240, 220),
    'line': (400, 6),
}

TRUE_VALUES = ('1', 'true', 'True', 'TRUE', 'on', 'yes')


def _clean_color(value, allow_transparent=True):
    """Return a safe CSS colour or None when the value is not a valid colour.

    Colours are injected into inline SVG/HTML on the client, so anything that is
    not a plain hex colour (optionally the `transparent` keyword) is rejected.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return ''
    if allow_transparent and text.lower() == TRANSPARENT:
        return TRANSPARENT
    if HEX_COLOR_RE.match(text):
        return text
    return None


def _clean_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip() in TRUE_VALUES


def _serialize(element):
    data = {
        'id': element.pk,
        'kind': element.kind,
        'shape': element.shape,
        'text': element.text,
        'color': element.color,
        'font_size': element.font_size,
        'bold': element.bold,
        'align': element.align,
        'font_family': element.font_family,
        'italic': element.italic,
        'letter_spacing': element.letter_spacing,
        'outline_color': element.outline_color,
        'outline_width': element.outline_width,
        'x': element.x,
        'y': element.y,
        'width': element.width,
        'height': element.height,
        'rotation': element.rotation,
        'opacity': element.opacity,
        'flip_x': element.flip_x,
        'flip_y': element.flip_y,
        'brightness': element.brightness,
        'contrast': element.contrast,
        'saturation': element.saturation,
        'hue': element.hue,
        'border_radius': element.border_radius,
        'z': element.z_index,
    }
    if element.image:
        data['image_url'] = element.image.url
        data['image_name'] = element.name()
    return data


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _natural_size(image_field):
    """Best effort natural size of a stored image. Never raises."""
    try:
        from PIL import Image

        with Image.open(image_field.path) as im:
            return im.size
    except Exception:
        return (0, 0)


def thumbnails(request):
    thumb_items = []
    for thumb in Thumbnail.objects.all().order_by('-created_at'):
        preview = (
            thumb.elements.filter(kind=ThumbnailElement.KIND_IMAGE)
            .order_by('-z_index', '-id')
            .first()
        )
        preview_url = None
        if preview is not None and preview.image:
            try:
                preview_url = preview.image.url
            except ValueError:
                preview_url = None
        thumb_items.append({
            'thumb': thumb,
            'preview_url': preview_url,
        })
    return render(request, 'thumbnails/thumbnails.html', {'thumb_items': thumb_items})


def editor(request, thumb_id):
    thumb = Thumbnail.objects.filter(pk=thumb_id).first()
    if thumb is None:
        return redirect('thumbnails')

    elements = thumb.elements.all().order_by('z_index', 'id')
    return render(request, 'thumbnails/editor.html', {
        'thumb': thumb,
        'elements_json': [_serialize(element) for element in elements],
    })


@require_POST
def create_thumbnail(request):
    name = (request.POST.get('name') or '').strip()[:MAX_NAME_LENGTH]
    if not name:
        return JsonResponse({'error': 'Name is required'}, status=400)

    thumb = Thumbnail.objects.create(name=name)
    return JsonResponse({'id': thumb.pk, 'url': reverse('thumbnail_editor', args=[thumb.pk])})


@require_POST
def rename_thumbnail(request):
    thumb = Thumbnail.objects.filter(pk=request.POST.get('id')).first()
    if thumb is None:
        return JsonResponse({'error': 'Thumbnail not found'}, status=404)

    name = (request.POST.get('name') or '').strip()[:MAX_NAME_LENGTH]
    if name:
        thumb.name = name
        thumb.save()
    return JsonResponse({'id': thumb.pk, 'name': thumb.name})


@require_POST
def background_update(request):
    thumb = Thumbnail.objects.filter(pk=request.POST.get('thumbnail') or request.POST.get('id')).first()
    if thumb is None:
        return JsonResponse({'error': 'Thumbnail not found'}, status=404)

    raw = (request.POST.get('background_color') or '').strip()
    if raw:
        color = _clean_color(raw, allow_transparent=False)
        if color is None:
            return JsonResponse({'error': 'Invalid color'}, status=400)
    else:
        color = ''
    thumb.background_color = color
    thumb.save()
    return JsonResponse({'id': thumb.pk, 'background_color': thumb.background_color})


@require_POST
def delete_thumbnail(request):
    thumb = Thumbnail.objects.filter(pk=request.POST.get('id')).first()
    if thumb is None:
        return JsonResponse({'error': 'Thumbnail not found'}, status=404)
    thumb.delete()
    return JsonResponse({'status': 'success'})


@require_POST
def duplicate_thumbnail(request):
    original = Thumbnail.objects.filter(pk=request.POST.get('id')).first()
    if original is None:
        return JsonResponse({'error': 'Thumbnail not found'}, status=404)

    duplicate = Thumbnail.objects.create(
        name=f'{original.name} (copy)'[:MAX_NAME_LENGTH],
        background_color=original.background_color,
    )
    for element in original.elements.all().order_by('z_index', 'id'):
        fields = {
            'thumbnail': duplicate,
            'kind': element.kind,
            'shape': element.shape,
            'text': element.text,
            'color': element.color,
            'font_size': element.font_size,
            'bold': element.bold,
            'align': element.align,
            'font_family': element.font_family,
            'italic': element.italic,
            'letter_spacing': element.letter_spacing,
            'outline_color': element.outline_color,
            'outline_width': element.outline_width,
            'x': element.x,
            'y': element.y,
            'width': element.width,
            'height': element.height,
            'rotation': element.rotation,
            'opacity': element.opacity,
            'flip_x': element.flip_x,
            'flip_y': element.flip_y,
            'brightness': element.brightness,
            'contrast': element.contrast,
            'saturation': element.saturation,
            'hue': element.hue,
            'border_radius': element.border_radius,
            'z_index': element.z_index,
        }
        if element.image:
            base = element.image.name.rsplit('/', 1)[-1]
            try:
                with element.image.open('rb') as file_obj:
                    fields['image'] = default_storage.save(f'thumbnail_elements/copy_{base}', file_obj)
            except (OSError, ValueError):
                pass
        ThumbnailElement.objects.create(**fields)
    return JsonResponse({'id': duplicate.pk, 'status': 'success'})


def _materialize_image(request):
    upload = request.FILES.get('image')
    if upload:
        if getattr(upload, 'size', 0) > MAX_UPLOAD_BYTES:
            return None
        base = os.path.basename(getattr(upload, 'name', '') or 'asset')
        base = re.sub(r'[^A-Za-z0-9_.-]', '_', base) or 'asset'
        return default_storage.save(f'thumbnail_elements/{base}', upload)

    src = (request.POST.get('image_url') or '').strip()
    if src:
        rel = src.split('/media/')[-1]
        match = MEDIA_PATH_RE.match(rel)
        if not match:
            return None
        path = f"{match.group(1)}/{match.group(2)}"
        if not default_storage.exists(path):
            return None
        base = match.group(2)
        try:
            with default_storage.open(path, 'rb') as file_obj:
                return default_storage.save(f'thumbnail_elements/copy_{base}', file_obj)
        except (OSError, ValueError):
            return None

    snapshot = (request.POST.get('snapshot_image') or '').strip()
    if snapshot:
        match = SNAPSHOT_IMAGE_RE.match(snapshot)
        if not match:
            return None
        ext = match.group(1)
        if ext == 'jpeg':
            ext = 'jpg'
        try:
            content = base64.b64decode(match.group(2), validate=True)
        except Exception:
            return None
        if not content or len(content) > MAX_UPLOAD_BYTES:
            return None
        name = f'thumbnail_elements/restore_{uuid.uuid4().hex[:10]}.{ext}'
        return default_storage.save(name, ContentFile(content))

    return None


@require_POST
def element_create(request):
    thumb = Thumbnail.objects.filter(pk=request.POST.get('thumbnail')).first()
    if thumb is None:
        return JsonResponse({'error': 'Thumbnail not found'}, status=404)

    kind = request.POST.get('kind') or ThumbnailElement.KIND_IMAGE
    if kind not in dict(ThumbnailElement.KIND_CHOICES):
        kind = ThumbnailElement.KIND_IMAGE

    element = ThumbnailElement(thumbnail=thumb, kind=kind)

    if kind == ThumbnailElement.KIND_IMAGE:
        stored = _materialize_image(request)
        if not stored:
            return JsonResponse({'error': 'Image is required'}, status=400)
        element.image = stored

        nat_w, nat_h = _natural_size(element.image)
        if not nat_w or not nat_h:
            nat_w, nat_h = FALLBACK_IMAGE_SIZE
        scale = min(1.0, CANVAS_W / nat_w, CANVAS_H / nat_h)
        element.width = round(nat_w * scale, 2)
        element.height = round(nat_h * scale, 2)
        element.x = round((CANVAS_W - element.width) / 2, 2)
        element.y = round((CANVAS_H - element.height) / 2, 2)
    elif kind == ThumbnailElement.KIND_SHAPE:
        shape = request.POST.get('shape') or 'rectangle'
        if shape not in ThumbnailElement.SHAPE_CHOICES:
            shape = 'rectangle'
        element.shape = shape
        color = _clean_color(request.POST.get('color'), allow_transparent=True)
        if color is None:
            color = '#5294e2'
        element.color = color
        default_size = SHAPE_DEFAULT_SIZES.get(shape, (320, 200))
        element.width = _float(request.POST.get('width'), default_size[0])
        element.height = _float(request.POST.get('height'), default_size[1])
        if shape == 'square':
            element.width = element.height = max(element.width, element.height)
        if shape == 'line':
            element.width = max(element.width, 2)
            element.height = max(element.height, 2)
        element.outline_width = _float(request.POST.get('outline_width'), 6 if shape == 'line' else 0)
        outline_color = _clean_color(request.POST.get('outline_color'), allow_transparent=True)
        if outline_color:
            element.outline_color = outline_color
        element.x = _float(request.POST.get('x'), round((CANVAS_W - element.width) / 2, 2))
        element.y = _float(request.POST.get('y'), round((CANVAS_H - element.height) / 2, 2))
    else:
        text = (request.POST.get('text') or '').strip()
        if not text:
            return JsonResponse({'error': 'Text is required'}, status=400)
        element.text = text
        color = _clean_color(request.POST.get('color'), allow_transparent=True)
        if color is None:
            color = element.color
        element.color = color
        element.font_size = _float(request.POST.get('font_size'), 48)
        element.bold = _clean_bool(request.POST.get('bold'), element.bold)
        align = request.POST.get('align')
        if align in ThumbnailElement.ALIGN_CHOICES:
            element.align = align
        family = request.POST.get('font_family')
        if family in ThumbnailElement.FONT_CHOICES:
            element.font_family = family
        element.width = _float(request.POST.get('width'), 400)

    element.x = _float(request.POST.get('x'), element.x)
    element.y = _float(request.POST.get('y'), element.y)
    element.width = max(element.width, 8)
    if kind == ThumbnailElement.KIND_IMAGE:
        element.height = max(element.height, 8)
        element.brightness = _int(request.POST.get('brightness'), element.brightness)
        element.contrast = _int(request.POST.get('contrast'), element.contrast)
        element.saturation = _int(request.POST.get('saturation'), element.saturation)
    if kind == ThumbnailElement.KIND_SHAPE:
        element.height = max(element.height, 2)
    if kind == ThumbnailElement.KIND_TEXT:
        element.italic = _clean_bool(request.POST.get('italic'), element.italic)
        element.letter_spacing = _float(request.POST.get('letter_spacing'), element.letter_spacing)
        outline_color = _clean_color(request.POST.get('outline_color'), allow_transparent=True)
        if outline_color:
            element.outline_color = outline_color
        element.outline_width = _float(request.POST.get('outline_width'), element.outline_width)
        element.outline_width = min(max(element.outline_width, 0), 24)
    if kind == ThumbnailElement.KIND_SHAPE:
        outline_color = _clean_color(request.POST.get('outline_color'), allow_transparent=True)
        if outline_color:
            element.outline_color = outline_color
        element.outline_width = min(max(element.outline_width, 0), 60)
        element.border_radius = _float(request.POST.get('border_radius'), element.border_radius)
        element.border_radius = min(max(element.border_radius, 0), 200)
    element.rotation = _float(request.POST.get('rotation'), element.rotation)
    element.opacity = _float(request.POST.get('opacity'), element.opacity)
    element.flip_x = _clean_bool(request.POST.get('flip_x'), element.flip_x)
    element.flip_y = _clean_bool(request.POST.get('flip_y'), element.flip_y)
    if kind == ThumbnailElement.KIND_IMAGE:
        element.hue = _int(request.POST.get('hue'), element.hue)
        element.hue = min(max(element.hue, -180), 180)
        element.border_radius = _float(request.POST.get('border_radius'), element.border_radius)
        element.border_radius = min(max(element.border_radius, 0), 200)

    z_received = request.POST.get('z')
    max_z = thumb.elements.aggregate(max_z=Max('z_index'))['max_z'] or 0
    if z_received not in (None, ''):
        element.z_index = _int(z_received, max_z + 1)
    else:
        element.z_index = max_z + 1
    element.opacity = min(max(element.opacity, 0), 1)
    element.brightness = min(max(element.brightness, 0), 200)
    element.contrast = min(max(element.contrast, 0), 200)
    element.saturation = min(max(element.saturation, 0), 200)

    requested_id = _int(request.POST.get('id'), 0)
    if requested_id and not ThumbnailElement.objects.filter(pk=requested_id).exists():
        # Restoring an element that was deleted (undo/redo) keeps its identity.
        element.pk = requested_id

    try:
        with transaction.atomic():
            element.save()
    except IntegrityError:
        # The requested id collided with a row created in the meantime.
        element.pk = None
        element.save()

    return JsonResponse(_serialize(element))


@require_POST
def element_update(request):
    element_id = request.POST.get('id')
    elements = ThumbnailElement.objects.filter(pk=element_id)
    thumbnail_id = request.POST.get('thumbnail')
    if thumbnail_id:
        elements = elements.filter(thumbnail_id=thumbnail_id)
    element = elements.first()
    if element is None:
        return JsonResponse({'error': 'Element not found'}, status=404)

    if 'text' in request.POST:
        element.text = request.POST.get('text') or ''

    if 'shape' in request.POST and request.POST.get('shape') in ThumbnailElement.SHAPE_CHOICES:
        element.shape = request.POST.get('shape')

    if 'color' in request.POST:
        new_color = _clean_color(request.POST.get('color'), allow_transparent=True)
        if new_color is None:
            return JsonResponse({'error': 'Invalid color'}, status=400)
        if new_color:
            element.color = new_color
        elif element.kind == ThumbnailElement.KIND_SHAPE:
            element.color = ''

    for key in ('font_size', 'width', 'height'):
        if key in request.POST and request.POST.get(key) != '':
            setattr(element, key, max(_float(request.POST.get(key), getattr(element, key)), 8))

    if 'font_size' in request.POST and request.POST.get('font_size') != '':
        element.font_size = min(max(element.font_size, 8), 400)

    for key in ('x', 'y', 'rotation', 'opacity'):
        if key in request.POST and request.POST.get(key) != '':
            setattr(element, key, _float(request.POST.get(key), getattr(element, key)))

    for key in ('brightness', 'contrast', 'saturation', 'z'):
        field = 'z_index' if key == 'z' else key
        if key in request.POST and request.POST.get(key) != '':
            setattr(element, field, _int(request.POST.get(key), getattr(element, field)))

    if 'bold' in request.POST:
        element.bold = _clean_bool(request.POST.get('bold'), element.bold)
    if 'italic' in request.POST:
        element.italic = _clean_bool(request.POST.get('italic'), element.italic)

    if 'font_family' in request.POST and request.POST.get('font_family') in ThumbnailElement.FONT_CHOICES:
        element.font_family = request.POST.get('font_family')

    if 'letter_spacing' in request.POST and request.POST.get('letter_spacing') != '':
        element.letter_spacing = min(max(_float(request.POST.get('letter_spacing'), element.letter_spacing), -20), 200)

    if 'outline_color' in request.POST and (request.POST.get('outline_color') or '').strip():
        outline_color = _clean_color(request.POST.get('outline_color'), allow_transparent=True)
        if outline_color is None:
            return JsonResponse({'error': 'Invalid color'}, status=400)
        element.outline_color = outline_color

    if 'outline_width' in request.POST and request.POST.get('outline_width') != '':
        outline_limit = 60 if element.kind == ThumbnailElement.KIND_SHAPE else 24
        element.outline_width = min(max(_float(request.POST.get('outline_width'), element.outline_width), 0), outline_limit)

    if 'hue' in request.POST and request.POST.get('hue') != '':
        element.hue = min(max(_int(request.POST.get('hue'), element.hue), -180), 180)

    if 'border_radius' in request.POST and request.POST.get('border_radius') != '':
        element.border_radius = min(max(_float(request.POST.get('border_radius'), element.border_radius), 0), 200)

    if 'align' in request.POST and request.POST.get('align') in ThumbnailElement.ALIGN_CHOICES:
        element.align = request.POST.get('align')

    if 'flip_x' in request.POST:
        element.flip_x = _clean_bool(request.POST.get('flip_x'), element.flip_x)
    if 'flip_y' in request.POST:
        element.flip_y = _clean_bool(request.POST.get('flip_y'), element.flip_y)

    element.x = min(max(element.x, -CANVAS_W), CANVAS_W)
    element.y = min(max(element.y, -CANVAS_H), CANVAS_H)
    element.width = max(element.width, 8)
    if element.kind == ThumbnailElement.KIND_IMAGE:
        element.height = max(element.height, 8)
    if element.kind == ThumbnailElement.KIND_SHAPE:
        element.height = max(element.height, 2)
    element.opacity = min(max(element.opacity, 0), 1)
    element.brightness = min(max(element.brightness, 0), 200)
    element.contrast = min(max(element.contrast, 0), 200)
    element.saturation = min(max(element.saturation, 0), 200)

    element.save()
    return JsonResponse(_serialize(element))


@require_POST
def element_delete(request):
    element_id = request.POST.get('id')
    elements = ThumbnailElement.objects.filter(pk=element_id)
    thumbnail_id = request.POST.get('thumbnail')
    if thumbnail_id:
        elements = elements.filter(thumbnail_id=thumbnail_id)
    element = elements.first()
    if element is None:
        return JsonResponse({'error': 'Element not found'}, status=404)
    element.delete()
    return JsonResponse({'status': 'success'})

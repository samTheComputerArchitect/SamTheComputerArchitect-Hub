from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
import os

class Thumbnail(models.Model):
    name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    background_color = models.CharField(max_length=9, blank=True, default='#ffffff')

    def __str__(self):
        return self.name or f"Thumbnail {self.id}"

class ThumbnailElement(models.Model):
    KIND_IMAGE = 'image'
    KIND_TEXT = 'text'
    KIND_SHAPE = 'shape'
    KIND_CHOICES = [
        (KIND_IMAGE, 'Image'),
        (KIND_TEXT, 'Text'),
        (KIND_SHAPE, 'Shape'),
    ]
    SHAPE_CHOICES = [
        'triangle', 'line', 'rectangle', 'square', 'circle',
    ]

    ALIGN_CHOICES = ['left', 'center', 'right']
    FONT_CHOICES = [
        'JetBrains Mono', 'Arial', 'Verdana', 'Tahoma', 'Trebuchet MS',
        'Georgia', 'Times New Roman', 'Courier New', 'Impact', 'Comic Sans MS',
    ]

    thumbnail = models.ForeignKey(
        Thumbnail,
        on_delete=models.CASCADE,
        related_name='elements',
    )
    kind = models.CharField(max_length=8, choices=KIND_CHOICES, default=KIND_IMAGE)
    image = models.ImageField(upload_to='thumbnail_elements/', blank=True, null=True)
    shape = models.CharField(max_length=16, blank=True, default='rectangle')
    text = models.TextField(blank=True)
    color = models.CharField(max_length=16, default='#111111')
    font_size = models.FloatField(default=48)
    bold = models.BooleanField(default=False)
    align = models.CharField(max_length=8, default='left', choices=[(a, a) for a in ALIGN_CHOICES])
    font_family = models.CharField(max_length=64, default='JetBrains Mono')
    italic = models.BooleanField(default=False)
    letter_spacing = models.FloatField(default=0)
    outline_color = models.CharField(max_length=16, default='#000000')
    outline_width = models.FloatField(default=0)

    x = models.FloatField(default=0)
    y = models.FloatField(default=0)
    width = models.FloatField(default=200)
    height = models.FloatField(default=100)
    rotation = models.FloatField(default=0)
    opacity = models.FloatField(default=1)

    flip_x = models.BooleanField(default=False)
    flip_y = models.BooleanField(default=False)
    brightness = models.IntegerField(default=100)
    contrast = models.IntegerField(default=100)
    saturation = models.IntegerField(default=100)
    hue = models.IntegerField(default=0)
    border_radius = models.FloatField(default=0)

    z_index = models.IntegerField(default=0)

    def __str__(self):
        label = self.text[:30] if self.kind == self.KIND_TEXT else (self.name() or f'Element {self.id}')
        return f"{self.kind} of {self.thumbnail} — {label}"

    def name(self):
        if not self.image:
            return ''
        return self.image.name.rsplit('/', 1)[-1]

@receiver(post_delete, sender=ThumbnailElement)
def delete_element_file(sender, instance, **kwargs):
    if not instance.image:
        return
    name = instance.image.name
    # another element may still point at the same file - do not pull it out
    # from under them
    if ThumbnailElement.objects.filter(image=name).exists():
        return
    try:
        path = instance.image.path
    except (ValueError, NotImplementedError):
        return
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass

from django.db import models


class Notebook(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Section(models.Model):
    notebook = models.ForeignKey(
        Notebook,
        on_delete=models.CASCADE,
        related_name='sections',
    )
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['notebook', 'name'],
                name='unique_section_per_notebook',
            ),
        ]

    def __str__(self):
        return f'{self.notebook.name} - {self.name}'


class Tab(models.Model):
    section = models.ForeignKey(
        Section,
        on_delete=models.CASCADE,
        related_name='tabs',
    )
    name = models.CharField(max_length=100)
    pan_x = models.FloatField(default=0)
    pan_y = models.FloatField(default=0)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['section', 'name'],
                name='unique_tab_per_section',
            ),
        ]

    def __str__(self):
        return f'{self.section} - {self.name}'


class Note(models.Model):
    KIND_NOTE = 'note'
    KIND_HEADING_1 = 'h1'
    KIND_HEADING_2 = 'h2'
    KIND_HEADING_3 = 'h3'
    KIND_CHOICES = [
        (KIND_NOTE, 'Note'),
        (KIND_HEADING_1, 'Heading 1'),
        (KIND_HEADING_2, 'Heading 2'),
        (KIND_HEADING_3, 'Heading 3'),
    ]

    tab = models.ForeignKey(
        Tab,
        on_delete=models.CASCADE,
        related_name='notes',
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=8, choices=KIND_CHOICES, default=KIND_NOTE)
    text = models.TextField(blank=True)
    x = models.FloatField(default=0)
    y = models.FloatField(default=0)
    date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return self.text[:50] or f'Note {self.pk}'


class Drawing(models.Model):
    tab = models.ForeignKey(
        Tab,
        on_delete=models.CASCADE,
        related_name='drawings',
        null=True,
        blank=True,
    )
    color = models.CharField(max_length=7, default='#5294e2')
    width = models.FloatField(default=2)
    path = models.TextField()
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created']

    def __str__(self):
        return f'Drawing {self.pk}'


class CanvasImage(models.Model):
    tab = models.ForeignKey(
        Tab,
        on_delete=models.CASCADE,
        related_name='images',
        null=True,
        blank=True,
    )
    data = models.TextField()
    x = models.FloatField(default=0)
    y = models.FloatField(default=0)
    width = models.FloatField(default=200)
    height = models.FloatField(default=200)
    rotation = models.FloatField(default=0)
    z = models.IntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['z', 'created']

    def __str__(self):
        return f'Image {self.pk}'
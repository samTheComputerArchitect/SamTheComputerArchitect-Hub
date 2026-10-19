from django.db import models
from django.utils.text import slugify


class ResearchTag(models.Model):
    """A label that can be attached to research projects (AI, Math, ...)."""

    name = models.CharField(max_length=32, unique=True)
    slug = models.SlugField(max_length=32, unique=True, blank=True)
    color = models.CharField(max_length=16, default='#5294e2')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class ResearchProject(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_PAUSED = 'paused'
    STATUS_FINISHED = 'finished'
    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_PAUSED, 'Paused'),
        (STATUS_FINISHED, 'Finished'),
    ]
    STATUS_COLORS = {
        # red: it is being worked on right now
        STATUS_ACTIVE: '#e25252',
        # yellow: on hold
        STATUS_PAUSED: '#e2c452',
        # green: wrapped up
        STATUS_FINISHED: '#52c48a',
    }

    acronym = models.CharField(max_length=32)
    full_form = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    # the long form write up that lives on the project page
    details = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    tags = models.ManyToManyField(ResearchTag, related_name='projects', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['acronym', 'id']

    def __str__(self):
        return f'{self.acronym} — {self.full_form}'

    @property
    def status_color(self):
        return self.STATUS_COLORS.get(self.status, '#8a919a')


class Experiment(models.Model):
    """A single experiment that belongs to a research project."""

    project = models.ForeignKey(
        ResearchProject,
        on_delete=models.CASCADE,
        related_name='experiments',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    hypothesis = models.TextField(blank=True)
    conclusion = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return self.title


class ExperimentFile(models.Model):
    """A file that was uploaded as part of an experiment."""

    experiment = models.ForeignKey(
        Experiment,
        on_delete=models.CASCADE,
        related_name='files',
    )
    file = models.FileField(upload_to='research_experiments/')
    original_name = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.original_name or self.file.name.rsplit('/', 1)[-1]

    def save(self, *args, **kwargs):
        if not self.original_name and self.file:
            self.original_name = self.file.name.rsplit('/', 1)[-1]
        super().save(*args, **kwargs)

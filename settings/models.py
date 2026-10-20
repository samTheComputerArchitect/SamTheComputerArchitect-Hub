from django.db import models

class APIKey(models.Model):
    provider = models.CharField(max_length=100)
    key = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.provider} API Key"


class EditorSetting(models.Model):
    """Preferences for the editors that live in other apps.

    The paper editor of the research app reads these on load: whether the
    vim emulation is on at all and whether the standard hjkl motions stay
    mapped alongside the jkl; remap.
    """

    vim_mode = models.BooleanField(default=True)
    keep_hjkl = models.BooleanField(default=True)

    def __str__(self):
        return 'Editor settings'

    @classmethod
    def load(cls):
        """The single row, created with the defaults on first read."""
        row, _created = cls.objects.get_or_create(pk=1)
        return row


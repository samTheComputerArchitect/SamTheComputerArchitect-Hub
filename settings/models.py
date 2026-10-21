from django.db import models

class APIKey(models.Model):
    provider = models.CharField(max_length=100)
    key = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.provider} API Key"


class GoogleCredential(models.Model):
    """The oauth client of the hub and the tokens Google hands back.

    The client id and the secret are entered once on the settings page;
    the refresh token arrives when the owner connects the hub to Google
    from the meetings page, and lives here until they disconnect.
    """

    label = models.CharField(max_length=50, default='Google Meet', unique=True)
    client_id = models.CharField(max_length=200, blank=True, default='')
    client_secret = models.CharField(max_length=500, blank=True, default='')
    refresh_token = models.CharField(max_length=600, blank=True, default='')
    access_token = models.CharField(max_length=800, blank=True, default='')
    access_token_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.label

    @classmethod
    def load(cls):
        """The single row, created empty on first read."""
        row, _created = cls.objects.get_or_create(pk=1)
        return row


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


from django.db import models

class APIKey(models.Model):
    provider = models.CharField(max_length=100)
    key = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.provider} API Key"

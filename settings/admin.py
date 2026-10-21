from django.contrib import admin

from .models import APIKey, EditorSetting, GoogleCredential

admin.site.register(APIKey)
admin.site.register(GoogleCredential)
admin.site.register(EditorSetting)

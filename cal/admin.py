from django.contrib import admin

from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'start', 'end', 'repeat')
    list_filter = ('repeat',)
    search_fields = ('title',)

from django.contrib import admin

from .models import ResearchProject


@admin.register(ResearchProject)
class ResearchProjectAdmin(admin.ModelAdmin):
    list_display = ('acronym', 'full_form', 'created_at')
    search_fields = ('acronym', 'full_form', 'description')

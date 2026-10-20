from django.urls import path
from . import views

urlpatterns = [
    path('', views.settings, name='settings'),
    path('save-api-key/', views.save_api_key, name='save_api_key'),
    path('get-api-keys/', views.get_api_keys, name='get_api_keys'),
    path('editor-settings/', views.get_editor_settings, name='get_editor_settings'),
    path('save-editor-settings/', views.save_editor_settings, name='save_editor_settings'),
]

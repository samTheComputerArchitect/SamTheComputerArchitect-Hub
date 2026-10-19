from django.urls import path
from . import views

urlpatterns = [
    path('', views.thumbnails, name='thumbnails'),
    path('<int:thumb_id>/', views.editor, name='thumbnail_editor'),
    path('create/', views.create_thumbnail, name='create_thumbnail'),
    path('rename/', views.rename_thumbnail, name='rename_thumbnail'),
    path('background/update/', views.background_update, name='background_update'),
    path('delete/', views.delete_thumbnail, name='delete_thumbnail'),
    path('duplicate/', views.duplicate_thumbnail, name='duplicate_thumbnail'),
    path('elements/create/', views.element_create, name='element_create'),
    path('elements/update/', views.element_update, name='element_update'),
    path('elements/delete/', views.element_delete, name='element_delete'),
]

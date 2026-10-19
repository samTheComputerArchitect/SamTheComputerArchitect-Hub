from django.urls import path
from . import views

urlpatterns = [
    path('', views.notes, name='notes'),
    path('sections/create/', views.create_section, name='create_section'),
    path('tabs/create/', views.create_tab, name='create_tab'),
    path('tabs/rename/', views.rename_tab, name='rename_tab'),
    path('tabs/pan/', views.update_tab_pan, name='update_tab_pan'),
    path('tabs/delete/', views.delete_tab, name='delete_tab'),
    path('sections/rename/', views.rename_section, name='rename_section'),
    path('sections/delete/', views.delete_section, name='delete_section'),
    path('notebooks/create/', views.create_notebook, name='create_notebook'),
    path('notes/create/', views.save_note, name='save_note'),
    path('notes/delete/', views.delete_note, name='delete_note'),
    path('drawings/create/', views.save_drawing, name='save_drawing'),
    path('drawings/update/', views.update_drawing, name='update_drawing'),
    path('drawings/delete/', views.delete_drawing, name='delete_drawing'),
    path('images/create/', views.save_image, name='save_image'),
    path('images/delete/', views.delete_image, name='delete_image'),
]
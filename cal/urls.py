from django.urls import path

from . import views

urlpatterns = [
    path('', views.calendar_page, name='calendar'),
    path('events/create/', views.create_event, name='calendar_event_create'),
    path('events/<int:pk>/', views.update_event, name='calendar_event_update'),
]

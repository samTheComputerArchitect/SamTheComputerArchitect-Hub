from django.urls import path

from . import views

urlpatterns = [
    path('', views.meetings_page, name='meetings'),
    path('create/', views.create_meeting, name='meetings_create'),
    path('link/<int:pk>/', views.create_meet_link, name='meetings_link'),
    path('delete/<int:pk>/', views.delete_meeting, name='meetings_delete'),
    path('connect-google/', views.connect_google, name='meetings_connect'),
    path('oauth/callback/', views.oauth_callback, name='meetings_callback'),
    path('disconnect-google/', views.disconnect_google, name='meetings_disconnect'),
    path('<int:pk>/', views.meeting_page, name='meeting_page'),
    path('<int:pk>/signal/', views.meeting_signal, name='meeting_signal'),
    path('<int:pk>/send/', views.meeting_send, name='meeting_send'),
]

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('main.urls')),
    path('notes/', include('notes.urls')),
    path('videos/', include('videos.urls')),
    path('editing/', include('editing.urls')),
    path('thumbnails/', include('thumbnails.urls')),
    path('research/', include('research.urls')),
    path('settings/', include('settings.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

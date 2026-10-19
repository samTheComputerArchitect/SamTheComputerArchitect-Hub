from django.shortcuts import render

def videos(request):
    return render(request, 'videos/videos.html')
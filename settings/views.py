from django.shortcuts import render
from django.http import JsonResponse
from .models import APIKey

def settings(request):
    tab = request.GET.get('tab', 'api_keys')
    return render(request, 'settings/settings.html', {'active_tab': tab})

def get_api_keys(request):
    keys = APIKey.objects.all().values('provider', 'key')
    return JsonResponse(list(keys), safe=False)

def save_api_key(request):
    if request.method == 'POST':
        provider = request.POST.get('provider')
        key = request.POST.get('key')
        if not provider or not key:
            return JsonResponse({'error': 'Provider and key are required'}, status=400)
        
        apikey, created = APIKey.objects.update_or_create(
            provider=provider,
            defaults={'key': key}
        )
        return JsonResponse({'id': apikey.id, 'status': 'success'})
    return JsonResponse({'error': 'Invalid method'}, status=405)

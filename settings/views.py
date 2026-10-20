from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import APIKey, EditorSetting


VALID_TABS = ('api_keys', 'models', 'editor')


def editor_flag(value):
    """A posted toggle travels as 'true'/'false'."""
    return str(value or '').strip().lower() in ('true', 'on', '1', 'checked')


def get_editor_settings(request):
    setting = EditorSetting.load()
    return JsonResponse({
        'vim': setting.vim_mode,
        'hjkl': setting.keep_hjkl,
    })


@require_POST
def save_editor_settings(request):
    setting = EditorSetting.load()
    setting.vim_mode = editor_flag(request.POST.get('vim'))
    setting.keep_hjkl = editor_flag(request.POST.get('hjkl'))
    setting.save()
    return JsonResponse({'vim': setting.vim_mode, 'hjkl': setting.keep_hjkl, 'status': 'success'})


def settings(request):
    tab = request.GET.get('tab', 'api_keys')
    # An unknown tab used to render a completely blank page: every
    # .tab-content section stays display: none when no comparison matches.
    if tab not in VALID_TABS:
        tab = 'api_keys'
    return render(request, 'settings/settings.html', {'active_tab': tab})


def get_api_keys(request):
    keys = APIKey.objects.all().values('provider', 'key')
    return JsonResponse(list(keys), safe=False)


def save_api_key(request):
    if request.method == 'POST':
        provider = (request.POST.get('provider') or '').strip()
        key = (request.POST.get('key') or '').strip()
        if not provider or not key:
            return JsonResponse({'error': 'Provider and key are required'}, status=400)
        if len(provider) > APIKey._meta.get_field('provider').max_length:
            return JsonResponse({'error': 'Provider name is too long'}, status=400)
        if len(key) > APIKey._meta.get_field('key').max_length:
            return JsonResponse({'error': 'API key is too long'}, status=400)
        
        apikey = APIKey.objects.filter(provider__iexact=provider).first()
        if apikey is None:
            apikey = APIKey.objects.create(provider=provider, key=key)
        else:
            # the same provider in another spelling is the same provider:
            # two rows would leave the second one invisible in the ui
            apikey.provider = provider
            apikey.key = key
            apikey.save()
        return JsonResponse({'id': apikey.id, 'status': 'success'})
    return JsonResponse({'error': 'Invalid method'}, status=405)

from django.shortcuts import render

def editing(request):
    return render(request, 'editing/editing.html')
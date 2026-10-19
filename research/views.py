from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import ExperimentForm
from .models import Experiment, ExperimentFile, ResearchProject, ResearchTag

DESCRIPTION_LIMIT = 140
MAX_ACRONYM_LENGTH = 32
MAX_FULL_FORM_LENGTH = 255
MAX_QUERY_LENGTH = 100


def research(request):
    """The project list.

    Searching and filtering happen in the browser: the client asks for the
    same url with the filters applied and swaps the result area, so the
    address bar of the page never changes.
    """
    active_tag = (request.GET.get('tag') or '').strip()
    active_status = (request.GET.get('status') or '').strip()
    query = (request.GET.get('q') or '').strip()[:MAX_QUERY_LENGTH]

    if active_status and active_status not in dict(ResearchProject.STATUS_CHOICES):
        active_status = ''

    projects = ResearchProject.objects.prefetch_related('tags')
    if active_tag:
        projects = projects.filter(tags__slug=active_tag)
    if active_status:
        projects = projects.filter(status=active_status)
    if query:
        projects = projects.filter(
            Q(acronym__icontains=query)
            | Q(full_form__icontains=query)
            | Q(description__icontains=query)
        )
    projects = projects.distinct()

    tags = ResearchTag.objects.all()

    return render(request, 'research/research.html', {
        'projects': projects,
        'tags': tags,
        'description_limit': DESCRIPTION_LIMIT,
        'status_choices': ResearchProject.STATUS_CHOICES,
        'status_colors': ResearchProject.STATUS_COLORS,
        'active_tag': active_tag,
        'active_status': active_status,
        'query': query,
    })


def project_detail(request, pk):
    """Everything that belongs to a single research project."""
    project = get_object_or_404(ResearchProject, pk=pk)
    experiments = list(project.experiments.prefetch_related('files'))
    attachment_count = sum(len(experiment.files.all()) for experiment in experiments)
    return render(request, 'research/detail.html', {
        'project': project,
        'experiments': experiments,
        'attachment_count': attachment_count,
        'status_choices': ResearchProject.STATUS_CHOICES,
        'status_colors': ResearchProject.STATUS_COLORS,
    })


def paper(request, pk):
    """Placeholder for the research paper editor."""
    project = get_object_or_404(ResearchProject, pk=pk)
    return render(request, 'research/paper.html', {
        'project': project,
    })


def experiment_form(request, pk, experiment_id=None):
    """Create or edit an experiment of a project."""
    project = get_object_or_404(ResearchProject, pk=pk)
    experiment = None
    if experiment_id is not None:
        experiment = get_object_or_404(Experiment, pk=experiment_id, project=project)

    if request.method == 'POST':
        form = ExperimentForm(request.POST, request.FILES, instance=experiment)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.project = project
            saved.save()
            for upload in form.cleaned_data.get('attachments') or []:
                ExperimentFile.objects.create(experiment=saved, file=upload)
            return redirect('research_project', pk=project.pk)
    else:
        form = ExperimentForm(instance=experiment)

    return render(request, 'research/experiment_form.html', {
        'project': project,
        'experiment': experiment,
        'form': form,
        'is_edit': experiment is not None,
    })


@require_POST
def experiment_delete(request, pk, experiment_id):
    project = get_object_or_404(ResearchProject, pk=pk)
    experiment = get_object_or_404(Experiment, pk=experiment_id, project=project)
    experiment.delete()
    return redirect('research_project', pk=project.pk)


@require_POST
def create_project(request):
    acronym = (request.POST.get('acronym') or '').strip()[:MAX_ACRONYM_LENGTH]
    full_form = (request.POST.get('full_form') or '').strip()[:MAX_FULL_FORM_LENGTH]
    description = (request.POST.get('description') or '').strip()
    status = (request.POST.get('status') or ResearchProject.STATUS_ACTIVE).strip()
    if status not in dict(ResearchProject.STATUS_CHOICES):
        status = ResearchProject.STATUS_ACTIVE

    if not acronym or not full_form:
        return JsonResponse({'error': 'Acronym and full form are required'}, status=400)

    project = ResearchProject.objects.create(
        acronym=acronym,
        full_form=full_form,
        description=description,
        status=status,
    )

    selected = request.POST.getlist('tags')
    for tag in ResearchTag.objects.filter(slug__in=selected):
        project.tags.add(tag)

    return JsonResponse({'id': project.pk, 'acronym': project.acronym, 'status': project.status})


@require_POST
def update_project(request):
    project = ResearchProject.objects.filter(pk=request.POST.get('id')).first()
    if project is None:
        return JsonResponse({'error': 'Research project not found'}, status=404)

    status = (request.POST.get('status') or '').strip()
    if status:
        if status not in dict(ResearchProject.STATUS_CHOICES):
            return JsonResponse({'error': 'Invalid status'}, status=400)
        project.status = status
        project.save(update_fields=['status'])

    if 'tags' in request.POST:
        project.tags.clear()
        for tag in ResearchTag.objects.filter(slug__in=request.POST.getlist('tags')):
            project.tags.add(tag)

    return JsonResponse({
        'id': project.pk,
        'status': project.status,
        'status_color': project.status_color,
        'tags': [tag.slug for tag in project.tags.all()],
    })


@require_POST
def delete_project(request):
    project = ResearchProject.objects.filter(pk=request.POST.get('id')).first()
    if project is None:
        return JsonResponse({'error': 'Research project not found'}, status=404)
    project.delete()
    return JsonResponse({'status': 'success'})

import os
import re
import shutil
import subprocess
import tempfile
import time

from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import ExperimentForm
from .models import Experiment, ExperimentFile, ResearchPaper, ResearchProject, ResearchTag
from settings.models import EditorSetting

DESCRIPTION_LIMIT = 140
MAX_ACRONYM_LENGTH = 32
MAX_FULL_FORM_LENGTH = 255
MAX_QUERY_LENGTH = 100
MAX_DESCRIPTION_LENGTH = 20000

# the paper editor compiles through the system pdflatex; it is never allowed
# to run longer than this, whatever the source does
PAPER_COMPILE_TIMEOUT = 25
PAPER_MAX_ERRORS = 6
PAPER_MAX_SOURCE_LENGTH = 1_000_000
PAPER_SOURCE_TOO_LONG_MESSAGE = 'The paper is over the 1 MB limit; trim it before compiling'
MAX_CONCLUSION_LENGTH = 20000
# How much of a file the viewer shows; bigger files are cut and marked.
MAX_FILE_TEXT_BYTES = 512 * 1024

# The code mirror modes the file viewer can use, with the scripts they need
# (the order matters: xml and javascript come before htmlmixed).
CODE_MIRROR_MODES = {
    'python': ['mode/python/python.js'],
    'javascript': ['mode/javascript/javascript.js'],
    'json': ['mode/javascript/javascript.js'],
    'css': ['mode/css/css.js'],
    'htmlmixed': [
        'mode/xml/xml.js',
        'mode/javascript/javascript.js',
        'mode/htmlmixed/htmlmixed.js',
    ],
    'xml': ['mode/xml/xml.js'],
    'markdown': ['mode/xml/xml.js', 'mode/markdown/markdown.js'],
    'sql': ['mode/sql/sql.js'],
    'shell': ['mode/shell/shell.js'],
    'yaml': ['mode/yaml/yaml.js'],
    'clike': ['mode/clike/clike.js'],
    'php': ['mode/php/php.js'],
    'go': ['mode/go/go.js'],
    'rust': ['mode/rust/rust.js'],
    'stex': ['mode/stex/stex.js'],
    'diff': ['mode/diff/diff.js'],
    'toml': ['mode/toml/toml.js'],
    'properties': ['mode/properties/properties.js'],
    'ruby': ['mode/ruby/ruby.js'],
}

# Which mode belongs to which file extension.
FILE_EXTENSIONS = {
    '.py': 'python', '.pyi': 'python', '.pyw': 'python',
    '.ipynb': 'json', '.json': 'json', '.jsonl': 'json',
    '.js': 'javascript', '.mjs': 'javascript', '.cjs': 'javascript',
    '.ts': 'javascript', '.tsx': 'javascript', '.jsx': 'javascript',
    '.css': 'css', '.scss': 'css', '.less': 'css',
    '.html': 'htmlmixed', '.htm': 'htmlmixed', '.xhtml': 'htmlmixed',
    '.xml': 'xml', '.svg': 'xml', '.plist': 'xml',
    '.md': 'markdown', '.markdown': 'markdown', '.mdx': 'markdown',
    '.sql': 'sql', '.sqlite': 'sql',
    '.sh': 'shell', '.bash': 'shell', '.zsh': 'shell', '.fish': 'shell',
    '.yml': 'yaml', '.yaml': 'yaml',
    '.c': 'clike', '.h': 'clike', '.cpp': 'clike', '.cc': 'clike',
    '.hpp': 'clike', '.java': 'clike', '.cs': 'clike', '.kt': 'clike',
    '.scala': 'clike', '.dart': 'clike', '.groovy': 'clike',
    '.php': 'php', '.go': 'go', '.rs': 'rust', '.rb': 'ruby',
    '.tex': 'stex', '.latex': 'stex', '.sty': 'stex', '.cls': 'stex',
    '.diff': 'diff', '.patch': 'diff',
    '.toml': 'toml', '.ini': 'properties', '.cfg': 'properties',
    '.conf': 'properties', '.properties': 'properties', '.env': 'properties',
}


def file_mode_for(name):
    """The code mirror mode of a file name, or None for plain text."""
    extension = ''
    if '.' in name:
        extension = '.' + name.rsplit('.', 1)[-1].lower()
    return FILE_EXTENSIONS.get(extension)


def read_text_file(field_file):
    """Read a file as utf-8.

    Returns (text, truncated). The text is None when the file is not
    valid utf-8 - a picture or an archive has no text to show.
    """
    try:
        with field_file.open('rb') as handle:
            data = handle.read(MAX_FILE_TEXT_BYTES + 4)
    except (OSError, ValueError):
        return None, False

    truncated = len(data) > MAX_FILE_TEXT_BYTES
    if truncated:
        data = data[:MAX_FILE_TEXT_BYTES]

    try:
        return data.decode('utf-8'), truncated
    except UnicodeDecodeError:
        # the cut may have split a multi byte character at the end
        for cut in (1, 2, 3):
            try:
                return data[:-cut].decode('utf-8'), True
            except UnicodeDecodeError:
                continue
    return None, truncated



def safe_pk(value):
    """Parse a form value into an integer pk, or None when it is junk."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


_TEX_SPECIALS = {
    '\\': r'\textbackslash{}',
    '~': r'\textasciitilde{}',
    '^': r'\textasciicircum{}',
    '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#',
    '_': r'\_', '{': r'\{', '}': r'\}',
}


def _tex_escape(text):
    """Escape a string so it can be dropped inside a LaTeX command.

    One pass with a regex: the naive `str.replace` chain would re-escape
    the braces of `\\textbackslash{}` on the next call and render the
    raw command inside the compiled title.
    """
    return re.sub(r'[\\~^&%$#_{}]', lambda match: _TEX_SPECIALS[match.group(0)], text)


def paper_skeleton(project):
    """The document a first-time editor starts from.

    It is minimal but it compiles on the very first request, so the preview
    side is never empty while the editor still says nothing. The project
    name is escaped, because a title like `C#` would otherwise feed the
    unbalanced-brace soup of TeX and the first compile would fail.
    """
    return '\n'.join([
        r'\documentclass[11pt]{article}',
        r'\usepackage{amsmath}',
        r'\usepackage{amssymb}',
        r'\title{' + _tex_escape(project.acronym) + ' --- ' + _tex_escape(project.full_form) + '}',
        r'\author{}',
        r'\date{}',
        r'\begin{document}',
        r'\maketitle',
        '',
        r'\section{Introduction}',
        '',
        r'\end{document}',
        '',
    ])


def paper(request, pk):
    """The paper editor of a project.

    The left side is the editor, the right side shows the compiled pdf.
    The source is not edited through a form: it autosaves, which is why
    the view only has to create the paper on the very first visit.
    """
    project = get_object_or_404(ResearchProject, pk=pk)
    paper_obj, created = ResearchPaper.objects.get_or_create(project=project)
    if created:
        paper_obj.source = paper_skeleton(project)
        paper_obj.save()

    # the editor's keyboard behaviour lives in the settings app
    editor_setting = EditorSetting.load()
    return render(request, 'research/paper.html', {
        'project': project,
        'paper': paper_obj,
        'vim_flags': {
            'enabled': editor_setting.vim_mode,
            'keep_hjkl': editor_setting.keep_hjkl,
        },
    })


def _latex_errors(log):
    """Pull the actionable error lines out of a pdflatex log.

    With -file-line-error the interesting entries look like
    `.../main.tex:9: LaTeX Error: ...` - they carry the line number the
    editor should scroll to (with -output-directory the prefix is the
    absolute work path). Without one of those, plain `! ...` lines are
    the fallback.
    """
    targeted = []
    for match in re.finditer(r'^.*main\.tex:(\d+):(.*)$', log, re.MULTILINE):
        message = match.group(2).strip()
        if 'Fatal error occurred' in message:
            continue
        targeted.append({
            'line': int(match.group(1)),
            'message': message,
        })
    if targeted:
        return targeted[:PAPER_MAX_ERRORS]

    plain = []
    for match in re.finditer(r'^! .+$', log, re.MULTILINE):
        message = match.group(0)[2:].strip()
        if 'Fatal error occurred' in message:
            continue
        plain.append({'line': None, 'message': message})
    return plain[:PAPER_MAX_ERRORS]


def _latex_engine():
    """The engine that compiles the paper.

    lualatex understands utf-8 out of the box, so a paper may contain
    greek letters, dashes or any other non-ascii character. pdflatex
    stops with "Unicode character not set up for use with LaTeX" and is
    only the fallback for machines without lualatex.
    """
    if shutil.which('lualatex'):
        return 'lualatex'
    return 'pdflatex'


def _compile_latex(source):
    """Run the latex engine over the source in a throwaway directory.

    Returns (pdf_bytes, errors): exactly one of the two is meaningful.
    The document never escapes the work directory, shell escapes are off
    and the run is capped at PAPER_COMPILE_TIMEOUT seconds.

    A second pass runs only when the first pass wrote labels or citations
    into the aux file, because anything else that the engine resolves
    between passes is worth neither the time nor the complexity here.
    """
    workdir = tempfile.mkdtemp(prefix='paper-compile-')
    try:
        tex_path = os.path.join(workdir, 'main.tex')
        with open(tex_path, 'w', encoding='utf-8') as handle:
            handle.write(source if source.endswith('\n') else source + '\n')

        engine = _latex_engine()
        command = [
            engine,
            '-interaction=nonstopmode',
            '-halt-on-error',
            '-file-line-error',
            '-no-shell-escape',
            '-output-directory', workdir,
            'main.tex',
        ]
        # HOME inside the workdir keeps TeX's writable cache out of the
        # user's actual home while everything else stays on PATH
        environment = {
            'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
            'HOME': workdir,
        }

        deadline = time.monotonic() + PAPER_COMPILE_TIMEOUT
        log = ''
        pdf = None
        returncode = None
        for attempt in (1, 2):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if pdf:
                    # pass one already helped: never throw a good pdf away
                    return pdf, []
                return None, [{'line': None, 'message': 'Compilation timed out'}]
            try:
                proc = subprocess.run(
                    command,
                    cwd=workdir,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=round(remaining, 3),
                )
            except subprocess.TimeoutExpired:
                if pdf:
                    return pdf, []
                return None, [{'line': None, 'message': 'Compilation timed out'}]
            except OSError:
                # the engine is not installed, blocked or the environment is
                # broken - the response is still usable json for the editor
                return None, [
                    {'line': None, 'message': f'{engine} is not available on the server'},
                ]
            returncode = proc.returncode

            log_path = os.path.join(workdir, 'main.log')
            if os.path.exists(log_path):
                with open(log_path, encoding='utf-8', errors='replace') as handle:
                    log = handle.read()

            pdf_path = os.path.join(workdir, 'main.pdf')
            try:
                pdf_size = os.path.getsize(pdf_path)
            except OSError:
                pdf_size = 0
            if pdf_size == 0:
                if returncode == 0:
                    # pdflatex reports zero typeset pages: the document is
                    # empty, which is not a LaTeX error but still no pdf
                    return None, [{'line': None, 'message': 'The document has nothing to typeset inside \\begin{document}'}]
                # the log is the only place the real error lives
                return None, _latex_errors(log) or [
                    {'line': None, 'message': 'Compilation failed without a message'},
                ]

            with open(pdf_path, 'rb') as handle:
                pdf = handle.read()

            aux_path = os.path.join(workdir, 'main.aux')
            aux = ''
            if os.path.exists(aux_path):
                with open(aux_path, encoding='utf-8', errors='replace') as handle:
                    aux = handle.read()
            resolved = ('\\newlabel{' in aux or '\\bibcite{' in aux)
            if attempt == 1 and resolved:
                # one more pass fixes \references that pointed nowhere
                continue
            break
        return pdf, []
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@require_POST
def paper_compile(request, pk):
    """Autosave and compile in one round trip.

    The debounced editor request and the Compile button hit the same
    endpoint: the fresh source is stored, then compiled. The response is
    either the pdf bytes or the compile errors - never a redirect.
    """
    started = time.monotonic()
    project = get_object_or_404(ResearchProject, pk=pk)
    paper_obj = ResearchPaper.objects.filter(project=project).first()
    if paper_obj is None:
        paper_obj = ResearchPaper(project=project)

    # A request without a source is not an autosave: treating it as '' would
    # blank every line the editor holds whenever a stray form post arrives.
    if 'source' not in request.POST:
        return JsonResponse(
            {'errors': [{'line': None, 'message': 'The request carried no source'}]},
            status=400,
        )
    source = request.POST['source']
    if len(source) > PAPER_MAX_SOURCE_LENGTH:
        return JsonResponse(
            {'errors': [
                {'line': None, 'message': PAPER_SOURCE_TOO_LONG_MESSAGE},
            ]},
            status=400,
        )
    if source != paper_obj.source:
        paper_obj.source = source
        paper_obj.save()

    pdf, errors = _compile_latex(source)
    if pdf:
        response = HttpResponse(pdf, content_type='application/pdf')
        response['X-Compile-Seconds'] = f'{time.monotonic() - started:.1f}'
        return response
    return JsonResponse({'errors': errors}, status=400)


def experiment_file(request, pk, experiment_id, file_id):
    """One file of an experiment, shown in a code editor.

    The text is read on the server: a file that is not valid utf-8 (a
    picture, an archive) has no text to show and says so instead.
    """
    project = get_object_or_404(ResearchProject, pk=pk)
    experiment = get_object_or_404(Experiment, pk=experiment_id, project=project)
    experiment_file = get_object_or_404(
        ExperimentFile, pk=file_id, experiment=experiment
    )

    name = experiment_file.original_name or experiment_file.file.name.rsplit('/', 1)[-1]
    mode = file_mode_for(name)
    text, truncated = read_text_file(experiment_file.file)

    try:
        size = experiment_file.file.size
    except (OSError, ValueError):
        size = 0

    return render(request, 'research/experiment_file.html', {
        'project': project,
        'experiment': experiment,
        'experiment_file': experiment_file,
        'file_name': name,
        'file_size': size,
        'file_text': text,
        'file_truncated': truncated,
        'file_mode': mode or 'null',
        'mode_scripts': CODE_MIRROR_MODES.get(mode, []),
    })


def experiment_view(request, pk, experiment_id):
    """The read-only page of an experiment: every detail in one place.

    Clicking an experiment card lands here. The page only shows what the
    experiment holds - the write-up, the expectation, the conclusion and
    the files - and links to the places where something can be changed.
    """
    project = get_object_or_404(ResearchProject, pk=pk)
    experiment = get_object_or_404(Experiment, pk=experiment_id, project=project)
    return render(request, 'research/experiment_view.html', {
        'project': project,
        'experiment': experiment,
    })


def experiment_detail(request, pk, experiment_id):
    """The conclusion of an experiment - one field, one job.

    Clicking an experiment card lands here, because a conclusion is the one
    thing you write once the experiment has actually run. Everything else lives
    on the full edit page.
    """
    project = get_object_or_404(ResearchProject, pk=pk)
    experiment = get_object_or_404(Experiment, pk=experiment_id, project=project)

    conclusion_error = ''
    conclusion_draft = ''
    if request.method == 'POST':
        conclusion = (request.POST.get('conclusion') or '').strip()
        if len(conclusion) > MAX_CONCLUSION_LENGTH:
            # The conclusion is written on a plain form, so the answer is
            # the page again with a message - not a json error. The text
            # the user typed stays in the box.
            conclusion_error = (
                f'The conclusion is longer than {MAX_CONCLUSION_LENGTH} characters.'
            )
            conclusion_draft = conclusion
        else:
            experiment.conclusion = conclusion
            experiment.save(update_fields=['conclusion', 'updated_at'])
            return redirect('research_project', pk=project.pk)

    return render(request, 'research/experiment.html', {
        'project': project,
        'experiment': experiment,
        'conclusion_error': conclusion_error,
        'conclusion_draft': conclusion_draft,
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
            # The checkboxes in the form let attachments be removed on edit;
            # only delete rows that really belong to this experiment.
            remove_ids = [
                pk for pk in (
                    safe_pk(value) for value in request.POST.getlist('remove_files')
                )
                if pk
            ]
            if remove_ids:
                saved.files.filter(pk__in=remove_ids).delete()
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
        'allowed_extensions': ', '.join(sorted(ExperimentForm.allowed_extensions)),
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
    description = (request.POST.get('description') or '').strip()[:MAX_DESCRIPTION_LENGTH]
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
    project = ResearchProject.objects.filter(pk=safe_pk(request.POST.get('id'))).first()
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
    project = ResearchProject.objects.filter(pk=safe_pk(request.POST.get('id'))).first()
    if project is None:
        return JsonResponse({'error': 'Research project not found'}, status=404)
    project.delete()
    return JsonResponse({'status': 'success'})

from django import forms

from .models import Experiment

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    'pdf', 'txt', 'md', 'csv', 'json', 'log', 'py', 'ipynb', 'png', 'jpg',
    'jpeg', 'gif', 'webp', 'svg', 'zip', 'tar', 'gz', 'xlsx', 'docx', 'mp4',
    'mov', 'wav',
}


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """A file field that accepts any number of files in one go."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        if not data and initial:
            return initial
        if not data:
            return []
        if not isinstance(data, (list, tuple)):
            data = [data]
        single = super().clean
        cleaned = []
        for item in data:
            if not item:
                continue
            cleaned.append(single(item, None))
        return cleaned


def validate_upload(upload):
    """Reject oversized files and block dangerous extensions."""
    name = getattr(upload, 'name', '') or ''
    extension = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    if extension and extension not in ALLOWED_EXTENSIONS:
        raise forms.ValidationError(f'"{extension}" files are not allowed.')
    size = getattr(upload, 'size', 0) or 0
    if size > MAX_UPLOAD_BYTES:
        raise forms.ValidationError(
            f'"{name}" is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.'
        )
    return upload


class ExperimentForm(forms.ModelForm):
    # validated in clean_title so a whitespace only title gets a clear message
    title = forms.CharField(max_length=200, required=False)
    attachments = MultipleFileField(required=False)

    class Meta:
        model = Experiment
        fields = ['title', 'description', 'hypothesis', 'conclusion']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 6}),
            'hypothesis': forms.Textarea(attrs={'rows': 5}),
            'conclusion': forms.Textarea(attrs={'rows': 5}),
        }

    def clean_title(self):
        title = (self.cleaned_data.get('title') or '').strip()
        if not title:
            raise forms.ValidationError('A title is required.')
        return title

    def clean_attachments(self):
        uploads = self.cleaned_data.get('attachments') or []
        for upload in uploads:
            validate_upload(upload)
        return uploads

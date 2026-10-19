from django.db import migrations


def seed(apps, schema_editor):
    Notebook = apps.get_model('notes', 'Notebook')
    Section = apps.get_model('notes', 'Section')
    for notebook in Notebook.objects.all():
        for name in ('General', 'Misc'):
            Section.objects.get_or_create(notebook=notebook, name=name)


def unseed(apps, schema_editor):
    Section = apps.get_model('notes', 'Section')
    Section.objects.filter(name__in=('General', 'Misc')).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('notes', '0003_section'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
from django.db import migrations


def seed(apps, schema_editor):
    Notebook = apps.get_model('notes', 'Notebook')
    for name in ('Ideas', 'School'):
        Notebook.objects.get_or_create(name=name)


def unseed(apps, schema_editor):
    Notebook = apps.get_model('notes', 'Notebook')
    Notebook.objects.filter(name__in=('Ideas', 'School')).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('notes', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
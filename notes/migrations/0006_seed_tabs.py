from django.db import migrations

TAB_NAMES = ('Tab 1', 'Tab 2')


def seed(apps, schema_editor):
    Section = apps.get_model('notes', 'Section')
    Tab = apps.get_model('notes', 'Tab')
    for section in Section.objects.all():
        for name in TAB_NAMES:
            Tab.objects.get_or_create(section=section, name=name)


def unseed(apps, schema_editor):
    Tab = apps.get_model('notes', 'Tab')
    Tab.objects.filter(name__in=TAB_NAMES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('notes', '0005_tab'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
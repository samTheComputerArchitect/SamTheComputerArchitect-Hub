from django.db import migrations

# A colour per tag that actually says something about the field.
TAG_COLORS = {
    'ai': '#9a52e2',        # purple - machine intelligence
    'math': '#4fc3e2',      # cyan - theory
    'software': '#5294e2',  # blue - code (the site primary)
    'other': '#8a919a',     # grey - everything else
}


def update_tag_colors(apps, schema_editor):
    ResearchTag = apps.get_model('research', 'ResearchTag')
    for slug, color in TAG_COLORS.items():
        ResearchTag.objects.filter(slug=slug).update(color=color)


def restore_tag_colors(apps, schema_editor):
    ResearchTag = apps.get_model('research', 'ResearchTag')
    previous = {
        'ai': '#9a52e2',
        'math': '#52e27a',
        'software': '#5294e2',
        'other': '#8a919a',
    }
    for slug, color in previous.items():
        ResearchTag.objects.filter(slug=slug).update(color=color)


class Migration(migrations.Migration):

    dependencies = [
        ('research', '0002_researchtag_researchproject_status_and_more'),
    ]

    operations = [
        migrations.RunPython(update_tag_colors, restore_tag_colors),
    ]

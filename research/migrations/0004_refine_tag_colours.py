from django.db import migrations

# A restrained, professional palette: soft violet, muted teal, the site blue
# and a neutral grey. All of them sit quietly on the dark background.
TAG_COLORS = {
    'ai': '#9b8cf7',
    'math': '#4fb3a5',
    'software': '#5294e2',
    'other': '#8b9098',
}

PREVIOUS_COLORS = {
    'ai': '#9a52e2',
    'math': '#4fc3e2',
    'software': '#5294e2',
    'other': '#8a919a',
}


def update_tag_colors(apps, schema_editor):
    ResearchTag = apps.get_model('research', 'ResearchTag')
    for slug, color in TAG_COLORS.items():
        ResearchTag.objects.filter(slug=slug).update(color=color)


def restore_tag_colors(apps, schema_editor):
    ResearchTag = apps.get_model('research', 'ResearchTag')
    for slug, color in PREVIOUS_COLORS.items():
        ResearchTag.objects.filter(slug=slug).update(color=color)


class Migration(migrations.Migration):

    dependencies = [
        ('research', '0003_update_tag_colours'),
    ]

    operations = [
        migrations.RunPython(update_tag_colors, restore_tag_colors),
    ]

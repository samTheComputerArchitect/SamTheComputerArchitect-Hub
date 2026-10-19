from django.db import migrations

# A bold, high contrast palette. The hues sit far apart from each other and
# from the status colours (red / yellow / green), so a tag can never be
# mistaken for a status.
TAG_COLORS = {
    'ai': '#c084fc',        # violet
    'math': '#22d3ee',      # electric cyan
    'software': '#f97316',  # orange
    'other': '#f472b6',     # rose
}

PREVIOUS_COLORS = {
    'ai': '#9b8cf7',
    'math': '#4fb3a5',
    'software': '#5294e2',
    'other': '#8b9098',
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
        ('research', '0004_refine_tag_colours'),
    ]

    operations = [
        migrations.RunPython(update_tag_colors, restore_tag_colors),
    ]

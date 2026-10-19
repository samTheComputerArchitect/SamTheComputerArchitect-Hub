from django.db import migrations

# A warm, earthy palette: copper, sage, steel blue and stone. No pinks, no
# purples and no electric cyans - and every hue sits far enough from the
# status colours (red / yellow / green) to never be mistaken for one.
TAG_COLORS = {
    'ai': '#e07a3f',        # copper
    'math': '#7d9b76',      # sage
    'software': '#4a7fb5',  # steel blue
    'other': '#8d8b7f',     # warm stone
}

PREVIOUS_COLORS = {
    'ai': '#c084fc',
    'math': '#22d3ee',
    'software': '#f97316',
    'other': '#f472b6',
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
        ('research', '0005_vivid_tag_colours'),
    ]

    operations = [
        migrations.RunPython(update_tag_colors, restore_tag_colors),
    ]

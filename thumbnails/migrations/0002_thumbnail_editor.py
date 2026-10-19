from django.db import migrations, models
import django.db.models.deletion


CANVAS_W = 1280
CANVAS_H = 720


def forward(apps, schema_editor):
    Thumbnail = apps.get_model('thumbnails', 'Thumbnail')
    Element = apps.get_model('thumbnails', 'ThumbnailElement')

    for thumb in Thumbnail.objects.all():
        img = thumb.image
        if not img:
            continue

        w, h = float(CANVAS_W), float(CANVAS_H)
        x = y = 0.0
        try:
            from PIL import Image
            with Image.open(img.path) as im:
                nat_w, nat_h = im.size
            scale = min(1.0, CANVAS_W / nat_w, CANVAS_H / nat_h)
            w = nat_w * scale
            h = nat_h * scale
            x = (CANVAS_W - w) / 2
            y = (CANVAS_H - h) / 2
        except Exception:
            pass

        Element.objects.create(
            thumbnail=thumb,
            kind='image',
            image=img,
            x=round(x, 2),
            y=round(y, 2),
            width=round(w, 2),
            height=round(h, 2),
            z_index=0,
        )


def backward(apps, schema_editor):
    raise migrations.IrreversibleError(
        'Thumbnail content cannot be restored into the removed image column.'
    )


class Migration(migrations.Migration):

    dependencies = [
        ('thumbnails', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='thumbnailelement',
            name='kind',
            field=models.CharField(choices=[('image', 'Image'), ('text', 'Text')], default='image', max_length=8),
        ),
        migrations.AddField(
            model_name='thumbnailelement',
            name='text',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='thumbnailelement',
            name='color',
            field=models.CharField(default='#111111', max_length=7),
        ),
        migrations.AddField(
            model_name='thumbnailelement',
            name='font_size',
            field=models.FloatField(default=48),
        ),
        migrations.AddField(
            model_name='thumbnailelement',
            name='bold',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='thumbnailelement',
            name='rotation',
            field=models.FloatField(default=0),
        ),
        migrations.AddField(
            model_name='thumbnailelement',
            name='opacity',
            field=models.FloatField(default=1),
        ),
        migrations.AddField(
            model_name='thumbnailelement',
            name='flip_x',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='thumbnailelement',
            name='flip_y',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='thumbnailelement',
            name='brightness',
            field=models.IntegerField(default=100),
        ),
        migrations.AddField(
            model_name='thumbnailelement',
            name='contrast',
            field=models.IntegerField(default=100),
        ),
        migrations.AddField(
            model_name='thumbnailelement',
            name='saturation',
            field=models.IntegerField(default=100),
        ),
        migrations.AddField(
            model_name='thumbnailelement',
            name='align',
            field=models.CharField(choices=[('left', 'left'), ('center', 'center'), ('right', 'right')], default='left', max_length=8),
        ),
        migrations.AlterField(
            model_name='thumbnailelement',
            name='image',
            field=models.ImageField(blank=True, null=True, upload_to='thumbnail_elements/'),
        ),
        migrations.AlterField(
            model_name='thumbnailelement',
            name='width',
            field=models.FloatField(default=200),
        ),
        migrations.RunPython(forward, backward),
        migrations.RemoveField(
            model_name='thumbnail',
            name='image',
        ),
    ]

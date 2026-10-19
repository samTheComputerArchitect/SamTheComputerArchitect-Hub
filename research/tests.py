import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Experiment, ExperimentFile, ResearchProject, ResearchTag


class TempMediaRootMixin:
    """Keep the test uploads out of the real media folder."""

    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp(prefix='hub-test-media-')
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)


class ResearchViewTests(TempMediaRootMixin, TestCase):
    def setUp(self):
        self.tags = {}
        for name, slug, color in [
            ('AI', 'ai', '#9a52e2'),
            ('Math', 'math', '#52e27a'),
            ('Software', 'software', '#5294e2'),
            ('Other', 'other', '#8a919a'),
        ]:
            # the data migration already seeds the default tags
            tag, _created = ResearchTag.objects.get_or_create(
                slug=slug,
                defaults={'name': name, 'color': color},
            )
            self.tags[slug] = tag

    def make_project(self, acronym='ALPHA', status=ResearchProject.STATUS_ACTIVE,
                     tags=(), full_form=None, description='A description.'):
        project = ResearchProject.objects.create(
            acronym=acronym,
            full_form=full_form if full_form is not None else f'{acronym} full form',
            description=description,
            status=status,
        )
        for tag in tags:
            project.tags.add(self.tags[tag])
        return project

    # ------------------------------------------------------------------ page
    def test_research_page_renders(self):
        self.make_project(tags=['ai'])
        response = self.client.get(reverse('research'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ALPHA')
        self.assertContains(response, 'ALPHA full form')

    def test_research_page_is_empty_without_projects(self):
        response = self.client.get(reverse('research'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No research projects yet')

    def test_page_shows_tags_and_status(self):
        self.make_project(tags=['ai', 'math'], status=ResearchProject.STATUS_PAUSED)
        response = self.client.get(reverse('research'))
        self.assertContains(response, 'research-tag')
        self.assertContains(response, 'data-status="paused"')

    def test_filter_by_tag(self):
        self.make_project(acronym='ALPHA', tags=['ai'])
        self.make_project(acronym='BETA', tags=['math'])
        response = self.client.get(reverse('research'), {'tag': 'ai'})
        self.assertContains(response, 'ALPHA')
        self.assertNotContains(response, 'BETA')

    def test_filter_by_status(self):
        self.make_project(acronym='ALPHA', status=ResearchProject.STATUS_ACTIVE)
        self.make_project(acronym='BETA', status=ResearchProject.STATUS_FINISHED)
        response = self.client.get(reverse('research'), {'status': 'finished'})
        self.assertContains(response, 'BETA')
        self.assertNotContains(response, 'ALPHA')

    def test_filter_by_tag_and_status(self):
        self.make_project(acronym='ALPHA', status=ResearchProject.STATUS_ACTIVE, tags=['ai'])
        self.make_project(acronym='BETA', status=ResearchProject.STATUS_FINISHED, tags=['ai'])
        response = self.client.get(reverse('research'), {'tag': 'ai', 'status': 'finished'})
        self.assertContains(response, 'BETA')
        self.assertNotContains(response, 'ALPHA')

    def test_unknown_tag_filter_returns_nothing(self):
        self.make_project(tags=['ai'])
        response = self.client.get(reverse('research'), {'tag': 'does-not-exist'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'ALPHA')

    def test_invalid_status_filter_is_ignored(self):
        self.make_project(acronym='ALPHA')
        response = self.client.get(reverse('research'), {'status': 'bogus'})
        self.assertContains(response, 'ALPHA')

    # ---------------------------------------------------------------- search
    def test_search_matches_the_acronym(self):
        self.make_project(acronym='Transformer', full_form='A block')
        self.make_project(acronym='Convolution', full_form='A filter')
        response = self.client.get(reverse('research'), {'q': 'transform'})
        self.assertContains(response, 'Transformer')
        self.assertNotContains(response, 'Convolution')

    def test_search_matches_the_full_form(self):
        self.make_project(acronym='ALPHA', full_form='Recursive Transformer Block')
        self.make_project(acronym='BETA', full_form='Convolutional Filter')
        response = self.client.get(reverse('research'), {'q': 'convolutional'})
        self.assertContains(response, 'BETA')
        self.assertNotContains(response, 'ALPHA')

    def test_search_matches_the_description(self):
        self.make_project(acronym='ALPHA', description='attention layers and tokens')
        self.make_project(acronym='BETA', description='nothing to see here')
        response = self.client.get(reverse('research'), {'q': 'attention'})
        self.assertContains(response, 'ALPHA')
        self.assertNotContains(response, 'BETA')

    def test_search_is_case_insensitive(self):
        self.make_project(acronym='ALPHA', full_form='Recursive Transformer Block')
        response = self.client.get(reverse('research'), {'q': 'TRANSFORMER'})
        self.assertContains(response, 'ALPHA')

    def test_search_with_no_match(self):
        self.make_project(acronym='ALPHA')
        response = self.client.get(reverse('research'), {'q': 'zzz-not-here'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'ALPHA')
        self.assertContains(response, 'No projects match')

    def test_search_combines_with_the_tag_filter(self):
        self.make_project(acronym='ALPHA', tags=['ai'], full_form='Shared title')
        self.make_project(acronym='BETA', tags=['math'], full_form='Shared title')
        response = self.client.get(reverse('research'), {'q': 'shared', 'tag': 'math'})
        self.assertNotContains(response, 'ALPHA')
        self.assertContains(response, 'BETA')

    def test_search_combines_with_the_status_filter(self):
        self.make_project(acronym='ALPHA', status=ResearchProject.STATUS_ACTIVE, full_form='Shared title')
        self.make_project(acronym='BETA', status=ResearchProject.STATUS_FINISHED, full_form='Shared title')
        response = self.client.get(reverse('research'), {'q': 'shared', 'status': 'finished'})
        self.assertNotContains(response, 'ALPHA')
        self.assertContains(response, 'BETA')

    def test_filter_links_keep_the_search_query(self):
        self.make_project(acronym='ALPHA', tags=['ai'])
        response = self.client.get(reverse('research'), {'q': 'alpha'})
        self.assertContains(response, 'data-filter-tag="ai"')

    # ---------------------------------------------------------------- create
    def test_create_project(self):
        response = self.client.post(reverse('research_create'), {
            'acronym': 'BETA',
            'full_form': 'Reduced Instruction Set Computer',
            'description': 'A small instruction set design.',
        })
        self.assertEqual(response.status_code, 200)
        project = ResearchProject.objects.get()
        self.assertEqual(project.acronym, 'BETA')
        self.assertEqual(project.full_form, 'Reduced Instruction Set Computer')
        self.assertEqual(project.status, ResearchProject.STATUS_ACTIVE)

    def test_create_project_with_tags_and_status(self):
        response = self.client.post(reverse('research_create'), {
            'acronym': 'LLVM',
            'full_form': 'Low Level Virtual Machine',
            'status': 'paused',
            'tags': ['ai', 'software'],
        })
        self.assertEqual(response.status_code, 200)
        project = ResearchProject.objects.get()
        self.assertEqual(project.status, ResearchProject.STATUS_PAUSED)
        self.assertEqual(
            sorted(project.tags.values_list('slug', flat=True)),
            ['ai', 'software'],
        )

    def test_create_project_rejects_unknown_status(self):
        self.client.post(reverse('research_create'), {
            'acronym': 'X',
            'full_form': 'X',
            'status': 'bogus',
        })
        self.assertEqual(ResearchProject.objects.get().status, ResearchProject.STATUS_ACTIVE)

    def test_create_project_requires_acronym_and_full_form(self):
        response = self.client.post(reverse('research_create'), {
            'acronym': '  ',
            'full_form': '',
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ResearchProject.objects.exists())

    # ---------------------------------------------------------------- update
    def test_update_status(self):
        project = self.make_project()
        response = self.client.post(reverse('research_update'), {
            'id': project.pk,
            'status': 'paused',
        })
        self.assertEqual(response.status_code, 200)
        project.refresh_from_db()
        self.assertEqual(project.status, ResearchProject.STATUS_PAUSED)
        self.assertEqual(response.json()['status'], 'paused')

    def test_update_status_rejects_invalid_status(self):
        project = self.make_project()
        response = self.client.post(reverse('research_update'), {
            'id': project.pk,
            'status': 'bogus',
        })
        self.assertEqual(response.status_code, 400)
        project.refresh_from_db()
        self.assertEqual(project.status, ResearchProject.STATUS_ACTIVE)

    def test_update_unknown_project(self):
        response = self.client.post(reverse('research_update'), {'id': 999999, 'status': 'active'})
        self.assertEqual(response.status_code, 404)

    def test_update_tags(self):
        project = self.make_project(tags=['ai'])
        response = self.client.post(reverse('research_update'), {
            'id': project.pk,
            'tags': ['math'],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(project.tags.values_list('slug', flat=True)),
            ['math'],
        )

    # ---------------------------------------------------------------- delete
    def test_delete_project(self):
        project = self.make_project()
        response = self.client.post(reverse('research_delete'), {'id': project.pk})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ResearchProject.objects.filter(pk=project.pk).exists())

    def test_delete_unknown_project(self):
        response = self.client.post(reverse('research_delete'), {'id': 999999})
        self.assertEqual(response.status_code, 404)

    def test_endpoints_reject_get(self):
        for name in ('research_create', 'research_update', 'research_delete'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 405, name)

    # ----------------------------------------------------------------- model
    def test_tag_slug_is_generated(self):
        tag = ResearchTag.objects.create(name='Signal Processing')
        self.assertEqual(tag.slug, 'signal-processing')

    def test_status_color_is_defined_for_every_status(self):
        for value, _label in ResearchProject.STATUS_CHOICES:
            project = ResearchProject(status=value)
            self.assertTrue(project.status_color.startswith('#'))

    def test_status_colors_are_meaningful(self):
        colors = ResearchProject.STATUS_COLORS
        self.assertEqual(colors[ResearchProject.STATUS_ACTIVE], '#e25252')
        self.assertEqual(colors[ResearchProject.STATUS_PAUSED], '#e2c452')
        self.assertEqual(colors[ResearchProject.STATUS_FINISHED], '#52c48a')

    def test_every_tag_has_its_own_colour(self):
        colours = set(ResearchTag.objects.values_list('color', flat=True))
        self.assertEqual(len(colours), ResearchTag.objects.count())
        for colour in colours:
            self.assertTrue(colour.startswith('#'))
            self.assertEqual(len(colour), 7)

    def test_tag_colours_are_the_earthy_palette(self):
        self.assertEqual(ResearchTag.objects.get(slug='ai').color, '#e07a3f')
        self.assertEqual(ResearchTag.objects.get(slug='math').color, '#7d9b76')
        self.assertEqual(ResearchTag.objects.get(slug='software').color, '#4a7fb5')
        self.assertEqual(ResearchTag.objects.get(slug='other').color, '#8d8b7f')

    def test_tag_colours_avoid_pink_purple_and_cyan(self):
        def hue(value):
            value = value.lstrip('#')
            r, g, b = (int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))
            import colorsys
            return colorsys.rgb_to_hsv(r, g, b)[0] * 360

        for colour in ResearchTag.objects.values_list('color', flat=True):
            h = hue(colour)
            self.assertFalse(300 <= h <= 360 or 0 <= h <= 12, colour)   # pink / rose
            self.assertFalse(255 <= h <= 300, colour)                   # purple / violet
            self.assertFalse(175 <= h <= 210, colour)                  # cyan

    def test_tag_colours_do_not_collide_with_the_status_colours(self):
        status_colours = set(ResearchProject.STATUS_COLORS.values())
        for colour in ResearchTag.objects.values_list('color', flat=True):
            self.assertNotIn(colour, status_colours)


class ProjectPageTests(TempMediaRootMixin, TestCase):
    def setUp(self):
        self.project = ResearchProject.objects.create(
            acronym='ALPHA',
            full_form='Alpha Project',
            description='A short description.',
            details='A much longer write up of the project.',
        )

    def test_project_page_renders(self):
        response = self.client.get(reverse('research_project', args=[self.project.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'ALPHA')
        self.assertContains(response, 'Alpha Project')
        self.assertContains(response, 'A much longer write up of the project.')

    def test_project_page_links_to_the_paper_and_experiment_pages(self):
        response = self.client.get(reverse('research_project', args=[self.project.pk]))
        self.assertContains(response, reverse('research_paper', args=[self.project.pk]))
        self.assertContains(response, reverse('research_experiment_create', args=[self.project.pk]))

    def test_project_page_404s_for_a_missing_project(self):
        response = self.client.get(reverse('research_project', args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_cards_link_to_the_project_page(self):
        response = self.client.get(reverse('research'))
        self.assertContains(response, reverse('research_project', args=[self.project.pk]))

    def test_paper_page_renders_the_placeholder(self):
        response = self.client.get(reverse('research_paper', args=[self.project.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Create your research paper here')

    def test_paper_page_404s_for_a_missing_project(self):
        response = self.client.get(reverse('research_paper', args=[999999]))
        self.assertEqual(response.status_code, 404)


class ExperimentTests(TempMediaRootMixin, TestCase):
    def setUp(self):
        self.project = ResearchProject.objects.create(
            acronym='ALPHA',
            full_form='Alpha Project',
        )

    def test_experiment_form_renders(self):
        response = self.client.get(reverse('research_experiment_create', args=[self.project.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hypothesis')
        self.assertContains(response, 'Description')

    def test_create_experiment(self):
        response = self.client.post(
            reverse('research_experiment_create', args=[self.project.pk]),
            {
                'title': 'First run',
                'description': 'What I did',
                'hypothesis': 'What I expected',
                'conclusion': 'What happened',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('research_project', args=[self.project.pk]))
        experiment = Experiment.objects.get()
        self.assertEqual(experiment.title, 'First run')
        self.assertEqual(experiment.hypothesis, 'What I expected')
        self.assertEqual(experiment.project, self.project)

    def test_create_experiment_requires_a_title(self):
        response = self.client.post(
            reverse('research_experiment_create', args=[self.project.pk]),
            {'title': '   ', 'description': 'x'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Experiment.objects.exists())
        self.assertContains(response, 'A title is required.')

    def test_create_experiment_with_files(self):
        upload = SimpleUploadedFile('notes.txt', b'hello world', content_type='text/plain')
        response = self.client.post(
            reverse('research_experiment_create', args=[self.project.pk]),
            {
                'title': 'With files',
                'attachments': [upload],
            },
        )
        self.assertEqual(response.status_code, 302)
        experiment = Experiment.objects.get()
        self.assertEqual(experiment.files.count(), 1)
        self.assertEqual(experiment.files.first().original_name, 'notes.txt')

    def test_create_experiment_rejects_disallowed_file_types(self):
        upload = SimpleUploadedFile('payload.exe', b'MZ', content_type='application/octet-stream')
        response = self.client.post(
            reverse('research_experiment_create', args=[self.project.pk]),
            {
                'title': 'Bad file',
                'attachments': [upload],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Experiment.objects.exists())
        self.assertContains(response, 'not allowed')

    def test_experiment_shows_on_the_project_page(self):
        experiment = Experiment.objects.create(
            project=self.project,
            title='Visible experiment',
            hypothesis='The hypothesis text',
            conclusion='The conclusion text',
        )
        response = self.client.get(reverse('research_project', args=[self.project.pk]))
        self.assertContains(response, 'Visible experiment')
        # the details live on the edit page, the card only shows the title
        response = self.client.get(
            reverse('research_experiment_edit', args=[self.project.pk, experiment.pk])
        )
        self.assertContains(response, 'The hypothesis text')
        self.assertContains(response, 'The conclusion text')

    def test_project_page_has_the_details_in_the_hero(self):
        response = self.client.get(reverse('research_project', args=[self.project.pk]))
        self.assertContains(response, 'hero-stats')
        for label in ('Created', 'Status', 'Experiments', 'Attachments'):
            self.assertContains(response, label)
        # the old side bar is gone
        self.assertNotContains(response, 'project-side')

    def test_experiments_are_rendered_as_cards_without_a_panel(self):
        Experiment.objects.create(project=self.project, title='Card experiment')
        response = self.client.get(reverse('research_project', args=[self.project.pk]))
        self.assertContains(response, 'experiment-grid')
        self.assertContains(response, 'experiment-card')
        self.assertContains(response, 'Card experiment')
        # the "Experiments" panel header is gone, the cards float on their own
        self.assertNotContains(response, '>Experiments <span class="panel-count">')

    def test_experiment_cards_only_show_the_title_and_the_timestamp(self):
        Experiment.objects.create(
            project=self.project,
            title='Slim card',
            description='The description should not be on the card.',
            hypothesis='The hypothesis should not be on the card.',
            conclusion='The conclusion should not be on the card.',
        )
        response = self.client.get(reverse('research_project', args=[self.project.pk]))
        self.assertContains(response, 'Slim card')
        self.assertContains(response, 'experiment-date')
        self.assertContains(response, 'experiment-time')
        self.assertNotContains(response, 'The description should not be on the card.')
        self.assertNotContains(response, 'The hypothesis should not be on the card.')
        self.assertNotContains(response, 'The conclusion should not be on the card.')

    def test_experiment_delete_uses_the_site_modal(self):
        experiment = Experiment.objects.create(project=self.project, title='Doomed')
        response = self.client.get(reverse('research_project', args=[self.project.pk]))
        # the confirmation is handled by the shared modal, not by the browser
        self.assertContains(response, 'data-confirm=')
        self.assertContains(response, 'Doomed')
        self.assertNotContains(response, "onsubmit=\"return confirm(")

    def test_the_create_form_has_no_conclusion_field(self):
        response = self.client.get(reverse('research_experiment_create', args=[self.project.pk]))
        self.assertNotContains(response, 'id_conclusion')
        self.assertContains(response, 'id_hypothesis')

    def test_the_edit_form_has_the_conclusion_field(self):
        experiment = Experiment.objects.create(project=self.project, title='Edit me')
        response = self.client.get(
            reverse('research_experiment_edit', args=[self.project.pk, experiment.pk])
        )
        self.assertContains(response, 'id_conclusion')

    def test_cards_show_whether_a_conclusion_was_added(self):
        done = Experiment.objects.create(project=self.project, title='Finished one', conclusion='It worked.')
        pending = Experiment.objects.create(project=self.project, title='Still running')
        response = self.client.get(reverse('research_project', args=[self.project.pk]))
        self.assertContains(response, 'Conclusion added')
        self.assertContains(response, 'No conclusion yet')
        self.assertContains(response, 'experiment-status done')
        self.assertContains(response, 'experiment-status pending')

    def test_edit_experiment(self):
        experiment = Experiment.objects.create(project=self.project, title='Before')
        response = self.client.post(
            reverse('research_experiment_edit', args=[self.project.pk, experiment.pk]),
            {'title': 'After', 'hypothesis': 'New hypothesis'},
        )
        self.assertEqual(response.status_code, 302)
        experiment.refresh_from_db()
        self.assertEqual(experiment.title, 'After')
        self.assertEqual(experiment.hypothesis, 'New hypothesis')

    def test_edit_experiment_keeps_the_existing_files(self):
        experiment = Experiment.objects.create(project=self.project, title='With file')
        ExperimentFile.objects.create(
            experiment=experiment,
            file=SimpleUploadedFile('keep.txt', b'data', content_type='text/plain'),
        )
        self.client.post(
            reverse('research_experiment_edit', args=[self.project.pk, experiment.pk]),
            {'title': 'Renamed'},
        )
        self.assertEqual(experiment.files.count(), 1)

    def test_delete_experiment(self):
        experiment = Experiment.objects.create(project=self.project, title='Bye')
        response = self.client.post(
            reverse('research_experiment_delete', args=[self.project.pk, experiment.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Experiment.objects.filter(pk=experiment.pk).exists())

    def test_delete_experiment_requires_post(self):
        experiment = Experiment.objects.create(project=self.project, title='Bye')
        response = self.client.get(
            reverse('research_experiment_delete', args=[self.project.pk, experiment.pk])
        )
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Experiment.objects.filter(pk=experiment.pk).exists())

    def test_cannot_edit_an_experiment_of_another_project(self):
        other = ResearchProject.objects.create(acronym='BETA', full_form='Beta Project')
        experiment = Experiment.objects.create(project=other, title='Not yours')
        response = self.client.get(
            reverse('research_experiment_edit', args=[self.project.pk, experiment.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_deleting_a_project_removes_its_experiments(self):
        experiment = Experiment.objects.create(project=self.project, title='Doomed')
        self.project.delete()
        self.assertFalse(Experiment.objects.filter(pk=experiment.pk).exists())

import os
import shutil
import subprocess
import tempfile
import unittest.mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Experiment, ExperimentFile, ResearchPaper, ResearchProject, ResearchTag
from settings.models import EditorSetting


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

    def test_paper_page_renders_the_editor(self):
        response = self.client.get(reverse('research_paper', args=[self.project.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'paper-studio')
        self.assertContains(response, 'studio-editor')
        self.assertContains(response, 'studio-preview')

    def test_paper_page_404s_for_a_missing_project(self):
        response = self.client.get(reverse('research_paper', args=[999999]))
        self.assertEqual(response.status_code, 404)

    def test_the_hero_carries_the_primary_actions(self):
        response = self.client.get(reverse('research_project', args=[self.project.pk]))
        self.assertContains(response, 'hero-actions')
        self.assertContains(response, 'tool-btn-primary')
        self.assertContains(response, 'Research Paper')
        self.assertContains(response, 'New Experiment')

    def test_the_empty_state_sits_inside_the_experiments_panel(self):
        response = self.client.get(reverse('research_project', args=[self.project.pk]))
        self.assertContains(response, 'empty-note')
        self.assertContains(response, 'Add the first experiment')

    def test_the_paper_page_no_longer_lists_the_experiments(self):
        Experiment.objects.create(project=self.project, title='Finished one', conclusion='It worked.')
        Experiment.objects.create(project=self.project, title='Still running')
        response = self.client.get(reverse('research_paper', args=[self.project.pk]))
        self.assertNotContains(response, 'Finished one')
        self.assertNotContains(response, 'Still running')
        self.assertNotContains(response, 'paper-exp-list')

    def test_the_toolbar_carries_the_compile_button(self):
        response = self.client.get(reverse('research_paper', args=[self.project.pk]))
        self.assertContains(response, 'Compile</button>')
        self.assertContains(response, 'role="toolbar"')

    def test_the_paper_page_carries_the_vim_flags(self):
        response = self.client.get(reverse('research_paper', args=[self.project.pk]))
        payload = response.context['vim_flags']
        self.assertEqual(payload, {'enabled': True, 'keep_hjkl': True})
        self.assertContains(response, 'id="vim-flags-data"')

    def test_the_paper_page_only_loads_the_vim_addon_when_enabled(self):
        page = self.client.get(reverse('research_paper', args=[self.project.pk]))
        self.assertContains(page, 'vendor/codemirror/vim.js')
        setting = EditorSetting.load()
        setting.vim_mode = False
        setting.save()
        page = self.client.get(reverse('research_paper', args=[self.project.pk]))
        self.assertNotContains(page, 'vendor/codemirror/vim.js')


class PaperTests(TempMediaRootMixin, TestCase):
    """The paper editor: skeleton, autosave compile endpoint, error return."""

    def setUp(self):
        self.project = ResearchProject.objects.create(
            acronym='ALPHA',
            full_form='Alpha Project',
        )

    def test_the_first_visit_creates_the_skeleton(self):
        response = self.client.get(reverse('research_paper', args=[self.project.pk]))
        self.assertEqual(response.status_code, 200)
        paper = ResearchPaper.objects.get(project=self.project)
        self.assertTrue(paper.source.startswith(r'\documentclass[11pt]{article}'))
        self.assertIn(r'\title{ALPHA --- Alpha Project}', paper.source)
        self.assertIn(r'\end{document}', paper.source)

    def test_the_editor_mounts_the_saved_source(self):
        ResearchPaper.objects.create(
            project=self.project,
            source=r'\section{Kept part}' + '\n',
        )
        response = self.client.get(reverse('research_paper', args=[self.project.pk]))
        self.assertContains(response, 'Kept part')
        self.assertContains(response, 'paper-source-data')

    def test_the_compile_endpoint_saves_and_compiles(self):
        source = r'\documentclass{article}' + '\n' + r'\begin{document}' + '\n' + 'Alpha paper on the board.' + '\n' + r'\end{document}' + '\n'
        response = self.client.post(
            reverse('research_paper_compile', args=[self.project.pk]),
            {'source': source},
        )
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))
        paper = ResearchPaper.objects.get(project=self.project)
        self.assertEqual(paper.source, source)

    def test_the_compile_endpoint_saves_an_empty_document(self):
        source = r'\documentclass{article}' + '\n' + r'\begin{document}' + '\n' + r'\end{document}' + '\n'
        response = self.client.post(
            reverse('research_paper_compile', args=[self.project.pk]),
            {'source': source},
        )
        self.assertEqual(response.status_code, 400)
        # even when nothing typesets, the source is kept
        paper = ResearchPaper.objects.get(project=self.project)
        self.assertEqual(paper.source, source)
        self.assertIn('nothing to typeset', response.json()['errors'][0]['message'])

    def test_the_compile_endpoint_creates_the_paper_when_missing(self):
        self.client.post(
            reverse('research_paper_compile', args=[self.project.pk]),
            {
                'source': (
                    r'\documentclass{article}' + '\n'
                    + r'\begin{document}' + '\n'
                    + 'Alpha paper on the board.' + '\n'
                    + r'\end{document}' + '\n'
                ),
            },
        )
        ResearchPaper.objects.get(project=self.project)

    def test_the_compile_endpoint_reports_the_errors(self):
        response = self.client.post(
            reverse('research_paper_compile', args=[self.project.pk]),
            {'source': r'\begin{document}'},
        )
        self.assertEqual(response.status_code, 400)
        errors = response.json()['errors']
        self.assertTrue(errors)
        self.assertIn('line', errors[0])
        self.assertIn('message', errors[0])
        self.assertTrue(errors[0]['message'])

    def test_the_compile_endpoint_never_accepts_a_get(self):
        response = self.client.get(reverse('research_paper_compile', args=[self.project.pk]))
        self.assertEqual(response.status_code, 405)

    def test_the_skeleton_compiles_right_away(self):
        """A newborn paper must not open the editor on a broken preview."""
        from .views import _compile_latex, paper_skeleton
        pdf, errors = _compile_latex(paper_skeleton(self.project))
        self.assertTrue(pdf, str(errors))
        self.assertFalse(errors)


class ExperimentTests(TempMediaRootMixin, TestCase):
    def setUp(self):
        self.project = ResearchProject.objects.create(
            acronym='ALPHA',
            full_form='Alpha Project',
        )

    def test_experiment_form_renders(self):
        response = self.client.get(reverse('research_experiment_create', args=[self.project.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'What I expected')
        self.assertContains(response, 'What I did')

    def test_the_form_submits_from_the_top_bar(self):
        response = self.client.get(reverse('research_experiment_create', args=[self.project.pk]))
        self.assertContains(response, 'form="experiment-form"')
        # exactly one submit button: the one in the top bar
        self.assertEqual(response.content.count(b'type="submit"'), 1)
        self.assertContains(response, 'form-layout')
        self.assertContains(response, 'col-rail')

    def test_the_form_submits_once(self):
        response = self.client.post(
            reverse('research_experiment_create', args=[self.project.pk]),
            {'title': 'Single submit', 'description': 'x'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Experiment.objects.count(), 1)

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

    def test_project_page_has_the_details_in_the_sidebar(self):
        response = self.client.get(reverse('research_project', args=[self.project.pk]))
        # the hero only carries the identity and the actions now
        self.assertNotContains(response, 'hero-stats')
        self.assertContains(response, 'detail-layout')
        self.assertContains(response, 'col-side')
        for label in ('Created', 'Experiments', 'Attachments'):
            self.assertContains(response, label)
        # status lives in the hero badge, it is not repeated in the sidebar
        self.assertNotContains(response, '<span class="detail-label">Status</span>')
        # the old side bar is gone
        self.assertNotContains(response, 'project-side')

    def test_experiments_are_rendered_as_cards_inside_the_panel(self):
        Experiment.objects.create(project=self.project, title='Card experiment')
        response = self.client.get(reverse('research_project', args=[self.project.pk]))
        self.assertContains(response, 'experiment-grid')
        self.assertContains(response, 'experiment-card')
        self.assertContains(response, 'Card experiment')
        # the cards sit in their own panel, with a count in the header
        self.assertContains(response, '>Experiments <span class="panel-count">')

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


class ExperimentConclusionPageTests(TempMediaRootMixin, TestCase):
    def setUp(self):
        self.project = ResearchProject.objects.create(acronym='ALPHA', full_form='Alpha Project')
        self.experiment = Experiment.objects.create(
            project=self.project,
            title='Budget sweep',
            description='Swept the slot budget.',
            hypothesis='Loss should stay flat.',
        )

    def test_conclusion_page_shows_the_context_and_the_field(self):
        response = self.client.get(
            reverse('research_experiment', args=[self.project.pk, self.experiment.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Budget sweep')
        self.assertContains(response, 'Swept the slot budget.')
        self.assertContains(response, 'Loss should stay flat.')
        self.assertContains(response, 'id_conclusion')

    def test_the_conclusion_page_is_a_two_column_layout(self):
        response = self.client.get(
            reverse('research_experiment', args=[self.project.pk, self.experiment.pk])
        )
        self.assertContains(response, 'write-layout')
        self.assertContains(response, 'col-recall')
        self.assertContains(response, 'col-write')
        # the context sits in the left column, the field in the right one
        recall_at = response.content.index(b'class="col-recall"')
        write_at = response.content.index(b'class="col-write"')
        field_at = response.content.index(b'id_conclusion')
        self.assertLess(recall_at, write_at)
        self.assertLess(write_at, field_at)

    def test_the_conclusion_page_collapses_without_any_context(self):
        experiment = Experiment.objects.create(project=self.project, title='Bare')
        response = self.client.get(
            reverse('research_experiment', args=[self.project.pk, experiment.pk])
        )
        self.assertContains(response, 'write-layout no-recall')

    def test_conclusion_page_saves_the_conclusion(self):
        response = self.client.post(
            reverse('research_experiment', args=[self.project.pk, self.experiment.pk]),
            {'conclusion': 'It fell off a cliff at 512 slots.'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('research_project', args=[self.project.pk]))
        self.experiment.refresh_from_db()
        self.assertEqual(self.experiment.conclusion, 'It fell off a cliff at 512 slots.')

    def test_conclusion_page_can_clear_the_conclusion(self):
        self.experiment.conclusion = 'Something'
        self.experiment.save()
        self.client.post(
            reverse('research_experiment', args=[self.project.pk, self.experiment.pk]),
            {'conclusion': ''},
        )
        self.experiment.refresh_from_db()
        self.assertEqual(self.experiment.conclusion, '')

    def test_conclusion_page_404s_for_an_experiment_of_another_project(self):
        other = ResearchProject.objects.create(acronym='BETA', full_form='Beta Project')
        response = self.client.get(
            reverse('research_experiment', args=[other.pk, self.experiment.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_the_card_links_to_the_view_page(self):
        """The card opens the read-only page, the edit button the form."""
        response = self.client.get(reverse('research_project', args=[self.project.pk]))
        self.assertContains(
            response, reverse('research_experiment_view', args=[self.project.pk, self.experiment.pk])
        )
        # and the edit button still goes to the full edit page
        self.assertContains(
            response, reverse('research_experiment_edit', args=[self.project.pk, self.experiment.pk])
        )

    def test_the_create_page_has_no_conclusion_field(self):
        response = self.client.get(
            reverse('research_experiment_create', args=[self.project.pk])
        )
        self.assertNotContains(response, 'id_conclusion')
        self.assertContains(response, 'id_hypothesis')
        self.assertContains(response, 'id_title')

    def test_the_edit_page_has_every_field(self):
        response = self.client.get(
            reverse('research_experiment_edit', args=[self.project.pk, self.experiment.pk])
        )
        for field in ('id_title', 'id_description', 'id_hypothesis', 'id_conclusion', 'id_attachments'):
            self.assertContains(response, field)


class ResearchHardeningTests(TempMediaRootMixin, TestCase):
    """Regression tests from the 2026-10 audit.

    One batch covers the remove_files checkboxes that the edit form had
    always rendered but the view never processed; the other batch guards
    the update/delete endpoints against non-numeric ids (they used to
    raise ValueError -> HTTP 500).
    """

    def setUp(self):
        self.project = ResearchProject.objects.create(
            acronym='HARD',
            full_form='Hardening full form',
            description='desc',
            status=ResearchProject.STATUS_ACTIVE,
        )

    def make_experiment(self, title='Exp', **kwargs):
        return Experiment.objects.create(project=self.project, title=title, **kwargs)

    def upload_experiment(self, experiment, names):
        uploads = [
            SimpleUploadedFile(name, b'content ' + name.encode(), content_type='text/plain')
            for name in names
        ]
        response = self.client.post(
            reverse('research_experiment_edit', args=[self.project.pk, experiment.pk]),
            {'title': experiment.title, 'attachments': uploads},
        )
        self.assertEqual(response.status_code, 302)
        experiment.refresh_from_db()
        return experiment

    # -------------------------------------------------- remove_files
    def test_edit_can_remove_an_attachment_via_checkbox(self):
        experiment = self.make_experiment()
        self.upload_experiment(experiment, ['keep.txt', 'remove.txt'])
        kept, removed = experiment.files.all()
        response = self.client.post(
            reverse('research_experiment_edit', args=[self.project.pk, experiment.pk]),
            {'title': 'Exp', 'remove_files': [removed.pk]},
        )
        self.assertEqual(response.status_code, 302)
        pks = [row.pk for row in experiment.files.all()]
        self.assertIn(kept.pk, pks)
        self.assertNotIn(removed.pk, pks)

    def test_removed_attachment_blob_is_cleaned_up(self):
        experiment = self.make_experiment()
        self.upload_experiment(experiment, ['gone.txt'])
        removed = experiment.files.first()
        path = removed.file.path
        import os
        self.assertTrue(os.path.exists(path))
        self.client.post(
            reverse('research_experiment_edit', args=[self.project.pk, experiment.pk]),
            {'title': 'Exp', 'remove_files': [removed.pk]},
        )
        self.assertFalse(os.path.exists(path))

    def test_remove_files_ignores_ids_of_other_experiments(self):
        other = self.make_experiment(title='Other')
        self.upload_experiment(other, ['other.txt'])
        victim = other.files.first()
        experiment = self.make_experiment(title='Main')
        self.upload_experiment(experiment, ['main.txt'])
        response = self.client.post(
            reverse('research_experiment_edit', args=[self.project.pk, experiment.pk]),
            {'title': 'Main', 'remove_files': [victim.pk]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(other.files.filter(pk=victim.pk).exists())

    # --------------------------------------------------- garbage ids
    def test_update_project_rejects_garbage_id(self):
        response = self.client.post(reverse('research_update'), {'id': 'zzz', 'status': 'paused'})
        self.assertEqual(response.status_code, 404)

    def test_delete_project_rejects_garbage_id(self):
        response = self.client.post(reverse('research_delete'), {'id': 'zzz'})
        self.assertEqual(response.status_code, 404)

    # -------------------------------------------------- blob cleanup
    def test_deleting_an_experiment_removes_its_files_from_media(self):
        import os
        experiment = self.make_experiment()
        self.upload_experiment(experiment, ['doomed.txt'])
        path = experiment.files.first().file.path
        self.assertTrue(os.path.exists(path))
        self.client.post(
            reverse('research_experiment_delete', args=[self.project.pk, experiment.pk]),
        )
        self.assertFalse(experiment.files.exists())
        self.assertFalse(os.path.exists(path))

    def test_delete_project_garbage_id_keeps_files(self):
        experiment = self.make_experiment()
        self.upload_experiment(experiment, ['safe.txt'])
        response = self.client.post(reverse('research_delete'), {'id': 'zzz'})
        self.assertEqual(response.status_code, 404)
        self.assertTrue(experiment.files.exists())


class PaperHardeningTests(TempMediaRootMixin, TestCase):
    """Second-round audit tests for the paper compile stack.

    They pin the behaviour the editor relies on when the server is
    unfriendly: a missing pdflatex, a compile that outlives its deadline
    mid-second-pass, posts that carry no source key, oversized sources
    and project names full of TeX specials.
    """

    def setUp(self):
        self.project = ResearchProject.objects.create(
            acronym='GUARD',
            full_form='Guarding full form',
        )
        self.compile_url = reverse('research_paper_compile', args=[self.project.pk])
        self.paper_url = reverse('research_paper', args=[self.project.pk])

    def make_paper(self, source=''):
        return ResearchPaper.objects.create(project=self.project, source=source)

    # ------------------------------------------------- missing source key
    def test_a_post_without_a_source_key_is_rejected(self):
        self.make_paper(r'\section{Kept}')
        response = self.client.post(self.compile_url)
        self.assertEqual(response.status_code, 400)
        self.assertIn('errors', response.json())
        paper = ResearchPaper.objects.get(project=self.project)
        self.assertEqual(paper.source, r'\section{Kept}')

    def test_an_explicit_empty_source_is_still_stored(self):
        self.make_paper('something')
        response = self.client.post(self.compile_url, {'source': ''})
        self.assertEqual(response.status_code, 400)
        paper = ResearchPaper.objects.get(project=self.project)
        # an autosave of an emptied editor wins over the old draft
        self.assertEqual(paper.source, '')
        self.assertTrue(response.json()['errors'][0]['message'])

    # ------------------------------------------------------ length cap
    def test_an_oversized_source_is_rejected_and_not_stored(self):
        self.make_paper('previous')
        source = 'x' * 1_000_001
        response = self.client.post(self.compile_url, {'source': source})
        self.assertEqual(response.status_code, 400)
        message = response.json()['errors'][0]['message']
        self.assertIn('1 MB', message)
        paper = ResearchPaper.objects.get(project=self.project)
        self.assertNotEqual(paper.source, source)
        self.assertEqual(paper.source, 'previous')

    # --------------------------------------------------- pdflatex not there
    def test_a_missing_pdflatex_reports_a_json_error(self):
        with unittest.mock.patch(
            'research.views.subprocess.run',
            side_effect=FileNotFoundError('pdflatex'),
        ):
            response = self.client.post(
                self.compile_url, {'source': r'\begin{document}x\end{document}'},
            )
        self.assertEqual(response.status_code, 400)
        errors = response.json()['errors']
        self.assertIn('is not available on the server', errors[0]['message'])
        self.assertIsNone(errors[0]['line'])

    def test_the_compile_view_survives_an_os_error_from_the_runner(self):
        with unittest.mock.patch(
            'research.views.subprocess.run',
            side_effect=OSError('no exec'),
        ):
            response = self.client.post(
                self.compile_url, {'source': r'\begin{document}x\end{document}'},
            )
        self.assertEqual(response.status_code, 400)

    # ------------------------------------------ second pass over deadline
    def test_a_second_pass_timeout_keeps_the_first_pdf(self):
        from research.views import PAPER_COMPILE_TIMEOUT, _compile_latex

        calls = []

        def fake_run(command, **kwargs):
            calls.append(command)
            if len(calls) == 2:
                raise subprocess.TimeoutExpired(cmd=command, timeout=1)
            # emulate pass one: it produced a pdf and requested a rerun
            workdir = kwargs['cwd']
            with open(os.path.join(workdir, 'main.pdf'), 'wb') as handle:
                handle.write(b'%PDF-1.4 fake pass one')
            with open(os.path.join(workdir, 'main.aux'), 'w') as handle:
                handle.write(r'\newlabel{sec:one}{{1}{1}}')
            from subprocess import CompletedProcess
            return CompletedProcess(command, 0)

        with unittest.mock.patch('research.views.subprocess.run', side_effect=fake_run):
            pdf, errors = _compile_latex(r'\begin{document}x\end{document}\n')
        self.assertTrue(pdf.startswith(b'%PDF'), errors)
        self.assertEqual(errors, [])
        self.assertEqual(len(calls), 2, 'the rerun must still be attempted')

        # and a first pass that never finishes stays a timeout
        def late_run(command, **kwargs):
            raise subprocess.TimeoutExpired(cmd=command, timeout=PAPER_COMPILE_TIMEOUT)

        with unittest.mock.patch('research.views.subprocess.run', side_effect=late_run):
            pdf, errors = _compile_latex(r'\begin{document}x\end{document}\n')
        self.assertIsNone(pdf)
        self.assertIn('timed out', errors[0]['message'])

    # ---------------------------------------------------- skeleton safety
    def test_the_skeleton_escapes_the_project_name(self):
        self.project.acronym = 'C# 100%'
        self.project.full_form = r'Stress_{test} & \Trickery~ v^2'
        self.project.save()
        self.client.get(self.paper_url)  # creates the paper
        paper = ResearchPaper.objects.get(project=self.project)
        self.assertIn(r'C\# 100\% --- Stress\_\{test\} \& \textbackslash{}', paper.source)
        self.assertIn(r'textasciitilde', paper.source)
        self.assertIn(r'textasciicircum', paper.source)

    def test_an_escaped_skeleton_still_compiles(self):
        from .views import _compile_latex, paper_skeleton

        self.project.acronym = 'C# (%)_{weird}'
        self.project.full_form = 'And ~one ^and two & \\downhill'
        self.project.save()
        pdf, errors = _compile_latex(paper_skeleton(self.project))
        self.assertTrue(pdf, str(errors))
        self.assertFalse(errors)

    # --------------------------------------------- vendor scripts render
    def test_a_paper_with_non_ascii_characters_compiles(self):
        """Greek letters, dashes and cjk must not break the preview.

        pdflatex refused every character outside ascii with a cryptic
        "Unicode character not set up for use with LaTeX" error.
        """
        from .views import _compile_latex

        source = (
            '\\documentclass{article}\n'
            '\\begin{document}\n'
            'Café — α β γ 日本語\n'
            '\\end{document}\n'
        )
        pdf, errors = _compile_latex(source)
        self.assertTrue(pdf, str(errors))
        self.assertFalse(errors)

    @override_settings(STATIC_URL='/assets/')
    def test_the_editor_builds_the_vendor_urls_from_static(self):
        """With a custom STATIC_URL the hard-coded /static/ paths would 404."""
        response = self.client.get(self.paper_url)
        html = response.content.decode()
        self.assertContains(response, '/assets/js/vendor/codemirror/codemirror.js')
        self.assertContains(response, '/assets/js/vendor/codemirror/codemirror.css')
        self.assertNotIn('/static/js/', html)

    @override_settings(STATIC_URL='/assets/')
    def test_vim_mode_loads_the_bracket_matcher_too(self):
        setting = EditorSetting.load()
        setting.vim_mode = True
        setting.save()
        response = self.client.get(self.paper_url)
        self.assertContains(response, '/assets/js/vendor/codemirror/matchbrackets.js')

    def test_the_vendored_matchbrackets_file_exists(self):
        from django.conf import settings as django_settings
        path = os.path.join(
            django_settings.BASE_DIR, 'static', 'js', 'vendor', 'codemirror',
            'matchbrackets.js',
        )
        self.assertTrue(os.path.exists(path))
        with open(path, encoding='utf-8') as handle:
            body = handle.read()
        self.assertIn('findMatchingBracket', body)


class ResearchPageGuardTests(TempMediaRootMixin, TestCase):
    """Round two: the research pages lost data and lied about saves."""

    def setUp(self):
        self.project = ResearchProject.objects.create(
            acronym='ROUND',
            full_form='Second round full form',
        )

    def test_the_status_badge_follows_the_status_attribute(self):
        """The badge colour comes from the [data-status] css rule."""
        response = self.client.get(reverse('research'))
        self.assertContains(response, 'data-status="active"')
        with open(
            os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'static', 'js', 'research-common.js',
            ),
            encoding='utf-8',
        ) as handle:
            script = handle.read()
        self.assertIn("badge.dataset.status = value", script)

    def test_the_project_description_is_capped(self):
        response = self.client.post(reverse('research_create'), {
            'acronym': 'CAP',
            'full_form': 'Capped form',
            'description': 'd' * 30000,
        })
        self.assertEqual(response.status_code, 200)
        project = ResearchProject.objects.get(acronym='CAP')
        self.assertLessEqual(len(project.description), 20000)

    def test_a_huge_experiment_description_is_refused_by_the_form(self):
        experiment = Experiment.objects.create(project=self.project, title='Big')
        response = self.client.post(
            reverse('research_experiment_edit', args=[self.project.pk, experiment.pk]),
            {'title': 'Big', 'description': 'x' * 30000},
        )
        self.assertEqual(response.status_code, 200)
        experiment.refresh_from_db()
        self.assertEqual(experiment.description, '')

    def test_a_huge_conclusion_keeps_the_old_value(self):
        experiment = Experiment.objects.create(
            project=self.project, title='Conclusion', conclusion='old',
        )
        response = self.client.post(
            reverse('research_experiment', args=[self.project.pk, experiment.pk]),
            {'conclusion': 'y' * 30000},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'longer than')
        experiment.refresh_from_db()
        self.assertEqual(experiment.conclusion, 'old')

    def test_the_experiment_form_tells_the_truth_about_file_types(self):
        response = self.client.get(
            reverse('research_experiment_create', args=[self.project.pk]),
        )
        self.assertContains(response, 'pdf')
        self.assertNotContains(response, 'Any file type')


class ResearchClientGuardTests(TempMediaRootMixin, TestCase):
    """Round two: the research pages keep their promises."""

    def setUp(self):
        self.project = ResearchProject.objects.create(
            acronym='CLIENT', full_form='Client full form',
        )

    def test_the_paper_editor_keeps_the_failed_source_and_retries_on_demand(self):
        response = self.client.get(reverse('research_paper', args=[self.project.pk]))
        html = response.content.decode()
        self.assertIn('lastAttemptedSource', html)
        self.assertIn('compileNow(true)', html)
        self.assertIn('compileNow(false)', html)

    def test_the_tag_picker_is_reachable_with_the_keyboard(self):
        response = self.client.get(reverse('research'))
        html = response.content.decode()
        self.assertNotIn('.tag-option input {\n        display: none;', html)
        self.assertIn('.tag-option:focus-within', html)

    def test_the_description_field_is_limited_to_what_the_server_stores(self):
        response = self.client.get(reverse('research'))
        self.assertContains(response, 'maxlength="20000"')


class PaperClipboardRegisterTests(TempMediaRootMixin, TestCase):
    """Round two: vim's "+ register is the system clipboard.

    CodeMirror's vim emulation only knows its own registers, so
    "+y ended up in the unnamed register and the system clipboard
    stayed untouched. The paper editor defines the register itself.
    """

    def setUp(self):
        self.project = ResearchProject.objects.create(
            acronym='CLIP', full_form='Clipboard full form',
        )
        EditorSetting.load().vim_mode = True
        EditorSetting.load().save()

    def editor_html(self):
        response = self.client.get(reverse('research_paper', args=[self.project.pk]))
        return response.content.decode()

    def test_the_editor_defines_the_clipboard_register(self):
        html = self.editor_html()
        self.assertIn("Vim.defineRegister('+'", html)
        self.assertIn('navigator.clipboard.writeText', html)
        self.assertIn('navigator.clipboard.readText', html)

    def test_the_paste_is_handled_before_the_vim_key_map(self):
        html = self.editor_html()
        # the capture phase listener keeps the key away from the vim key map
        self.assertIn("editor.getWrapperElement().addEventListener('keydown'", html)
        self.assertIn('e.stopPropagation();', html)

    def test_the_settings_page_documents_the_register(self):
        response = self.client.get(reverse('settings'), {'tab': 'editor'})
        self.assertContains(response, '&quot;+y')
        self.assertContains(response, '&quot;+p')


class ExperimentViewPageTests(TempMediaRootMixin, TestCase):
    """The read-only page of an experiment: every detail in one place."""

    def setUp(self):
        self.project = ResearchProject.objects.create(
            acronym='VIEW', full_form='View page full form',
        )
        self.experiment = Experiment.objects.create(
            project=self.project,
            title='The interesting run',
            description='I trained a four layer model.',
            hypothesis='The loss should plateau around 0.2.',
            conclusion='It plateaued at 0.31 instead.',
        )

    def url(self, experiment=None):
        return reverse(
            'research_experiment_view',
            args=[self.project.pk, (experiment or self.experiment).pk],
        )

    def test_the_view_page_shows_every_detail(self):
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'The interesting run')
        self.assertContains(response, 'I trained a four layer model.')
        self.assertContains(response, 'The loss should plateau around 0.2.')
        self.assertContains(response, 'It plateaued at 0.31 instead.')

    def test_the_view_page_is_read_only(self):
        response = self.client.get(self.url())
        self.assertNotContains(response, '<form method="post"')
        self.assertNotContains(response, 'name="conclusion"')
        self.assertNotContains(response, 'name="title"')

    def test_the_view_page_lists_the_files(self):
        experiment = Experiment.objects.create(project=self.project, title='With files')
        upload = SimpleUploadedFile('notes.txt', b'hello world', content_type='text/plain')
        ExperimentFile.objects.create(experiment=experiment, file=upload, original_name='notes.txt')
        response = self.client.get(self.url(experiment))
        self.assertContains(response, 'notes.txt')

    def test_the_view_page_says_when_a_field_is_empty(self):
        empty = Experiment.objects.create(project=self.project, title='Empty one')
        response = self.client.get(self.url(empty))
        self.assertContains(response, 'Nothing written down yet.')
        self.assertContains(response, 'The experiment has no conclusion yet.')

    def test_the_view_page_links_to_the_edit_page(self):
        response = self.client.get(self.url())
        self.assertContains(
            response,
            reverse('research_experiment_edit', args=[self.project.pk, self.experiment.pk]),
        )

    def test_the_view_page_links_to_the_conclusion_page(self):
        response = self.client.get(self.url())
        self.assertContains(
            response,
            reverse('research_experiment', args=[self.project.pk, self.experiment.pk]),
        )

    def test_the_view_page_404s_for_an_experiment_of_another_project(self):
        other = ResearchProject.objects.create(acronym='OTHR', full_form='Other project')
        response = self.client.get(
            reverse('research_experiment_view', args=[other.pk, self.experiment.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_the_conclusion_page_links_back_to_the_view_page(self):
        response = self.client.get(
            reverse('research_experiment', args=[self.project.pk, self.experiment.pk])
        )
        self.assertContains(response, self.url())


class ExperimentFilePageTests(TempMediaRootMixin, TestCase):
    """A file opens in its own page: a code editor with the text in it."""

    def setUp(self):
        self.project = ResearchProject.objects.create(
            acronym='FILES', full_form='Files full form',
        )
        self.experiment = Experiment.objects.create(
            project=self.project, title='Experiment with files',
        )
        self.file = ExperimentFile.objects.create(
            experiment=self.experiment,
            file=SimpleUploadedFile('report.txt', b'plain text', content_type='text/plain'),
            original_name='report.txt',
        )

    def view_url(self):
        return reverse('research_experiment_view', args=[self.project.pk, self.experiment.pk])

    def file_url(self, experiment_file=None):
        return reverse(
            'research_experiment_file',
            args=[
                self.project.pk,
                self.experiment.pk,
                (experiment_file or self.file).pk,
            ],
        )

    # --------------------------------------------------------- the card
    def test_the_card_links_to_the_file_page(self):
        response = self.client.get(self.view_url())
        self.assertContains(response, self.file_url())

    def test_every_file_has_a_download_control(self):
        response = self.client.get(self.view_url())
        self.assertContains(response, 'class="file-download"')
        self.assertContains(response, 'data-download-url=')
        self.assertContains(response, self.file.file.url)

    def test_the_download_does_not_follow_the_card_link(self):
        response = self.client.get(self.view_url())
        self.assertContains(response, 'e.stopPropagation();')
        self.assertContains(response, "link.download = name || '';")

    # ----------------------------------------------------- the file page
    def test_the_file_page_shows_the_text(self):
        response = self.client.get(self.file_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'plain text')
        self.assertContains(response, 'report.txt')

    def test_the_file_page_opens_a_code_editor(self):
        response = self.client.get(self.file_url())
        self.assertContains(response, 'id="file-editor"')
        self.assertContains(response, 'CodeMirror(')
        self.assertContains(response, 'readOnly: true')

    def test_a_code_file_gets_its_syntax_highlighting(self):
        code = ExperimentFile.objects.create(
            experiment=self.experiment,
            file=SimpleUploadedFile('script.py', b'def hello():\n    return 1\n', content_type='text/plain'),
            original_name='script.py',
        )
        response = self.client.get(self.file_url(code))
        self.assertContains(response, 'mode/python/python.js')
        self.assertContains(response, '"python"')

    def test_a_plain_file_gets_no_mode(self):
        response = self.client.get(self.file_url())
        self.assertNotContains(response, 'mode/python/python.js')
        self.assertContains(response, '"null"')

    def test_a_binary_file_says_it_is_not_text(self):
        binary = ExperimentFile.objects.create(
            experiment=self.experiment,
            file=SimpleUploadedFile('plot.png', b'\x89PNG\r\n\x1a\n\x00\xff', content_type='image/png'),
            original_name='plot.png',
        )
        response = self.client.get(self.file_url(binary))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'is not a text file')
        self.assertNotContains(response, 'id="file-editor"')

    def test_a_huge_file_is_cut_and_says_so(self):
        big = ExperimentFile.objects.create(
            experiment=self.experiment,
            file=SimpleUploadedFile('big.log', b'x' * (600 * 1024), content_type='text/plain'),
            original_name='big.log',
        )
        response = self.client.get(self.file_url(big))
        self.assertContains(response, 'The file is larger than 512 KB')
        self.assertContains(response, 'id="file-editor"')

    def test_the_file_page_404s_for_a_file_of_another_experiment(self):
        other = Experiment.objects.create(project=self.project, title='Other')
        stranger = ExperimentFile.objects.create(
            experiment=other,
            file=SimpleUploadedFile('stranger.txt', b'x', content_type='text/plain'),
            original_name='stranger.txt',
        )
        response = self.client.get(
            reverse(
                'research_experiment_file',
                args=[self.project.pk, self.experiment.pk, stranger.pk],
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_the_file_page_404s_for_another_project(self):
        other = ResearchProject.objects.create(acronym='OTHR', full_form='Other project')
        response = self.client.get(
            reverse(
                'research_experiment_file',
                args=[other.pk, self.experiment.pk, self.file.pk],
            )
        )
        self.assertEqual(response.status_code, 404)


class ProjectOverviewTests(TempMediaRootMixin, TestCase):
    """The long description of a project: written at creation, edited later."""

    def setUp(self):
        self.project = ResearchProject.objects.create(
            acronym='OVER', full_form='Overview full form',
        )

    def test_a_project_can_be_created_with_a_long_description(self):
        response = self.client.post(reverse('research_create'), {
            'acronym': 'LONG',
            'full_form': 'Long description project',
            'description': 'the short one',
            'details': 'the long write-up of the project',
        })
        self.assertEqual(response.status_code, 200)
        project = ResearchProject.objects.get(acronym='LONG')
        self.assertEqual(project.details, 'the long write-up of the project')

    def test_the_long_description_can_be_written_afterwards(self):
        response = self.client.post(reverse('research_update'), {
            'id': self.project.pk,
            'details': 'written on the project page',
        })
        self.assertEqual(response.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.details, 'written on the project page')
        self.assertEqual(response.json()['details'], 'written on the project page')

    def test_an_empty_long_description_clears_it(self):
        self.project.details = 'something'
        self.project.save()
        response = self.client.post(reverse('research_update'), {
            'id': self.project.pk,
            'details': '',
        })
        self.assertEqual(response.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.details, '')

    def test_a_status_change_does_not_touch_the_long_description(self):
        self.project.details = 'keep me'
        self.project.save()
        response = self.client.post(reverse('research_update'), {
            'id': self.project.pk,
            'status': 'paused',
        })
        self.assertEqual(response.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.details, 'keep me')
        self.assertEqual(self.project.status, 'paused')

    def test_the_long_description_is_capped(self):
        response = self.client.post(reverse('research_update'), {
            'id': self.project.pk,
            'details': 'x' * 30000,
        })
        self.assertEqual(response.status_code, 200)
        self.project.refresh_from_db()
        self.assertLessEqual(len(self.project.details), 20000)

    def test_the_project_page_carries_the_editor(self):
        response = self.client.get(reverse('research_project', args=[self.project.pk]))
        self.assertContains(response, 'id="overview-edit"')
        self.assertContains(response, 'id="overview-input"')
        self.assertContains(response, 'id="overview-save"')
        self.assertContains(response, 'id="overview-cancel"')

    def test_the_overview_shows_the_text(self):
        self.project.details = 'the write-up'
        self.project.save()
        response = self.client.get(reverse('research_project', args=[self.project.pk]))
        self.assertContains(response, 'the write-up')

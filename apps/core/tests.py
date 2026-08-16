from django.test import TestCase
from django.urls import reverse

from apps.math_quiz.models import ConceptMastery, MasteryState, Section, Unit


class CoreRouteTests(TestCase):
    def test_home_lists_all_subjects(self):
        response = self.client.get(reverse('core:home'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<nav class="navbar"')
        for label in ('Mathematics', 'Coding', 'Languages', 'Other Subjects'):
            self.assertContains(response, label)

    def test_no_subject_card_is_stuck_on_a_hardcoded_label(self):
        """Every card reads its badge from progress_summary. Three of them used
        to print "Coming soon" no matter what the learner had done."""
        response = self.client.get(reverse('core:home'))

        self.assertNotContains(response, 'Coming soon')
        self.assertContains(response, 'Not started yet', count=4)

    def _master_one_maths_section(self):
        session = self.client.session
        session.save()
        unit = Unit.objects.create(name='Algebra')
        ConceptMastery.objects.create(
            section=Section.objects.create(unit=unit, title='Linear equations'),
            browser_session_key=session.session_key,
            mastery_state=MasteryState.MASTERED,
        )

    def test_maths_card_reflects_real_progress(self):
        self._master_one_maths_section()

        response = self.client.get(reverse('core:home'))

        self.assertContains(response, '1 mastered')

    def test_the_standalone_subject_page_shows_the_same_badges(self):
        """core/home.html includes this partial, but /subjects/ serves it on
        its own — a context missing there fails silently in the template."""
        self._master_one_maths_section()

        response = self.client.get(reverse('core:subject_selection'))

        self.assertContains(response, '1 mastered')

from django.test import SimpleTestCase

from .exceptions import UnsupportedLanguage
from .runner import ExecutionRequest, ExecutionStatus, UnavailableCodeExecutionGateway


class CodeRunnerBoundaryTests(SimpleTestCase):
    def test_local_placeholder_never_claims_code_was_run(self):
        result = UnavailableCodeExecutionGateway().run(
            ExecutionRequest(language='python', source_code='print(1)')
        )

        self.assertEqual(result.status, ExecutionStatus.NOT_EXECUTED)

    def test_only_python_is_accepted(self):
        with self.assertRaises(UnsupportedLanguage):
            UnavailableCodeExecutionGateway().run(
                ExecutionRequest(language='javascript', source_code='console.log(1)')
            )

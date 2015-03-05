"""Ralint tests."""


from unittest import TestCase
import ralint


class TestRalint(TestCase):

    """Ralint Tests."""

    def test_rally_query(self):
        """RallyQuery is initially None."""
        query = ralint.RallyQuery()
        self.assertTrue(query() is None)

# test rally query parenthesis are matched
# test rally query is formatted correctly
# test output functions?
# test checkers?
# can i mock the Rally class?? Or the Ralint class.
# separate out teammembers, test it

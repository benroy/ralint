"""Ralint tests."""


from unittest import TestCase
import ralint


class TestRalintQuery(TestCase):

    """Ralint Tests."""

    def test_terms_are_validated(self):
        """RallyQuery terms are validated."""
        query = ralint.RallyQuery('X > Y')
        self.assertRaises(ValueError, query.add_term, 'X>Y')
        self.assertRaises(ValueError, query.add_term, 'X> Y')
        self.assertRaises(ValueError, query.add_term, 'X >Y')
        self.assertRaises(ValueError, query.add_term, ' X > Y')
        self.assertRaises(ValueError, query.add_term, 'X > Y ')
        self.assertRaises(ValueError, query.add_term, '(X > Y)')

    def test_parens_are_balanced(self):
        """RallyQuery parens are balanced."""
        query = ralint.RallyQuery('blah blah blah')
        query.add_term('foo foo foo', bool_op='OR')
        query.add_term('bar bar bar')
        query.add_term(query)
        lparens = query().count('(')
        rparens = query().count(')')
        self.assertEqual(lparens, rparens)

    def test_rally_query_from_list(self):
        """RallyQuery can be created from list of terms."""
        query = ralint.RallyQuery(['X > Y', 'A = B'])
        self.assertRegexpMatches(query(), r'\) (AND|OR) \(')

    def test_rally_query_from_query(self):
        """RallyQuery can be created from another RallyQuery."""
        query1 = ralint.RallyQuery('X > Y')
        query2 = ralint.RallyQuery(query1)
        self.assertEqual(query1(), query2())

    def test_rally_query_current_iter(self):
        """RallyQuery can include current iteration."""
        query = ralint.RallyQuery('X > Y', current_iteration=True)
        self.assertRegexpMatches(
            query(),
            r'.*Iteration.*Date.*today.*\) AND \(.*Iteration.*Date.*today')


# test rally query is formatted correctly
# test output functions?
# test checkers?
# can i mock the Rally class?? Or the Ralint class.
# separate out teammembers, test it

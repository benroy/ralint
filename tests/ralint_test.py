"""Ralint tests."""


from unittest2 import TestCase
import ralint


class TestRalintQuery(TestCase):

    """RalintQuery Tests."""

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


class PyralRallyRespMock(object):

    """Mock for pyral RallyRESTResponse."""

    def __init__(self, errors=None):
        """Initialize PyralRallyMock."""
        self.errors = errors or []

    def __iter__(self):
        """Implement iterable protocol."""
        return self

    def next(self):
        """Implement iterable protocol."""
        raise StopIteration


class PyralRallyMock(object):

    """Mock for pyral Rally."""

    def __init__(self, resp=None, get_delegate=None):
        """Initialize PyralRallyMock."""
        self.__resp = resp or PyralRallyRespMock()
        self.__get_delegate = get_delegate

    def get(self, *args, **kwargs):
        """Get the mocked pyral RallyRESTResponse."""
        if self.__get_delegate is not None:
            self.__get_delegate(*args, **kwargs)
        return self.__resp


class TestRalint(TestCase):

    """Ralint Tests."""

    def test_get_handles_errors(self):
        """Rally.get checks for errors and handles them."""
        resp = PyralRallyRespMock(errors=['error1', 'error2'])
        ralint_obj = ralint.Ralint(PyralRallyMock(resp), {})
        self.assertRaises(RuntimeError, ralint_obj.get, 'DummyEntity')

    def test_get_passes_query(self):
        """Rally.get passes its query to pyral.Rally.get."""
        test_query = ralint.RallyQuery('X > Y')

        def get_delegate(_, query=None, **kwargs):
            """Check the query passed to PyralRallyMock.get."""
            self.assertEqual(query, test_query())

        ralint_obj = ralint.Ralint(
            PyralRallyMock(get_delegate=get_delegate), {})

        ralint_obj.get('some entity', test_query)

    def test_get_adds_user_to_stories(self):
        """Rally.get adds user filter to story queries."""
        users = ['Ike', 'Luke']

        def get_delegate(_, query=None, **kwargs):
            """Check the query passed to PyralRallyMock.get."""
            user_regexp = r'.*\) OR \(.*'.join(users)
            self.assertRegexpMatches(query, user_regexp)

        options = {}
        options['filter_owner'] = users
        ralint_obj = ralint.Ralint(
            PyralRallyMock(get_delegate=get_delegate),
            options)

        ralint_obj.get('HierarchicalRequirement')

    def test_get_wont_always_add_user(self):
        """Rally.get won't add user filter to entities without owner attr."""
        users = ['Ike', 'Luke']

        def get_delegate(_, query=None, **kwargs):
            """Check the query passed to PyralRallyMock.get."""
            user_regexp = r'.*\) OR \(.*'.join(users)
            self.assertNotRegexpMatches(query, user_regexp)

        options = {}
        options['filter_owner'] = users
        ralint_obj = ralint.Ralint(
            PyralRallyMock(get_delegate=get_delegate),
            options)

        ralint_obj.get('Iteration', ralint.RallyQuery('x < y'))

    def test_get_inserts_user(self):
        """Rally.get inserts user filter into initial query."""
        initial_query = ralint.RallyQuery('x < y')
        initial_query_str = initial_query()
        users = ['Ike', 'Luke']

        def get_delegate(_, query=None, **kwargs):
            """Check the query passed to PyralRallyMock.get."""
            user_regexp = r'.*\) OR \(.*'.join(users)
            self.assertRegexpMatches(query, user_regexp)
            self.assertRegexpMatches(query, initial_query_str)

        options = {}
        options['filter_owner'] = users
        ralint_obj = ralint.Ralint(
            PyralRallyMock(get_delegate=get_delegate),
            options)

        ralint_obj.get('Task', initial_query)
# test rally query is formatted correctly
# test output functions?
# test checkers?
# can i mock the Rally class?? Or the Ralint class.
# separate out teammembers, test it

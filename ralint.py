#!/usr/bin/env python
"""docstring for ralint module."""


import argparse
import inspect
import re
import types
from pyral import Rally, rallyWorkset

__version__ = '0.0.0'


def check_tasks_with_no_owner(rally):
    """Disowned tasks."""
    query = RallyQuery("Owner = null", current_iteration=True)

    return [format_artifact(t) for t in rally.get('Task', query)]


def check_tasks_with_no_estimate(rally):
    """Unestimated tasks."""
    query = RallyQuery(
        ['Estimate = null',
         'Estimate = 0'],
        bool_op='OR',
        current_iteration=True)

    return [format_artifact(t) for t in rally.get('Task', query=query)]


def check_users_with_no_stories(rally):
    """Available users."""
    query = RallyQueryCurrentIteration()
    stories = rally.get('HierarchicalRequirement', query)
    users = set(rally.get('User'))
    users_with_stories = set([s.Owner for s in stories])

    return [u.Name for u in users - users_with_stories]


def check_users_with_too_many_tasks(rally):
    """Overtasked users."""
    # get user's capacity
    # need a way to default to some value
    query = RallyQueryCurrentIteration()
    response = rally.get('UserIterationCapacity', query)

    uic_list = [uic for uic in response if uic.TaskEstimates > uic.Capacity]

    return ['{0} capacity: {1}, task estimate {2}'.format(uic.User.Name,
                                                          uic.Capacity,
                                                          uic.TaskEstimates)
            for uic in uic_list]


def check_stories_with_no_points(rally):
    """Unestimated stories."""
    query = RallyQuery(
        ['PlanEstimate = null',
         'PlanEstimate = 0'],
        bool_op="OR",
        current_iteration=True)

    return [format_artifact(s)
            for s in rally.get('HierarchicalRequirement', query=query)]


def check_stories_with_no_owner(rally):
    """Disowned stories."""
    query = RallyQuery("Owner = null", current_iteration=True)

    return [format_artifact(s)
            for s in rally.get('HierarchicalRequirement', query=query)]


def check_stories_with_no_desc(rally):
    """Undescribed stories."""
    query = RallyQuery("Description = null", current_iteration=True)

    return [format_artifact(s)
            for s in rally.get('HierarchicalRequirement', query=query)]


def check_stories_with_no_tasks(rally):
    """Untaksed stories."""
    query = RallyQuery("TaskStatus = NONE", current_iteration=True)

    return [format_artifact(s)
            for s in rally.get('HierarchicalRequirement', query=query)]


def check_stories_blocked(rally):
    """Blocked stories."""
    query = RallyQuery("Blocked = true", current_iteration=True)

    return [format_artifact(s)
            for s in rally.get('HierarchicalRequirement', query=query)]


class RallyQuery(object):

    """Rally Query."""

    def __init__(self, term, current_iteration=False, bool_op='AND'):
        """Rally Query constructor."""
        super(RallyQuery, self).__init__()

        self.__query_string = None

        self.add_term(term, bool_op)

        if current_iteration:
            self.and_current_iteration()

    @staticmethod
    def __validate_term(term):
        """Raise an exception if term is invalid."""
        if not (isinstance(term, RallyQuery) or
                re.compile(r'^[^\s\(\)]+ [^\s\(\)]+ [^\s\(\)]+$').match(term)):
            raise ValueError('Invalid format. Must be a RallyQuery or a '
                             'string like: X > Y')

    def add_term(self, term, bool_op='AND'):
        """Add a term to the query."""
        if type(term) in [types.ListType, types.TupleType]:
            for sub_term in term:
                self.add_term(sub_term, bool_op)
        else:
            self.__validate_term(term)
            term = term() if isinstance(term, RallyQuery) else term
            if self.__query_string is None:
                self.__query_string = term
            else:
                self.__query_string = "({0}) {1} ({2})".format(
                    self.__query_string,
                    bool_op,
                    term)

    def and_current_iteration(self):
        """Add current iteration to query."""
        self.add_term(RallyQueryCurrentIteration())

    def __call__(self):
        """Return the query string."""
        return self.__query_string


class RallyQueryCurrentIteration(RallyQuery):

    """Shortcut for creating a RallyQuery for the current iteration."""

    def __init__(self):
        """Construct a RallyQueryCurrentIteration instance."""
        terms = ['Iteration.StartDate < today',
                 'Iteration.EndDate > today']

        super(RallyQueryCurrentIteration, self).__init__(terms)


def build_user_name_reference(entity_name):
    """Get the path to the user associated with entity."""
    owner_ref = {
        'HierarchicalRequirement': ['Owner'],
        'UserIterationCapacity':   ['User'],
        'Task':                    ['Owner'],
        'User':                    []
    }.get(entity_name, None)

    if owner_ref is None:
        return

    return ".".join(owner_ref + ['UserName'])


class Ralint(object):

    """Ralint main object."""

    def __init__(self, pyral_rally_instance, include_users=None):
        """Ralint constructor."""
        super(Ralint, self).__init__()
        self.__rally = pyral_rally_instance
        self.__include_users = include_users

    def __apply_query_filters(self, entity_name, query):
        """Insert additional terms into query."""
        # if no team_members were specified, return unmodified query
        if self.__include_users is None:
            return query

        path = build_user_name_reference(entity_name)

        # if entity has no user attribute, return unmodified query
        if path is None:
            return query

        # create query that OR's all team_members together
        user_query = RallyQuery(
            ["{0} = {1}".format(path, m) for m in self.__include_users],
            bool_op='OR')

        # if initial query was empty, return user_query
        if query is None:
            return user_query

        # or add user_query to existing query
        query.add_term(user_query)
        return query

    def get(self, entity_name, query=None):
        """
        Wrap the pyral get method.

        Does several things (should only do one?)
        1) Inserts user terms into query if team_members are specified
        2) Inserts additional projectScopeDown arg into pyral.Rally.get
        3) Does some minimal, generic error "handling"
        4) Coverts pyral's response object to a list of entities
        """
        query = self.__apply_query_filters(entity_name, query)

        if query is None:
            pyral_resp = self.__rally.get(entity_name,
                                          projectScopeDown=True)
        else:
            pyral_resp = self.__rally.get(entity_name,
                                          query=query(),
                                          projectScopeDown=True)

        if len(pyral_resp.errors) > 0:
            print("Could not get '{0}', query='{1}'".format(
                entity_name,
                query() if query else ''))

            print(pyral_resp.errors)
            raise RuntimeError

        return list(pyral_resp)


def output(title, details):
    """Format the output of a check function."""
    if len(details) == 0:
        return

    print('==={0} ({1})'.format(title, len(details)))
    print('\n'.join(details))
    print('\n')


def format_artifact(story):
    """Format artifact like US12345: This is a story about Jack and Diane."""
    return '{0}: {1}'.format(story.FormattedID, story.Name)


def _ralint_init():
    """Return an instance of pyral.Rally."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--teamMembers', nargs='+')
    ralint_args, pyral_args = parser.parse_known_args()
    team_members = ralint_args.teamMembers
    server, user, password, _, _, project = rallyWorkset(pyral_args)
    rally = Rally(server, user, password, project=project)

    return Ralint(rally, include_users=team_members)


def get_check_functions():
    """Return all globally visible czech functions."""
    checks = []
    mod = inspect.getmodule(_ralint_init)
    for (name, function) in inspect.getmembers(mod, inspect.isfunction):
        if name.find('check_') == 0:
            checks.append(function)
    return checks


def _run_checkers(rally):
    """Run rally lint checks."""
    for check_func in get_check_functions():
        output(check_func.__doc__, check_func(rally))


def ralint():
    """Lint your rally."""
    _run_checkers(_ralint_init())

if __name__ == '__main__':
    ralint()

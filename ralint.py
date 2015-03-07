#!/usr/bin/env python
"""docstring for ralint module."""


import argparse
import re
import types
from pyral import Rally, rallyWorkset

__version__ = '0.0.0'


def users_with_no_current_stories(rally):
    """Return list of users with no current stories."""
    query = RallyQueryCurrentIteration()
    stories = rally.get('HierarchicalRequirement', query)
    users = set(rally.get('User'))
    users_with_stories = set([s.Owner for s in stories])
    return users - users_with_stories


def users_with_too_many_tasks(rally):
    """Check if a user has too many tasks."""
    # get user's capacity
    # need a way to default to some value
    query = RallyQueryCurrentIteration()
    response = rally.get('UserIterationCapacity', query)

    return [uic for uic in response if uic.TaskEstimates > uic.Capacity]


def current_stories_with_no_points(rally):
    """Return the list of stories in the current iteration with no points."""
    query = RallyQuery("PlanEstimate = null", current_iteration=True)

    return rally.get('HierarchicalRequirement', query=query)


def current_stories_with_no_owner(rally):
    """Return the list of stories in the current iteration with no owner."""
    query = RallyQuery("Owner = null", current_iteration=True)

    return rally.get('HierarchicalRequirement', query)


def current_stories_with_no_desc(rally):
    """Return the stories in the current iteration with no description."""
    query = RallyQuery("Description = null", current_iteration=True)

    return rally.get('HierarchicalRequirement', query)


def current_stories_with_no_tasks(rally):
    """Return the list of stories in the current iteration with no tasks."""
    query = RallyQuery("TaskStatus = NONE", current_iteration=True)

    return rally.get('HierarchicalRequirement', query)


def current_stories_blocked(rally):
    """Return the list of stories that are blocked."""
    query = RallyQuery("Blocked = true", current_iteration=True)

    return rally.get('HierarchicalRequirement', query)


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


def get_user_attribute_path(entity_name):
    """Get the path to the user associated with entity."""
    return {
        "HierarchicalRequirement": ["Owner"],
        "UserIterationCapacity": ["User"],
        "User": []
    }.get(entity_name, None)


class Ralint(object):

    """Ralint main object."""

    def __init__(self):
        """Ralint constructor."""
        super(Ralint, self).__init__()
        parser = argparse.ArgumentParser()
        parser.add_argument('--teamMembers', nargs='+')
        self.__ralint_args, pyral_args = parser.parse_known_args()
        self.__team_members = self.__ralint_args.teamMembers
        server, user, password, _, _, project = rallyWorkset(pyral_args)
        self.__rally = Rally(server, user, password, project=project)

    def get(self, entity_name, query=None):
        """Wrap the pyral get method."""
        if self.__team_members is not None:
            path = get_user_attribute_path(entity_name)
            if path is not None:
                user_query = []
                path.append("UserName")
                path = ".".join(path)
                for member in self.__team_members:
                    user_query.append("{0} = {1}".format(path, member))
                if query is None:
                    query = RallyQuery(user_query, bool_op='OR')
                else:
                    query.add_term(RallyQuery(user_query, bool_op='OR'))

        if query is None:
            resp = self.__rally.get(entity_name,
                                    projectScopeDown=True)
        else:
            resp = self.__rally.get(entity_name,
                                    query=query(),
                                    projectScopeDown=True)

        if len(resp.errors) > 0:
            print "Could not get '{0}', query='{1}'".format(entity_name,
                                                            query())
            print resp.errors
            raise RuntimeError

        return list(resp)


def output(title, details):
    """Format the output of a check function."""
    if len(details) == 0:
        return

    print '==={0} ({1})'.format(title, len(details))
    print '\n'.join(details)
    print '\n'


def output_stories(title, stories):
    """Format the output of a story check function."""
    output(title, [format_story(s) for s in stories])


def format_story(story):
    """Format the story like US12345: This is a story about Jack and Diane."""
    return '{0}: {1}'.format(story.FormattedID, story.Name)


def _ralint_init():
    """Return an instance of pyral.Rally."""
    return Ralint()


def _run_checkers(rally):
    """Run rally lint checks."""
    output('Users with no current stories',
           [u.Name for u in users_with_no_current_stories(rally)])

    output('Users with too many tasks',
           ['{0} capacity: {1}, task estimate {2}'.format(uic.User.Name,
                                                          uic.Capacity,
                                                          uic.TaskEstimates)
            for uic in users_with_too_many_tasks(rally)])

    output_stories('Current stories with no points',
                   current_stories_with_no_points(rally))

    output_stories('Current stories with no owner',
                   current_stories_with_no_owner(rally))

    output_stories('Current stories with no tasks',
                   current_stories_with_no_tasks(rally))

    output_stories('Current stories with no description',
                   current_stories_with_no_desc(rally))


def ralint():
    """Lint your rally."""
    _run_checkers(_ralint_init())

if __name__ == '__main__':
    ralint()

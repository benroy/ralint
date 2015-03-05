#!/usr/bin/env python
"""docstring for ralint module."""


import argparse
from pyral import Rally, rallyWorkset

__version__ = '0.0.0'


def users_with_no_current_stories(rally):
    """Return list of users with no current stories."""
    query = RallyQuery()
    query.and_current_iteration()
    stories = rally.get('HierarchicalRequirement', query)
    users = set(rally.get('User', RallyQuery()))
    users_with_stories = set([s.Owner for s in stories])
    return users - users_with_stories


def users_with_too_many_tasks(rally):
    """Check if a user has too many tasks."""
    # get user's capacity
    # need a way to default to some value
    query = RallyQuery()
    query.and_current_iteration()
    response = rally.get('UserIterationCapacity', query)

    return [uic for uic in response if uic.TaskEstimates > uic.Capacity]


def current_stories_with_no_points(rally):
    """Return the list of stories in the current iteration with no points."""
    query = RallyQuery()
    query.and_current_iteration()
    query.and_term("PlanEstimate = null")

    return rally.get('HierarchicalRequirement', query=query)


def current_stories_with_no_owner(rally):
    """Return the list of stories in the current iteration with no owner."""
    query = RallyQuery()
    query.and_current_iteration()
    query.and_term("Owner = null")

    return rally.get('HierarchicalRequirement', query)


def current_stories_with_no_desc(rally):
    """Return the stories in the current iteration with no description."""
    query = RallyQuery()
    query.and_current_iteration()
    query.and_term("Description = null")

    return rally.get('HierarchicalRequirement', query)


def current_stories_with_no_tasks(rally):
    """Return the list of stories in the current iteration with no tasks."""
    query = RallyQuery()
    query.and_current_iteration()
    query.and_term("TaskStatus = NONE")

    return rally.get('HierarchicalRequirement', query)


def current_stories_blocked(rally):
    """Return the list of stories that are blocked."""
    query = RallyQuery()
    query.and_current_iteration()
    query.and_term("Blocked = true")

    return rally.get('HierarchicalRequirement', query)


class RallyQuery(object):

    """Rally Query."""

    def __init__(self):
        """Rally Query constructor."""
        super(RallyQuery, self).__init__()
        self.__query_string = None

    def and_term(self, term):
        """AND a term with the query."""
        if self.__query_string is None:
            self.__query_string = "{0}".format(term)
        else:
            self.__query_string = "({0}) AND ({1})".format(self.__query_string,
                                                           term)

    def or_term(self, term):
        """OR a term with the query."""
        if self.__query_string is None:
            self.__query_string = "{0}".format(term)
        else:
            self.__query_string = "({0}) OR ({1})".format(self.__query_string,
                                                          term)

    def and_current_iteration(self):
        """Add current iteration to query."""
        query = RallyQuery()
        query.and_term("Iteration.StartDate < today")
        query.and_term("Iteration.EndDate > today")
        self.and_term(query())

    def __call__(self):
        """Return the query string."""
        return self.__query_string


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

    def get(self, entity_name, query):
        """Wrap the pyral get method."""
        if self.__team_members is not None:
            path = get_user_attribute_path(entity_name)
            if path is not None:
                user_query = RallyQuery()
                path.append("UserName")
                path = ".".join(path)
                for member in self.__team_members:
                    user_query.or_term("{0} = {1}".format(path, member))
                query.and_term(user_query())

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

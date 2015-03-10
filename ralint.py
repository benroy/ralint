#!/usr/bin/env python
"""docstring for ralint module."""


import sys
import os
import argparse
import ConfigParser
import inspect
import re
import types
import pyral

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


def check_stories_with_hi_points(rally):
    """Oversized stories."""
    query = RallyQuery(
        'PlanEstimate >= {0}'.format(rally.options['points_per_iteration']),
        current_iteration=True)

    return [format_artifact(t)
            for t in rally.get('HierarchicalRequirement', query)]


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


def _check_stories_with_incomp_pred(rally):
    """Incomplete dependencies."""
    query = RallyQueryCurrentIteration()
    current_stories = rally.get('HierarchicalRequirement', query)

    unready_stories = {}
    for story in current_stories:
        for pred in story.Predecessors:
            if pred.ScheduleState != 'Accepted':
                unready_stories[story] = (unready_stories[story] or []) + [pred]


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

    def __init__(self, pyral_rally_instance, conf_args):
        """Ralint constructor."""
        super(Ralint, self).__init__()
        self.__rally = pyral_rally_instance
        self.options = conf_args

    def __apply_query_filters(self, entity_name, query):
        """Insert additional terms into query."""
        # if no team_members were specified, return unmodified query
        if not('include_users' in self.options) or self.options['include_users'] is None:
            return query

        path = build_user_name_reference(entity_name)

        # if entity has no user attribute, return unmodified query
        if path is None:
            return query

        # create query that OR's all team_members together
        user_query = RallyQuery(
            ["{0} = {1}".format(path, m) for m in self.options['include_users']],
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


def get_parser():
    """Get Parser."""
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--conf_file',
        help='Specify config file',
        metavar='FILE',
        default=os.path.expanduser('~/.ralint.conf'))

    parser.add_argument(
        '--rally_server',
        help='Rally server domain name',
        default='rally1.rallydev.com')

    parser.add_argument(
        '--rally_user',
        help='User name used to login to Rally',
        default=argparse.SUPPRESS)

    parser.add_argument(
        '--rally_password',
        help='Password used to login to Rally',
        default=argparse.SUPPRESS)

    parser.add_argument(
        '--rally_project',
        help='Rally project',
        default=argparse.SUPPRESS)

    parser.add_argument(
        '--include_users',
        help='Only run checks on items owned by specified users',
        nargs='+',
        metavar='USER_NAME')

    parser.add_argument(
        '--points_per_iteration',
        help='Size of an iteration in points',
        default=8)

    parser.add_argument(
        '--include_checks',
        help='Only run tests that match PATTERN',
        metavar='PATTERN',
        default='.*')

    return parser


class RalintConfig(object):

    """RalintConfig."""

    def __init__(self, cmd_line, conf_files):
        """Initialize RalintConfig."""
        super(RalintConfig, self).__init__()

        parser = get_parser()

        cmd_line_args = parser.parse_args(cmd_line)

        # override with config file specifed in cmd line
        conf_files.append(cmd_line_args.conf_file)

        conf_file_args = {}
        config = ConfigParser.SafeConfigParser()
        if len(config.read(conf_files)) > 0:
            conf_file_args = dict(config.items('ralint'))

        # override with cmdline args
        conf_file_args.update(vars(cmd_line_args))

        self.options = conf_file_args


def _ralint_init():
    """Return an instance of Rally."""
    conf_files = [

        # override with config file from ~
        os.path.expanduser('~/.ralint.conf'),

        # override with enviroment
        os.getenv('RALINT_CONF') or '',

        # override with config file from cwd
        os.path.abspath('.ralint_conf')]

    conf_args = RalintConfig(sys.argv[1:], conf_files).options

    try:
        rally = pyral.Rally(
            conf_args['rally_server'],
            conf_args['rally_user'],
            conf_args['rally_password'],
            project=conf_args['rally_project'])
    except Exception as e:
        print('\nCould not connect to rally')
        print(str(e))
        if 'Pinging' in str(e) or 'ping: unknown host' in str(e):
            print('If you are behind a proxy, '
                  'try setting HTTP_PROXY and HTTPS_PROXY in your env.')
        print('\n\n')
        raise

    return Ralint(rally, conf_args)


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
    check_func_re = re.compile(rally.options['include_checks'])
    for check_func in get_check_functions():
        if check_func_re.search(check_func.__doc__):
            output(check_func.__doc__, check_func(rally))


def ralint():
    """Lint your rally."""
    _run_checkers(_ralint_init())

if __name__ == '__main__':
    ralint()

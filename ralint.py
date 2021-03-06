#!/usr/bin/env python
"""docstring for ralint module."""


import sys
import atexit
import os
import argparse
import ConfigParser
import logging
import logging.handlers
import pprint
import inspect
import re
import types
import pyral
import datetime

__version__ = '0.0.0'


def check_tasks_with_no_owner(rally):
    """Disowned tasks."""
    # Some filters like include_feature can only be applied to stories
    # and story can't be referenced directly from task (only it's ABC can)
    # In order for filters to apply to tasks we have to get (filter) stories
    # separately and do a manual filteing of tasks
    # This logic should ideally be factored out of check function
    tasks = rally.get('Task', RallyQuery("Owner = null"))
    story_ids = [s.ObjectID for s in rally.get('HierarchicalRequirement')]

    return [format_artifact(t) for t in tasks
            if t.WorkProduct.ObjectID in story_ids]


def check_tasks_with_no_estimate(rally):
    """Unestimated tasks."""
    query = RallyQuery(
        ['Estimate = null',
         'Estimate = 0'],
        bool_op='OR')

    tasks = rally.get('Task', query=query)
    story_ids = [s.ObjectID for s in rally.get('HierarchicalRequirement')]

    return [format_artifact(t) for t in tasks
            if t.WorkProduct.ObjectID in story_ids]


def check_users_with_no_capacity(rally):
    """Check for users with no capacity."""
    if 'filter_owner' not in rally.options:
        return []

    uics = rally.get('UserIterationCapacity',
                     RallyQuery('User != null'))
    uwc = [uic.User.UserName for uic in uics]
    return [u for u in rally.options['filter_owner'] if u not in uwc]


def check_users_with_no_stories(rally):
    """Available users."""
    if 'filter_owner' not in rally.options:
        return []

    users = set(rally.options['filter_owner'])
    stories = rally.get('HierarchicalRequirement',
                        RallyQuery('Owner != null'))
    users_with_stories = set([s.Owner.UserName for s in stories])

    return [u for u in users - users_with_stories]


def check_users_with_hi_points(rally):
    """Overstoried users."""
    if 'filter_owner' not in rally.options:
        return []

    if 'points_per_iteration' not in rally.options:
        return []

    stories = rally.get('HierarchicalRequirement',
                        RallyQuery(['Owner != null',
                                    'Iteration != null']))

    uip = [(s.Owner.UserName, s.Iteration.Name, s.PlanEstimate)
           for s in stories]
    info = {}
    for user, itr, points in uip:
        key = user + ', ' + itr
        info[key] = info.get(key, 0) + (points or 0)

    return ['{0}: {1}'.format(ikey, info[ikey])
            for ikey in info.keys()
            if info[ikey] > float(rally.options['points_per_iteration'])]


def check_users_with_lo_points(rally):
    """Understoried users."""
    if 'filter_owner' not in rally.options:
        return []

    if 'points_per_iteration' not in rally.options:
        return []

    stories = rally.get('HierarchicalRequirement',
                        RallyQuery(['Owner != null',
                                    'Iteration != null']))

    uip = [(s.Owner.UserName, s.Iteration.Name, s.PlanEstimate)
           for s in stories]
    info = {}
    for user, itr, points in uip:
        key = itr + ', ' + user
        info[key] = info.get(key, 0) + (points or 0)

    return sorted(['{0}: {1}'.format(ikey, info[ikey])
                   for ikey in info.keys()
                   if info[ikey] < 0.75 *
                   float(rally.options['points_per_iteration'])])


def check_epics_with_too_many_cooks(rally):
    """Too many cooks."""
    epics = {}
    stories = rally.get(
        'HierarchicalRequirement',
        RallyQuery(['DirectChildrenCount = 0',
                    'Parent != null',
                    'Owner != null']))
    for story in stories:
        epics.setdefault(story.Parent.Name, []).append(
            story.Owner.UserName)

    tmc = []
    for epic, owners in epics.iteritems():
        story_count = float(len(owners))
        owner_count = float(len(set(owners)))
        if (story_count > 1
                and owner_count > 2
                and (story_count / owner_count) < 2):
            tmc.append('{0} has {1} stories owned by {2} people'.format(
                epic,
                int(story_count),
                int(owner_count)))

    return tmc


def check_stories_with_hi_points(rally):
    """Oversized stories."""
    query = RallyQuery([
        'PlanEstimate > {0}'.format(rally.options['points_per_iteration']),
        'DirectChildrenCount = 0'])

    return [format_artifact(t)
            for t in rally.get('HierarchicalRequirement', query)]


def check_users_with_too_many_tasks(rally):
    """Overtasked users."""
    # get user's capacity
    # need a way to default to some value
    response = rally.get('UserIterationCapacity')

    uic_list = [uic for uic in response if uic.TaskEstimates > uic.Capacity]

    return ['{0} capacity: {1}, task estimate {2}'.format(uic.User.Name,
                                                          uic.Capacity,
                                                          uic.TaskEstimates)
            for uic in uic_list]


def check_stories_with_incomp_pred(rally):
    """Incomplete dependencies."""
    current_stories = rally.get('HierarchicalRequirement')

    unmet_deps = {}
    for story in current_stories:
        for pred in story.Predecessors:
            if pred.ScheduleState != 'Completed':
                siter = story.Iteration
                piter = pred.Iteration
                if (piter is None or siter.StartDate < piter.StartDate or
                   (siter.StartDate == piter.StartDate and
                    story.Owner.UserName != pred.Owner.UserName)):
                    unmet_deps[story] = unmet_deps.get(story, []) + [pred]

    return [
        '{0} has unmet dependencies:\n    {1}'.format(
            format_artifact(s),
            '\n    '.join([format_artifact(d) for d in unmet_deps[s]]))
        for s in unmet_deps.keys()]


def check_stories_with_no_points(rally):
    """Unestimated stories."""
    query = RallyQuery(
        ['PlanEstimate = null',
         'PlanEstimate = 0'],
        bool_op="OR")

    return [format_artifact(s)
            for s in rally.get('HierarchicalRequirement', query=query)]


def check_stories_with_no_owner(rally):
    """Disowned stories."""
    query = RallyQuery("Owner = null")

    return [format_artifact(s)
            for s in rally.get('HierarchicalRequirement', query=query)]


def check_stories_with_no_desc(rally):
    """Undescribed stories."""
    return [format_artifact(s)
            for s in rally.get('HierarchicalRequirement')
            if len(s.Description) < 140]


def check_stories_with_no_tasks(rally):
    """Untasked stories."""
    query = RallyQuery("TaskStatus = NONE")

    return [format_artifact(s)
            for s in rally.get('HierarchicalRequirement', query=query)]


def check_stories_blocked(rally):
    """Blocked stories."""
    query = RallyQuery("Blocked = true")

    return [format_artifact(s)
            for s in rally.get('HierarchicalRequirement', query=query)]


def check_stories_with_lo_tasks(rally):
    """Undertasked stories."""
    def close_enough(points, task_hours):
        """Are points and task_hours roughly equal."""
        point_hours = (((2 * float(points)) - 1.3) * 8)
        task_hours = float(task_hours)
        numerator = min(point_hours, task_hours)
        denominator = max(point_hours, task_hours)
        return numerator/denominator > 0.5

    return [format_artifact(s)
            for s in rally.get('HierarchicalRequirement',
                               RallyQuery(['PlanEstimate != null',
                                           'TaskEstimateTotal != 0']))
            if not close_enough(s.PlanEstimate, s.TaskEstimateTotal)]


def check_tasks_with_hi_hours(rally):
    """Oversized tasks."""
    return [format_artifact(t)
            for t in rally.get('Task', RallyQuery('Estimate != null'))
            if float(t.Estimate) > 16]


def check_stories_with_no_release(rally):
    """Release-less stories."""
    return [format_artifact(s) for s in rally.get(
        'HierarchicalRequirement',
        RallyQuery('Release = null'))]


def check_stories_with_no_ac(rally):
    """Unacceptable stories."""
    return [format_artifact(s) for s in rally.get(
        'HierarchicalRequirement',
        RallyQuery('Description !contains cceptance'))]


def check_tasks_with_no_update(rally):
    """Outdated tasks."""
    three_days_ago = (datetime.datetime.utcnow() -
                      datetime.timedelta(days=3)).isoformat()

    date_term = 'LastUpdateDate < {0}'.format(three_days_ago)

    return [format_artifact(t) for t in rally.get(
        'Task', RallyQuery(['State = In-Progress', date_term]))]


class RallyQuery(object):

    """Rally Query."""

    def __init__(self, term, bool_op='AND'):
        """Rally Query constructor."""
        super(RallyQuery, self).__init__()

        self.__query_string = None

        self.add_term(term, bool_op)

    @staticmethod
    def __validate_term(term):
        """Raise an exception if term is invalid."""
        if not (isinstance(term, RallyQuery) or
                re.compile(r'^[^\s\(\)]+ [^\s\(\)]+ [^\s\(\)]+$').match(term)):
            raise ValueError('Invalid format. Must be a RallyQuery or a '
                             'string like: X > Y\n{0}'.format(term))

    def add_term(self, term, bool_op='AND'):
        """Add a term to the query."""
        if type(term) in [types.ListType, types.TupleType]:
            for sub_term in term:
                self.add_term(sub_term, bool_op)
        else:
            self.__validate_term(term)
            term = str(term)
            if self.__query_string is None:
                self.__query_string = term
            else:
                self.__query_string = "({0}) {1} ({2})".format(
                    self.__query_string,
                    bool_op,
                    term)
        return self

    def ___unicode__(self):
        """Return the query string."""
        return u'{0}'.format(str(self))

    def __str__(self):
        """Return the query string."""
        return self.__query_string


def build_attribute_reference(entity_name, attr):
    """Get the path to the user associated with entity."""
    attr_ref = {
        'feature': {
            'HierarchicalRequirement': 'Feature.FormattedID'
        },
        'iteration': {
            'HierarchicalRequirement': 'Iteration',
            'UserIterationCapacity':   'Iteration',
            'Task':                    'Iteration',
            'Iteration':               ''
        },
        'owner': {
            'HierarchicalRequirement': 'Owner.UserName',
            'UserIterationCapacity':   'User.UserName',
            'Task':                    'Owner.UserName',
            'User':                    'UserName'
        }}.get(attr, {}).get(entity_name, None)

    if attr_ref is None:
        return

    return attr_ref


class RalintFilter(object):

    """Ralint Filter."""

    def __init__(self):
        """Initialize RalintFilter."""
        super(RalintFilter, self).__init__()

    def apply(self, entity_name, query, options):
        """Apply filters."""
        # if no team_members were specified, return unmodified query

        apply_func = {
            'owner':     self.__apply_user_filter,
            'iteration': self.__apply_iter_filter,
            'feature':   self.__apply_feat_filter
        }

        for attr in apply_func.keys():
            key = 'filter_{0}'.format(attr)
            if key not in options or not options[key]:
                continue

            path = build_attribute_reference(entity_name, attr)

            # if entity has no user attribute, return unmodified query
            if path is None:
                return query

            filter_query = apply_func[attr](path, options['filter_' + attr])

            # if initial query was empty, return user_query
            if query is None:
                query = filter_query
            else:
                # or add user_query to existing query
                query.add_term(filter_query)

        return query

    def __apply_user_filter(self, path, users):
        """Insert additional terms into query."""
        # create query that OR's all team_members together
        return RallyQuery(
            ["{0} = {1}".format(path, m)
             for m in users],
            bool_op='OR')

    def __apply_iter_filter(self, path, iters):
        """Apply iteration filter."""
        if iters == ['current']:
            return RallyQuery([
                path + '.StartDate' + ' <= today',
                path + '.EndDate' + ' >= today'
            ])
        elif iters == ['future']:
            return RallyQuery(
                path + '.EndDate' + ' >= today')
        else:
            raise ValueError('unknown filter_iteration value: ' + str(iters))

    def __apply_feat_filter(self, path, features):
        """Apply feature filter."""
        return RallyQuery(
            ["{0} = {1}".format(path, f)
             for f in features],
            bool_op='OR')


class Ralint(object):

    """Ralint main object."""

    def __init__(self, pyral_rally_instance, conf_args):
        """Ralint constructor."""
        super(Ralint, self).__init__()
        self.__rally = pyral_rally_instance
        self.options = conf_args

    def get(self, entity_name, query=None):
        """
        Wrap the pyral get method.

        Does several things (should only do one?)
        1) Inserts user terms into query if team_members are specified
        2) Inserts additional projectScopeDown arg into pyral.Rally.get
        3) Does some minimal, generic error "handling"
        4) Coverts pyral's response object to a list of entities
        """
        query = RalintFilter().apply(entity_name, query, self.options)

        log().info('GET entity=%s query=%s', entity_name, str(query))

        pyral_resp = self.__rally.get(entity_name,
                                      query=str(query),
                                      projectScopeDown=True)

        if len(pyral_resp.errors) > 0:
            errs = '\n'.join(pyral_resp.errors)
            log().error("Could not get %s, query=%s\n%s",
                        entity_name,
                        str(query),
                        errs)
            raise RuntimeError(errs)

        return list(pyral_resp)


def output(title, details):
    """Format the output of a check function."""
    print('==={0} ({1})'.format(title, len(details)))

    if not details or len(details) == 0:
        return

    print('\n'.join(details))
    print('\n')


def format_artifact(story):
    """Format artifact like US12345: This is a story about Jack and Diane."""
    return '{0}: {1}'.format(story.FormattedID, story.Name)


def parse_cmd_line(cmd_line):
    """Parse command line."""
    log().info('command line:' + str(cmd_line))

    # User/Pass are required but can either be in the cmd_line or config file.
    # This is harder than it seems it should be. We do it in three steps.
    #
    # Step 1 is a pre-parser that extracts the user, pass and conf file and
    # removes them from the cmd line (if they're specified). This pre-parser
    # will not exit or print a usage message if there are problems with the
    # command line.
    #
    # Step 2 is to completely parse all config files. If we parse one or more
    # user/pass values, we choose the one from the "best" sounce and append it
    # to the cmd_line. The best source the cmd_line, followed by conf_files.
    #
    # Step 3 is to completly parse the full command line, including user/pass
    # which may have come from a config file. This parser requires user and
    # pass and will exit and print a usage message if they aren't specified
    # (or if there are any other issues with the cmd_line).

    # Step 1, pre-parse cmd-line to extract user, pass, conf_file
    pre_parser = argparse.ArgumentParser(
        add_help=False,
        argument_default=argparse.SUPPRESS)
    pre_parser.add_argument('--conf_file')
    pre_parser.add_argument('--rally_user')
    pre_parser.add_argument('--rally_password')
    cmd_args = None

    # Do not print usage or exit if parser throws an exeption
    pre_parse_error = False
    pre_parser.print_usage = lambda _: {}
    try:
        cmd_args, cmd_line = pre_parser.parse_known_args(cmd_line)
        cmd_args = vars(cmd_args)
        log().info('pre-parsed: ' + str(cmd_args))
    except BaseException:
        log().warn('Error during pre-parsing.')
        pre_parse_error = True

    # Step 2, parse config files. If Step 1 failed, we can skip to Step 3,
    # which is also guaranteed to fail, but it will give a nice usage message
    # and exit
    default_args = {}
    if not pre_parse_error:
        conf_files = [

            # config file in ~ lowest priority
            os.path.expanduser('~/.ralint.conf'),

            # config file specified by env is higher
            os.getenv('RALINT_CONF') or '',

            # a config file in cwd would be higher still
            os.path.abspath('.ralint.conf')]

        # but the highest priority conf file would be the one
        # specified on the cmd line.
        if 'conf_file' in cmd_args:
            conf_files.append(cmd_args['conf_file'])

        log().info('parsing config files:' +
                   ', '.join(conf_files))

        config = ConfigParser.SafeConfigParser()
        if len(config.read(conf_files)) > 0:
            default_args = dict(config.items('ralint'))

            # FIXME: Hardcoded hack for user name list
            default_args['filter_owner'] = default_args.get(
                'filter_owner', '').split()

        log().info('args parsed from config files:\n' +
                   pprint.pformat(default_args, width=1))

        # extract username and password and append them
        # to cmd_line to be parsed by main parser
        default_args.update(cmd_args)
        for k in ['rally_user', 'rally_password']:
            if k in default_args:
                cmd_line.extend(['--' + k, default_args[k]])

    # Step 3, parse like normal
    main_parser = argparse.ArgumentParser()

    main_parser.add_argument(
        '--rally_user',
        help='Rally user name.',
        required=True)

    main_parser.add_argument(
        '--rally_password',
        help='Rally password.',
        required=True)

    main_parser.add_argument(
        '--conf_file',
        metavar='FILE',
        help='Configuration file. Defaults to ~/.ralint.conf')

    main_parser.add_argument(
        '--rally_server',
        help='Rally server domain name.',
        default='rally1.rallydev.com')

    main_parser.add_argument(
        '--rally_project',
        help='Rally project.',
        default=argparse.SUPPRESS)

    main_parser.add_argument(
        '--points_per_iteration',
        help='Size of an iteration in points.',
        default=8)

    main_parser.add_argument(
        '--include_checks',
        help='Only run checks that match PATTERN.',
        nargs='+',
        metavar='PATTERN',
        default=['.*'])

    main_parser.add_argument(
        '--filter_owner',
        help='Only check items owned by USER_NAME.',
        nargs='+',
        metavar='USER_NAME',
        default=argparse.SUPPRESS)

    main_parser.add_argument(
        '--filter_iteration',
        help='Only check items scheduled for ITERATION. '
             'Default is current iteration.',
        nargs='+',
        metavar='ITERATION',
        default=['current'])

    main_parser.add_argument(
        '--filter_feature',
        help='Only check items that are part of FEATURE.',
        nargs='+',
        metavar='FEATURE',
        default=argparse.SUPPRESS)

    log().info('final parsing: ' + str(cmd_line))

    # override with cmdline args
    cmd_args = main_parser.parse_args(cmd_line)
    default_args.update(vars(cmd_args))

    log().info('args:\n' +
               pprint.pformat(default_args, width=1))

    return default_args


def _ralint_init():
    """Return an instance of Rally."""
    conf_args = parse_cmd_line(sys.argv[1:])

    log().info('Config: ' + pprint.pformat(conf_args, width=1))

    try:
        rally = pyral.Rally(
            conf_args['rally_server'],
            conf_args['rally_user'],
            conf_args['rally_password'],
            project=conf_args['rally_project'])
    except Exception as ex:
        print('\nCould not connect to rally')
        print(str(ex))
        if 'Pinging' in str(ex) or 'ping: unknown host' in str(ex):
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
    check_func_res = [re.compile(c) for c in rally.options['include_checks']]
    for check_func in get_check_functions():
        for check_func_re in check_func_res:
            if check_func_re.search(check_func.__doc__):
                output(check_func.__doc__, check_func(rally))
                break


def ralint():
    """Lint your rally."""
    _run_checkers(_ralint_init())


def log():
    """Get the module logger."""
    return logging.getLogger(__name__)


def _configure_logging():
    """Configure logging."""
    logger = log()

    logger.setLevel(logging.DEBUG)

    # create console handler and set level to debug
    chan = logging.handlers.RotatingFileHandler(
        os.path.expanduser('~/.ralint.log'),
        maxBytes=1024*1024,
        backupCount=5)
    chan.setLevel(logging.DEBUG)

    # create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # add formatter to ch
    chan.setFormatter(formatter)

    # add ch to logger
    logger.addHandler(chan)

    logger.info('Log started')


@atexit.register
def exit_handler():
    """Do stuff on exit."""
    log().info('Exit')


_configure_logging()

if __name__ == '__main__':
    ralint()

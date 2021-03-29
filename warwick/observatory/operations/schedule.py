#
# This file is part of opsd.
#
# opsd is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# opsd is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with opsd.  If not, see <http://www.gnu.org/licenses/>.

"""Helper functions for validating and parsing schedule JSON objects into actions"""

import datetime
import sys
import traceback
import jsonschema
from skyfield import almanac
from skyfield.api import Loader


def __create_validator(config, night):
    """Returns a template validator that includes support for the
       custom schema tags used by the observation schedules:
            require-night: add to string properties to require times between sunset and sunrise
                           on the schema's defined date
    """
    validators = dict(jsonschema.Draft4Validator.VALIDATORS)

    loader = Loader('/var/tmp/')
    ts = loader.timescale()
    eph = loader('de421.bsp')

    sun_above_horizon = almanac.risings_and_settings(eph, eph['Sun'], config.site_location)

    # Search for sunset/sunrise between midday on 'night' and midday the following day
    night_date = datetime.datetime.strptime(night, '%Y-%m-%d')
    night_search_start = ts.utc(night_date.year, night_date.month, night_date.day, 12)
    night_search_end = ts.tt_jd(night_search_start.tt + 1)
    events, _ = almanac.find_discrete(night_search_start, night_search_end, sun_above_horizon)
    night_start = events[0].utc_datetime()
    night_end = events[1].utc_datetime()

    # pylint: disable=unused-argument
    def require_night(validator, value, instance, schema):
        """Create a validator object that forces a tagged date to match
           the night defined in the observing plan
        """
        try:
            date = datetime.datetime.strptime(instance, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc)
        except Exception:
            yield jsonschema.ValidationError('{} is not a valid datetime'.format(instance))
            return

        if value and (date < night_start or date > night_end):
            start_str = night_start.strftime('%Y-%m-%dT%H:%M:%SZ')
            end_str = night_end.strftime('%Y-%m-%dT%H:%M:%SZ')
            yield jsonschema.ValidationError("{} is not between {} and {}".format(
                instance, start_str, end_str))
    # pylint: enable=unused-argument

    validators['require-night'] = require_night
    return jsonschema.validators.create(meta_schema=jsonschema.Draft4Validator.META_SCHEMA,
                                        validators=validators)


def __validate_schema(validator, schema, block):
    try:
        errors = []
        for error in sorted(validator(schema).iter_errors(block), key=lambda e: e.path):
            if error.path:
                path = '->'.join([str(p) for p in error.path])
                message = path + ': ' + error.message
            else:
                message = error.message
            errors.append(message)
    except Exception:
        traceback.print_exc(file=sys.stdout)
        errors = ['exception while validating']
    return errors


def __validate_dome(validator, block):
    """Returns a list of error messages that stop json from defining a valid dome schedule"""
    try:
        schema = {
            'type': 'object',
            'additionalProperties': False,
            'required': ['open', 'close'],
            'properties': {
                'open': {
                    'type': 'string',
                    'format': 'date-time',
                    'require-night': True
                },
                'close': {
                    'type': 'string',
                    'format': 'date-time',
                    'require-night': True
                }
            }
        }

        errors = __validate_schema(validator, schema, block)
    except Exception as e:
        print(e)
        errors = ['exception while validating']

    # Prefix each message with the action index and type
    return ['dome: ' + e for e in errors]


def __validate_action(validator, index, block, action_types):
    """Validates an action block and returns a list of any schema violations"""
    if 'type' not in block:
        return ['action ' + str(index) + ": missing key 'type'"]

    if block['type'] not in action_types:
        return ['action ' + str(index) + ": unknown action type '" + block['type'] + "'"]

    try:
        schema = action_types[block['type']].validation_schema()
        if schema is not None:
            errors = __validate_schema(validator, schema, block)
        else:
            errors = ['validation not implemented']
    except Exception:
        traceback.print_exc(file=sys.stdout)
        errors = ['exception while validating']

    # Prefix each message with the action index and type
    return ['action ' + str(index) + ' (' + block['type'] + '): ' + e for e in errors]


def validate_schedule(json, config):
    """
    Tests whether a json object defines a valid opsd schedule
    Returns a tuple of (valid, messages) where:
       valid is a boolean indicating whether the schedule is valid
       messages is a list of strings describing errors in the schedule
    """

    # Schedule requires a night to be defined
    if 'night' not in json:
        return False, ['syntax error: missing key \'night\'']

    # TODO: Require schedule to be for tonight!

    validator = __create_validator(config, json['night'])

    if 'dome' in json:
        errors = __validate_dome(validator, json['dome'])
    else:
        errors = []

    if 'actions' in json:
        if isinstance(json['actions'], list):
            for i, action in enumerate(json['actions']):
                errors.extend(__validate_action(validator, i, action, config.actions))
        else:
            errors.append('syntax: error \'actions\' must be a list')
    else:
        errors.append('syntax error: missing key \'actions\'')

    return not errors, errors


def schedule_is_tonight(json):
    """Returns true if a given schedule is valid to execute tonight"""
    # TODO: Implement me!
    pass


def parse_schedule_actions(json, action_types):
    """
    Parses a json object into a list of TelescopeActions
    to be run by the telescope control thread
    """
    actions = []
    try:
        for action in json['actions']:
            actions.append(action_types[action['type']](action))
    except Exception:
        print('exception while parsing schedule')
        traceback.print_exc(file=sys.stdout)
        return []
    return actions


def parse_dome_window(json):
    """
    Parses dome open and close dates from a schedule
    Returns a tuple of the open and close dates
    or None if the json does not define a dome block
    """
    if 'dome' in json and 'open' in json['dome'] and 'close' in json['dome']:
        # These dates have already been validated by __validate_dome
        open_date = datetime.datetime.strptime(json['dome']['open'], '%Y-%m-%dT%H:%M:%SZ')
        close_date = datetime.datetime.strptime(json['dome']['close'], '%Y-%m-%dT%H:%M:%SZ')
        return open_date, close_date

    return None

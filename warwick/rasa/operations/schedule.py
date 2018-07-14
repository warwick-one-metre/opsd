#!/usr/bin/env python3
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

# pylint: disable=too-many-instance-attributes
# pylint: disable=too-few-public-methods
# pylint: disable=too-many-branches
# pylint: disable=broad-except
# pylint: disable=invalid-name

import datetime
import ephem
import jsonschema

# Action types
from .actions import FocusSweep, SkyFlats, TestHorizonImage, Wait

# Measured from GPS receiver
SITE_LATITUDE = 28.7603135
SITE_LONGITUDE = -17.8796168
SITE_ELEVATION = 2387

ACTION_TYPES = {
    'FocusSweep': FocusSweep,
    'SkyFlats': SkyFlats,
    'TestHorizonImage': TestHorizonImage,
    'Wait': Wait
}

def __create_validator(night):
    """Returns a template validator that includes support for the
       custom schema tags used by the observation schedules:
            require-night: add to string properties to require times between sunset and sunrise
                           on the schema's defined date
    """
    validators = dict(jsonschema.Draft4Validator.VALIDATORS)

    # Calculate the night start and end times
    # pylint: disable=assigning-non-slot
    # pylint: disable=no-member
    obs = ephem.Observer()
    obs.lat = SITE_LATITUDE*ephem.degree
    obs.lon = SITE_LONGITUDE*ephem.degree
    obs.elev = SITE_ELEVATION
    obs.date = datetime.datetime.strptime(night, '%Y-%m-%d') + datetime.timedelta(hours=12)
    night_start = obs.next_setting(ephem.Sun()).datetime()
    night_end = obs.next_rising(ephem.Sun()).datetime()
    # pylint: enable=no-member
    # pylint: enable=assigning-non-slot

    # Ensure that tagged dates occur on the same night as the observation
    def require_night(validator, value, instance, schema):
        try:
            date = datetime.datetime.strptime(instance, '%Y-%m-%dT%H:%M:%SZ')
        except Exception:
            yield jsonschema.ValidationError('{} is not a valid datetime'.format(instance))
            return

        if value and (date < night_start or date > night_end):
            yield jsonschema.ValidationError("{} is not between {} and {}".format(date, night_start, night_end))

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
    except Exception as e:
        print(e)
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

def __validate_action(validator, index, block):
    """Validates an action block and returns a list of any schema violations"""
    if 'type' not in block:
        return ['action ' + str(index) + ": missing key 'type'"]

    if block['type'] not in ACTION_TYPES:
        return ['action ' + str(index) + ": unknown action type '" + block['type'] + "'"]

    try:
        schema = ACTION_TYPES[block['type']].validation_schema()
        if schema is not None:
            errors = __validate_schema(validator, schema, block)
        else:
            errors = ['validation not implemented']
    except Exception as e:
        print(e)
        errors = ['exception while validating']

    # Prefix each message with the action index and type
    return ['action ' + str(index) + ' (' + block['type'] + '): ' + e for e in errors]

def validate_schedule(json):
    """Tests whether a json object defines a valid opsd schedule
       Returns a tuple of (valid, messages) where:
          valid is a boolean indicating whether the schedule is valid
          messages is a list of strings describing errors in the schedule
    """

    # Schedule requires a night to be defined
    if 'night' not in json:
        return False, ['syntax error: missing key \'night\'']

    try:
        validator = __create_validator(json['night'])
    except Exception as e:
        pass

    if 'dome' in json:
        errors = __validate_dome(validator, json['dome'])
    else:
        errors = []

    if 'actions' in json:
        if isinstance(json['actions'], list):
            for i, action in enumerate(json['actions']):
                errors.extend(__validate_action(validator, i, action))
        else:
            errors.append('syntax: error \'actions\' must be a list')
    else:
        errors.append('syntax error: missing key \'actions\'')

    return not errors, errors

def schedule_is_tonight(json):
    """Returns true if a given schedule is valid to execute tonight"""

def parse_schedule_actions(json):
    """Parses a json object into a list of TelescopeActions
       to be run by the telescope control thread"""
    actions = []
    try:
        for action in json['actions']:
            actions.append(ACTION_TYPES[action['type']](action))
    except Exception as e:
        print('exception while parsing schedule')
        print(e)
        return []
    return actions

def parse_schedule_dome_times(json):
    """Parses dome open and close times from a schedule"""
    return None, None

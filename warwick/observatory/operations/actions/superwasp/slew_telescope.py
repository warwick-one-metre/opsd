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

"""Telescope action to slew the telescope to a given ra, dec"""

from warwick.observatory.operations import TelescopeAction, TelescopeActionStatus
from .telescope_helpers import tel_slew_radec, tel_stop

SLEW_TIMEOUT = 120


class SlewTelescope(TelescopeAction):
    """Telescope action to slew the telescope to a given ra, dec"""
    def __init__(self, config):
        super().__init__('Slew Telescope', config)

    @classmethod
    def validation_schema(cls):
        return {
            'type': 'object',
            'additionalProperties': False,
            'required': ['ra', 'dec', 'tracking'],
            'properties': {
                'type': {'type': 'string'},
                'ra': {
                    'type': 'number',
                    'minimum': 0,
                    'maximum': 360
                },
                'dec': {
                    'type': 'number',
                    'minimum': -30,
                    'maximum': 85
                },
                'tracking': {
                    'type': 'boolean'
                }
            }
        }

    def run_thread(self):
        """Thread that runs the hardware actions"""
        self.set_task('Slewing')
        if not tel_slew_radec(self.log_name, self.config['ra'], self.config['dec'],
                              self.config['tracking'], SLEW_TIMEOUT):
            self.status = TelescopeActionStatus.Error
            return

        self.status = TelescopeActionStatus.Complete

    def abort(self):
        """Notification called when the telescope is stopped by the user"""
        super().abort()
        tel_stop(self.log_name)

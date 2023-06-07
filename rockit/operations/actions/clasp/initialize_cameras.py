#
# This file is part of the Robotic Observatory Control Kit (rockit)
#
# rockit is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# rockit is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with rockit.  If not, see <http://www.gnu.org/licenses/>.

"""Telescope action to power on and cool the cameras"""
import sys
import threading
import traceback
import Pyro4
from astropy.time import Time
import astropy.units as u
from rockit.common import daemons, log, validation
from rockit.operations import TelescopeAction, TelescopeActionStatus
from .camera_helpers import cameras, cam_initialize, cam_status

CAMERA_POWERON_DELAY = 5

# Interval (in seconds) to poll the camera for temperature lock
CAMERA_CHECK_INTERVAL = 10

# Exit with an error if temperatures haven't locked after this many seconds
CAMERA_COOLING_TIMEOUT = 900


class InitializeCameras(TelescopeAction):
    """
    Telescope action to power on and cool the cameras.

    Example block:
    {
        "type": "InitializeCameras",
        "start": "2022-09-18T22:20:00", # Optional: defaults to immediately
        "cameras": ["cam1", "cam2"]
    }
    """
    def __init__(self, log_name, config):
        super().__init__('Initializing Cameras', log_name, config)
        if 'start' in config:
            self._start_date = Time(config['start'])
        else:
            self._start_date = None

        self._wait_condition = threading.Condition()

    def __wait_for_temperature_lock(self):
        """Waits until all cameras have reached their target temperature
           Returns True on success, False on error
        """
        # Wait for cameras to cool if required
        self.set_task('Cooling cameras')
        locked = {camera_id: False for camera_id in self.config['cameras']}

        start = Time.now()
        while not self.aborted:
            if (Time.now() - start) > CAMERA_COOLING_TIMEOUT * u.s:
                return False

            for camera_id in self.config['cameras']:
                status = cam_status(self.log_name, camera_id)
                if 'temperature_locked' not in status:
                    log.error(self.log_name, 'Failed to check temperature on camera ' + camera_id)
                    return False

                locked[camera_id] = status['temperature_locked']

            if all(locked[k] for k in locked):
                break

            with self._wait_condition:
                self._wait_condition.wait(CAMERA_CHECK_INTERVAL)
        return not self.aborted

    def run_thread(self):
        """Thread that runs the hardware actions"""
        if self._start_date is not None and Time.now() < self._start_date:
            self.set_task(f'Waiting until {self._start_date.strftime("%H:%M:%S")}')
            if not self.wait_until_time_or_aborted(self._start_date, self._wait_condition):
                self.status = TelescopeActionStatus.Complete
                return

        # Power cameras on if needed
        switched = False
        try:
            with daemons.clasp_power.connect() as powerd:
                p = powerd.last_measurement()
                for camera_id in self.config['cameras']:
                    if camera_id in p and not p[camera_id]:
                        switched = True
                        powerd.switch(camera_id, True)
        except Pyro4.errors.CommunicationError:
            log.error(self.log_name, 'Failed to communicate with power daemon')
        except Exception:
            log.error(self.log_name, 'Unknown error with power daemon')
            traceback.print_exc(file=sys.stdout)

        if switched:
            # Wait for cameras to power up
            with self._wait_condition:
                self._wait_condition.wait(CAMERA_POWERON_DELAY)

        self.set_task('Initializing Cameras')
        for camera_id in self.config['cameras']:
            if not cam_initialize(self.log_name, camera_id):
                self.status = TelescopeActionStatus.Error
                return

        locked = self.__wait_for_temperature_lock()
        if self.aborted or locked:
            self.status = TelescopeActionStatus.Complete
        else:
            self.status = TelescopeActionStatus.Error

    def abort(self):
        """Notification called when the telescope is stopped by the user"""
        super().abort()
        with self._wait_condition:
            self._wait_condition.notify_all()

    @classmethod
    def validate_config(cls, config_json):
        """Returns an iterator of schema violations for the given json configuration"""
        return validation.validation_errors(config_json, {
            'type': 'object',
            'additionalProperties': False,
            'required': ['cameras'],
            'properties': {
                'type': {'type': 'string'},

                'cameras': {
                    'type': 'array',
                    'items': {
                        'type': 'string',
                        'enum': cameras.keys()
                    }
                },

                # Optional
                'start': {
                    'type': 'string',
                    'format': 'date-time',
                }
            }
        })
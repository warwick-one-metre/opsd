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

"""Telescope action to acquire sky flats"""

# pylint: disable=too-many-return-statements
# pylint: disable=too-many-branches

import datetime
import sys
import threading
import traceback
import Pyro4

from astropy.coordinates import get_sun, EarthLocation, AltAz
from astropy.time import Time
from astropy import units as u

from warwick.observatory.operations import TelescopeAction, TelescopeActionStatus
from warwick.observatory.common import log, validation
from warwick.observatory.pipeline import configure_flats_validation_schema as pipeline_schema
from warwick.observatory.camera.atik import configure_validation_schema as camera_schema
from .telescope_helpers import tel_status, tel_slew_altaz
from .camera_helpers import cameras, cam_stop
from .pipeline_helpers import pipeline_enable_archiving, configure_pipeline

SLEW_TIMEOUT = 120

# Note: pipeline and camera schemas are inserted in the validate_config method
CONFIG_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['evening'],
    'properties': {
        'type': {'type': 'string'},
        'evening': {
            'type': 'boolean'
        }
    }
}

class AutoFlatState:
    """Possible states of the AutoFlat routine"""
    Waiting, Saving, Complete, Error = range(4)
    Names = ['Waiting', 'Saving', 'Complete', 'Error']
    Codes = ['W', 'S', 'C', 'E']

CONFIG = {
    # We can't take a bias without a shutter, so subtract an approximate level from all pixels
    # TODO: Measure this properly
    'bias_signal': 1300,

    # Range of sun angles where we can acquire useful data
    'max_sun_altitude': -6,
    'min_sun_altitude': -10,
    'sun_altitude_check_interval': 30,

    # Exposure fudge factor to account for changing sky brightness
    'evening_scale': 1.07,
    'dawn_scale': 0.9,

    # Clamp exposure time deltas to this range (e.g. 5 -> 15 or 5 -> 1.6)
    'max_exposure_delta': 3,

    # Number of seconds to add to the exposure time to account for readout + object detection
    # Consider the frame lost if this is exceeded
    'max_processing_time': 20,

    # Exposure limits in seconds
    'min_exposure': 0.1,
    'max_exposure': 30,

    # Exposures shorter than this will be discarded
    'min_save_exposure': 1,

    # Exposures with less counts than this lack the signal to noise ratio that we desire
    'min_save_counts': 15000,

    # Target flat counts to aim for
    'target_counts': 30000,
}


def sun_position(location):
    """Returns current (alt, az) of sun in degrees for the given location"""
    now = Time(datetime.datetime.utcnow(), format='datetime', scale='utc')
    frame = AltAz(obstime=now, location=location)
    sun = get_sun(now).transform_to(frame)
    return sun.alt.value, sun.az.value


class CameraWrapper:
    """Holds camera-specific flat state"""
    def __init__(self, camera_id, daemon, camera_config, is_evening, log_name):
        self.camera_id = camera_id
        self.state = AutoFlatState.Waiting
        self._daemon = daemon
        self._log_name = log_name
        self._camera_config = camera_config
        self._expected_complete = datetime.datetime.utcnow()
        self._is_evening = is_evening
        self._bias_signal = CONFIG['bias_signal']
        self._scale = CONFIG['evening_scale'] if is_evening else CONFIG['dawn_scale']
        self._start_exposure = CONFIG['min_exposure'] if is_evening else CONFIG['min_save_exposure']
        self._start_time = None
        self._exposure_count = 0

    def start(self):
        """Starts the flat sequence for this camera"""
        with self._daemon.connect() as cam:
            cam.configure(self._camera_config, quiet=True)

        self.__take_image(self._start_exposure)
        self._start_time = datetime.datetime.utcnow()

    def check_timeout(self):
        """Sets error state if an expected frame is more than 30 seconds late"""
        if self.state not in [AutoFlatState.Waiting, AutoFlatState.Saving]:
            return

        if datetime.datetime.utcnow() > self._expected_complete:
            print('AutoFlat: camera ' + self.camera_id + ' exposure timed out')
            log.error(self._log_name, 'AutoFlat: camera ' + self.camera_id + ' exposure timed out')
            self.state = AutoFlatState.Error

    def __take_image(self, exposure):
        """Tells the camera to take an exposure.
           if exposure is 0 then it will reset the camera
           configuration and take a bias with the shutter closed
        """
        self._expected_complete = datetime.datetime.utcnow() \
            + datetime.timedelta(seconds=exposure + CONFIG['max_processing_time'])
        try:
            with self._daemon.connect() as cam:
                cam.set_exposure(exposure, quiet=True)
                cam.start_sequence(1, quiet=True)
        except Pyro4.errors.CommunicationError:
            log.error(self._log_name, 'Failed to communicate with camera ' + self.camera_id)
            self.state = AutoFlatState.Error
        except Exception:
            log.error(self._log_name, 'Unknown error with camera ' + self.camera_id)
            traceback.print_exc(file=sys.stdout)
            self.state = AutoFlatState.Error

    def received_frame(self, headers):
        """Callback to process an acquired frame. headers is a dictionary of header keys"""
        last_state = self.state
        if self.state == AutoFlatState.Waiting or self.state == AutoFlatState.Saving:
            if self.state == AutoFlatState.Saving:
                self._exposure_count += 1

            exposure = headers['EXPTIME']
            counts = headers['MEDCNTS'] - self._bias_signal

            # If the count rate is too low then we scale the exposure by the maximum amount
            if counts > 0:
                new_exposure = self._scale * exposure * CONFIG['target_counts'] / counts
            else:
                new_exposure = exposure * CONFIG['max_exposure_delta']

            # Clamp the exposure to a sensible range
            clamped_exposure = min(new_exposure, CONFIG['max_exposure'], exposure * CONFIG['max_exposure_delta'])
            clamped_exposure = max(clamped_exposure, CONFIG['min_exposure'], exposure / CONFIG['max_exposure_delta'])

            clamped_desc = ' (clamped from {:.2f}s)'.format(new_exposure) if new_exposure > clamped_exposure else ''
            print('AutoFlat: camera {} exposure {:.2f}s counts {:.0f} ADU -> {:.2f}s{}'
                  .format(self.camera_id, exposure, counts, clamped_exposure, clamped_desc))

            if self._is_evening:
                # Sky is decreasing in brightness
                if clamped_exposure == CONFIG['max_exposure'] and counts < CONFIG['min_save_counts']:
                    self.state = AutoFlatState.Complete
                elif self.state == AutoFlatState.Waiting and counts > CONFIG['min_save_counts'] \
                        and new_exposure > CONFIG['min_save_exposure']:
                    self.state = AutoFlatState.Saving
            else:
                # Sky is increasing in brightness
                if clamped_exposure < CONFIG['min_save_exposure']:
                    self.state = AutoFlatState.Complete
                elif self.state == AutoFlatState.Waiting and counts > CONFIG['min_save_counts']:
                    self.state = AutoFlatState.Saving

            if self.state != last_state:
                archive = self.state == AutoFlatState.Saving
                if not pipeline_enable_archiving(self._log_name, self.camera_id.upper(), archive):
                    self.state = AutoFlatState.Error
                    return

                print('AutoFlat: camera ' + self.camera_id + ' ' + AutoFlatState.Names[last_state] +
                      ' -> ' + AutoFlatState.Names[self.state])

                if self.state == AutoFlatState.Saving:
                    log.info(self._log_name, 'AutoFlat: {} saving enabled'.format(self.camera_id))
                elif self.state == AutoFlatState.Complete:
                    runtime = (datetime.datetime.utcnow() - self._start_time).total_seconds()
                    message = 'AutoFlat: camera {} acquired {} flats in {:.0f} seconds'.format(
                        self.camera_id, self._exposure_count, runtime)
                    log.info(self._log_name, message)

            if self.state != AutoFlatState.Complete:
                self.__take_image(clamped_exposure)

    def abort(self):
        """Aborts any active exposures and sets the state to complete"""
        if self.state == AutoFlatState.Saving:
            cam_stop(self._log_name, self.camera_id)
        self.state = AutoFlatState.Complete


class SkyFlats(TelescopeAction):
    """Telescope action to acquire sky flats"""
    def __init__(self, log_name, config):
        super().__init__('Sky Flats', log_name, config)
        self._wait_condition = threading.Condition()

        self._cameras = {}
        for camera_id, camera_daemon in cameras.items():
            self._cameras[camera_id] = CameraWrapper(camera_id, camera_daemon, self.config.get(camera_id, {}),
                                                     self.config['evening'], self.log_name)

    @classmethod
    def validate_config(cls, config_json):
        """Returns an iterator of schema violations for the given json configuration"""
        schema = {}
        schema.update(CONFIG_SCHEMA)
        for camera_id in cameras:
            schema['properties'][camera_id] = camera_schema(camera_id)

        schema['properties']['pipeline'] = pipeline_schema()

        return validation.validation_errors(config_json, schema)

    def run_thread(self):
        """Thread that runs the hardware actions"""
        # Query site location from the telescope
        ts = tel_status(self.log_name)
        if not ts:
            self.status = TelescopeActionStatus.Error
            return

        # pylint: disable=no-member
        location = EarthLocation(lat=ts['site_latitude'] * u.deg,
                                 lon=ts['site_longitude'] * u.deg,
                                 height=ts['site_elevation'] * u.m)
        # pylint: enable=no-member

        # Configure pipeline immediately so the dashboard can show target name etc
        # Archiving will be enabled when the brightness is inside the required range
        pipeline_config = {}
        pipeline_config.update(self.config['pipeline'])
        pipeline_config.update({
            'intstats': True,
            'type': 'FLAT',
        })

        if not configure_pipeline(self.log_name, pipeline_config):
            self.status = TelescopeActionStatus.Error
            return

        while not self.aborted:
            waiting_for = []
            sun_altitude = sun_position(location)[0]
            if self.config['evening']:
                if sun_altitude < CONFIG['min_sun_altitude']:
                    print('AutoFlat: Sun already below minimum altitude')
                    log.info(self.log_name, 'AutoFlat: Sun already below minimum altitude')
                    self.status = TelescopeActionStatus.Complete
                    return

                if sun_altitude < CONFIG['max_sun_altitude'] and self.dome_is_open:
                    break

                if not self.dome_is_open:
                    waiting_for.append('Dome')

                if sun_altitude >= CONFIG['max_sun_altitude']:
                    waiting_for.append('Sun < {:.1f} deg'.format(CONFIG['max_sun_altitude']))

                print('AutoFlat: {:.1f} > {:.1f}; dome {} - keep waiting'.format(
                    sun_altitude, CONFIG['max_sun_altitude'], self.dome_is_open))
            else:
                if sun_altitude > CONFIG['max_sun_altitude']:
                    print('AutoFlat: Sun already above maximum altitude')
                    log.info(self.log_name, 'AutoFlat: Sun already above maximum altitude')
                    self.status = TelescopeActionStatus.Complete
                    return

                if sun_altitude > CONFIG['min_sun_altitude'] and self.dome_is_open:
                    break

                if not self.dome_is_open:
                    waiting_for.append('Dome')

                if sun_altitude < CONFIG['min_sun_altitude']:
                    waiting_for.append('Sun > {:.1f} deg'.format(CONFIG['min_sun_altitude']))

                print('AutoFlat: {:.1f} < {:.1f}; dome {} - keep waiting'.format(
                    sun_altitude, CONFIG['min_sun_altitude'], self.dome_is_open))

            self.set_task('Waiting for ' + ', '.join(waiting_for))
            with self._wait_condition:
                self._wait_condition.wait(CONFIG['sun_altitude_check_interval'])

        if self.aborted:
            self.status = TelescopeActionStatus.Complete
            return

        self.set_task('Slewing to antisolar point')

        # The anti-solar point is opposite the sun at 75 degrees
        sun_altaz = sun_position(location)
        print('AutoFlat: Sun position is', sun_altaz)

        if not tel_slew_altaz(self.log_name, 75, sun_altaz[1] + 180, False, SLEW_TIMEOUT):
            if not self.aborted:
                print('AutoFlat: Failed to slew telescope')
                log.error(self.log_name, 'AutoFlat: Failed to slew telescope')
                self.status = TelescopeActionStatus.Error
                return

        # Last chance to bail out before starting the main logic
        if self.aborted:
            self.status = TelescopeActionStatus.Complete
            return

        # Take an initial bias frame for calibration
        # This starts the autoflat logic, which is run
        # in the received_frame callbacks
        for camera in self._cameras.values():
            camera.start()

        # Wait until complete
        while True:
            with self._wait_condition:
                self._wait_condition.wait(5)

            codes = ''
            for camera in self._cameras.values():
                camera.check_timeout()
                codes += AutoFlatState.Codes[camera.state]

            self.set_task('Acquiring (' + ''.join(codes) + ')')
            if self.aborted:
                break

            if not self.dome_is_open:
                for camera in self._cameras.values():
                    camera.abort()

                print('AutoFlat: Dome has closed')
                log.error(self.log_name, 'AutoFlat: Dome has closed')
                break

            # We are done once all cameras are either complete or have errored
            if all([camera.state >= AutoFlatState.Complete for camera in self._cameras.values()]):
                break

        success = self.dome_is_open and all([camera.state == AutoFlatState.Complete
                                             for camera in self._cameras.values()])

        if self.aborted or success:
            self.status = TelescopeActionStatus.Complete
        else:
            self.status = TelescopeActionStatus.Error

    def abort(self):
        """Notification called when the telescope is stopped by the user"""
        super().abort()
        for camera in self._cameras.values():
            camera.abort()

        with self._wait_condition:
            self._wait_condition.notify_all()

    def dome_status_changed(self, dome_is_open):
        """Notification called when the dome is fully open or fully closed"""
        super().dome_status_changed(dome_is_open)

        with self._wait_condition:
            self._wait_condition.notify_all()

    def received_frame(self, headers):
        """Notification called when a frame has been processed by the data pipeline"""
        camera_id = headers.get('CAMID', '').lower()
        if camera_id in self._cameras:
            self._cameras[camera_id].received_frame(headers)
        else:
            print('AutoFlat: Ignoring unknown frame')

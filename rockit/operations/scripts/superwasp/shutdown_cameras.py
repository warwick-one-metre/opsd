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

"""Script to warm and power off cameras"""

import argparse
import sys
import time
from rockit.camera.qhy import CameraStatus, CommandStatus, CoolerMode
from rockit.common import daemons, TFmt
from rockit.operations.actions.superwasp.camera_helpers import cameras


def shutdown_cameras(prefix, args):
    """warm and power off cameras"""
    parser = argparse.ArgumentParser(prefix)
    parser.add_argument('--cameras', type=str, nargs='+', choices=cameras.keys(),
                        default=cameras.keys(), help='cameras to shut down')

    args = parser.parse_args(args)

    try:
        # Disable terminal cursor
        sys.stdout.write('\033[?25l')

        sys.stdout.write('Warming cameras...')
        sys.stdout.flush()

        try:
            failed = False
            warm = {camera_id: False for camera_id in args.cameras}
            for camera_id in args.cameras:
                with cameras[camera_id].connect() as cam:
                    status = cam.set_target_temperature(None)
                    if status not in [CommandStatus.Succeeded, CommandStatus.CameraNotInitialized]:
                        failed = True
                        warm[camera_id] = True

            while True:
                for camera_id in args.cameras:
                    if warm[camera_id]:
                        continue

                    with cameras[camera_id].connect() as camd:
                        status = camd.report_status() or {}

                        if 'state' not in status or 'cooler_mode' not in status:
                            failed = True
                            warm[camera_id] = True
                        else:
                            warm[camera_id] = status['state'] == CameraStatus.Disabled or \
                                              status['cooler_mode'] == CoolerMode.Warm

                if all(warm[k] for k in warm):
                    break

                time.sleep(5)
        except Exception:
            print(f'\r\033[KWarming cameras {TFmt.Bold}{TFmt.Red}FAILED{TFmt.Clear}')
            return

        if failed:
            print(f'\r\033[KWarming cameras {TFmt.Bold}{TFmt.Yellow}FAILED{TFmt.Clear}')
        else:
            print(f'\r\033[KWarming cameras {TFmt.Bold}{TFmt.Green}COMPLETE{TFmt.Clear}')

        sys.stdout.write('Shutting down cameras...')
        sys.stdout.flush()

        for camera_id in args.cameras:
            try:
                with cameras[camera_id].connect() as cam:
                    cam.shutdown()

                with daemons.superwasp_power.connect() as powerd:
                    p = powerd.last_measurement()
                    if camera_id in p and p[camera_id]:
                        powerd.switch(camera_id, False)
            except Exception:
                failed = True
                continue

        if failed:
            print(f'\r\033[KShutting down cameras {TFmt.Bold}{TFmt.Red}FAILED{TFmt.Clear}')
        else:
            print(f'\r\033[KShutting down cameras {TFmt.Bold}{TFmt.Green}COMPLETE{TFmt.Clear}')
    finally:
        # Restore cursor
        sys.stdout.write('\033[?25h')
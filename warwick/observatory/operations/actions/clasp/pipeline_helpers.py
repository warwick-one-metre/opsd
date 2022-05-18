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

"""Helper functions for actions to interact with the pipeline"""

import sys
import traceback
import Pyro4
from warwick.observatory.common import daemons, log
from warwick.observatory.pipeline import CommandStatus as PipelineCommandStatus

pipelines = {
    'cam1': daemons.clasp_pipeline_1,
    'cam2': daemons.clasp_pipeline_2,
}


def pipeline_enable_archiving(log_name, camera_id, enabled):
    """Toggle archiving on or off for a given arm name"""
    try:
        with pipelines[camera_id].connect() as pipeline:
            return pipeline.set_archive(camera_id, enabled) == PipelineCommandStatus.Succeeded
    except Pyro4.errors.CommunicationError:
        log.error(log_name, 'Failed to communicate with pipeline daemon')
        return False
    except Exception:
        log.error(log_name, 'Unknown error while configuring pipeline')
        traceback.print_exc(file=sys.stdout)
        return False


def configure_pipeline(log_name, config, quiet=False):
    """Update pipeline configuration"""
    try:
        success = True
        for daemon in pipelines.values():
            with daemon.connect() as pipeline:
                success = pipeline.configure(config, quiet=quiet) == PipelineCommandStatus.Succeeded and success
        return success
    except Pyro4.errors.CommunicationError:
        log.error(log_name, 'Failed to communicate with pipeline daemon')
        return False
    except Exception:
        log.error(log_name, 'Unknown error while configuring pipeline')
        traceback.print_exc(file=sys.stdout)
        return False

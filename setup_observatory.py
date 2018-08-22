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

from distutils.core import setup

setup(name='warwick.observatory.operations',
      version='0',
      packages = ['warwick.observatory.operations'],
      author='Paul Chote',
      description='Common code for the W1m and RASA operations daemons',
      license='GNU GPLv3',
      author_email='p.chote@warwick.ac.uk',
      url="https://github.com/warwick-one-metre/opsd",
)
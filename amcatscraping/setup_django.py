###########################################################################
# (C) Vrije Universiteit, Amsterdam (the Netherlands)                     #
#                                                                         #
# This file is part of AmCAT - The Amsterdam Content Analysis Toolkit     #
#                                                                         #
# AmCAT is free software: you can redistribute it and/or modify it under  #
# the terms of the GNU Lesser General Public License as published by the  #
# Free Software Foundation, either version 3 of the License, or (at your  #
# option) any later version.                                              #
#                                                                         #
# AmCAT is distributed in the hope that it will be useful, but WITHOUT    #
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or   #
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public     #
# License for more details.                                               #
#                                                                         #
# You should have received a copy of the GNU Lesser General Public        #
# License along with AmCAT.  If not, see <http://www.gnu.org/licenses/>.  #
###########################################################################
"""
This module is a big hack to get "from amcat.models import Article" working. It
would be nice if we can import settings from amcat at some point (of course, we
would like to prevent import database settings).
"""
import amcat
import django
import sys

from os.path import dirname, join, abspath, realpath

from django.conf import global_settings

# Figure out where amcat lives, import settings module
amcat_lib_dir = abspath(join(realpath(dirname(amcat.__file__)), ".."))
sys.path.insert(0, amcat_lib_dir)
import settings as amcat_settings
sys.path.pop(0)

# Copy relevant config
global_settings.ES_MAPPING = amcat_settings.ES_MAPPING
global_settings.ES_MAPPING_TYPES = amcat_settings.ES_MAPPING_TYPES
global_settings.ES_MAPPING_TYPE_PRIMITIVES = amcat_settings.ES_MAPPING_TYPE_PRIMITIVES
global_settings.INSTALLED_APPS += [
    "django.contrib.contenttypes",
    "django.contrib.auth"
]


# Fire up Django
django.conf.settings.configure()
django.setup()

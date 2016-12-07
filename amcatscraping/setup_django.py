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
import django
import datetime

from django.conf import global_settings

ES_MAPPING_TYPE_PRIMITIVES = {
    "int": int,
    "date": datetime.datetime,
    "num": float,
    "url": str,
    "id": str,
    "text": str,
    "default": str
}


ES_MAPPING_TYPES = {
    'int': {"type": "long"},
    'date': {"format": "dateOptionalTime", "type": "date"},
    'num': {"type": "double"},
    'url': {"index": "not_analyzed", "type": "string"},
    'id': {"index": "not_analyzed", "type": "string"},
    'text': {"type": "string"},
    'default': {"type": "string",
                 "fields": {"raw":   { "type": "string", "index": "not_analyzed", "ignore_above": 256}}}
    }

ES_MAPPING = {
    "properties": {
        # id / hash / project/set membership
        "id": ES_MAPPING_TYPES['int'],
        "sets": ES_MAPPING_TYPES['int'],
        "hash": ES_MAPPING_TYPES['id'],
        "parent_hash": ES_MAPPING_TYPES['id'],
        # article properties
        "date": ES_MAPPING_TYPES['date'],
        "title": ES_MAPPING_TYPES['default'],
        "url": ES_MAPPING_TYPES['url'],
        "text": ES_MAPPING_TYPES['text'],
    },
}

global_settings.ES_MAPPING = ES_MAPPING
global_settings.ES_MAPPING_TYPES = ES_MAPPING_TYPES
global_settings.ES_MAPPING_TYPE_PRIMITIVES = ES_MAPPING_TYPE_PRIMITIVES
global_settings.INSTALLED_APPS += [
    "django.contrib.contenttypes",
    "django.contrib.auth"
]

django.conf.settings.configure()
django.setup()
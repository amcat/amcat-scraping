###########################################################################
# (C) Vrije Universiteit, Amsterdam (the Netherlands)            #
# #
# This file is part of AmCAT - The Amsterdam Content Analysis Toolkit     #
# #
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
from collections import OrderedDict

import functools
import logging
import sys
import datetime

from html2text import HTML2Text
from lxml import html, etree

log = logging.getLogger(__name__)

### MISC ###
def unique(seq):
    seen = set()
    seen_add = seen.add
    return [x for x in seq if not (x in seen or seen_add(x))]

def listify(fn=None, wrapper=list):
    """
    A decorator which wraps a function's return value in ``list(...)``.

    Useful when an algorithm can be expressed more cleanly as a generator but
    the function should return an list.

    Example::

        >>> @listify
        ... def get_lengths(iterable):
        ...     for i in iterable:
        ...         yield len(i)
        >>> get_lengths(["spam", "eggs"])
        [4, 4]
        >>>
        >>> @listify(wrapper=tuple)
        ... def get_lengths_tuple(iterable):
        ...     for i in iterable:
        ...         yield len(i)
        >>> get_lengths_tuple(["foo", "bar"])
        (3, 3)
    """
    def listify_return(fn):
        @functools.wraps(fn)
        def listify_helper(*args, **kw):
            return wrapper(fn(*args, **kw))
        return listify_helper
    if fn is None:
        return listify_return
    return listify_return(fn)

_boolean_states = {
    '1': True, 'yes': True, 'true': True, 'on': True,
    '0': False, 'no': False, 'false': False, 'off': False
}


def get_boolean(v):
    """Convert string to boolean, based on rules of ConfigParser"""
    if v.lower() not in _boolean_states:
        raise ValueError('Not a boolean: %s' % v)
    return _boolean_states[v.lower()]


def _html2text(data, handler):
    if isinstance(data, bytes):
        raise ValueError("You supplied bytes. Please decode at borders of I/O!!")

    if isinstance(data, str):
        return handler.handle(data).strip()

    if isinstance(data, (html.HtmlElement, etree._Element)):
        return html2text(html.tostring(data, encoding="unicode"))

    # Assume iterable
    return "\n\n".join(html2text(bit) for bit in data)


def html2text(data, bodywidth=0, baseurl='', ignore_links=True, ignore_images=True):
    handler = HTML2Text(baseurl=baseurl, bodywidth=bodywidth)
    handler.ignore_links = ignore_links
    handler.ignore_images = ignore_images
    return _html2text(data, handler)


def parse_form(form):
    return {inp.get('name'): inp.get('value', '') for inp in form.cssselect('input')}


def setup_logging():
    loggers = [logging.getLogger("amcatscraping"), logging.getLogger("__main__")]
    handlers = [logging.StreamHandler(sys.stdout)]

    for handler in handlers:
        handler.setLevel(logging.INFO)

    for logger in loggers:
        logger.propagate = False
        logger.setLevel(logging.INFO)
        for handler in handlers:
            logger.addHandler(handler)


### DATES ###
def to_date(date_or_datetime):
    if isinstance(date_or_datetime, datetime.datetime):
        return date_or_datetime.date()
    return date_or_datetime

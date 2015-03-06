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

import logging
import sys
import re
import argparse
import datetime

from html2text import HTML2Text
from lxml import html, etree

log = logging.getLogger(__name__)

### MISC ###
_boolean_states = {
    '1': True, 'yes': True, 'true': True, 'on': True,
    '0': False, 'no': False, 'false': False, 'off': False
}


def get_boolean(v):
    """Convert string to boolean, based on rules of ConfigParser"""
    if v.lower() not in _boolean_states:
        raise ValueError, 'Not a boolean: %s' % v
    return _boolean_states[v.lower()]


def setup_django():
    import django

    try:
        django.setup()
    except django.core.exceptions.ImproperlyConfigured:
        django.conf.settings.configure()
        django.setup()


def _html2text(data, handler):
    if isinstance(data, basestring):
        return handler.handle(data).strip()

    if isinstance(data, (html.HtmlElement, etree._Element)):
        return html2text(html.tostring(data))

    # Assume iterable
    return "\n\n".join(html2text(bit) for bit in data)


def html2text(data, bodywidth=0, baseurl='', ignore_links=True, ignore_images=True):
    handler = HTML2Text(baseurl=baseurl, bodywidth=bodywidth)
    handler.ignore_links = ignore_links
    handler.ignore_images = ignore_images
    return _html2text(data, handler)


def parse_form(form):
    return {inp.get('name'): inp.get('value', '').encode('utf-8') for inp in
            form.cssselect('input')}


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


class _DateFormat(object):
    """Format definition for parsing dates"""

    def __init__(self, expr, yeargroup=3, monthgroup=2, daygroup=1,
                 monthisname=False, swapamerican=False):
        self.expr = re.compile(expr, re.UNICODE)
        self.yeargroup = yeargroup
        self.monthgroup = monthgroup
        self.daygroup = daygroup
        self.monthisname = monthisname
        self.swapamerican = swapamerican

    def readDate(self, date, american=False):
        """Read the given date, producing a y,m,d tuple"""
        match = re.search(self.expr, date)
        if not match: return
        y, m, d = [match.group(x)
                   for x in (self.yeargroup, self.monthgroup, self.daygroup)]
        if self.monthisname:
            m = _monthnr(m)
            if not m: return
        y, m, d = map(int, (y, m, d))
        # 2-digit year logic:
        if y < 40:
            y += 2000
        elif y < 100:
            y += 1900
        # dmy vs mdy
        if american and self.swapamerican:
            m, d = d, m
        return y, m, d


_DATEFORMATS = (
    _DateFormat("(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})", 1, 2, 3),
    _DateFormat("(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{4})", 3, 2, 1, swapamerican=True),
    _DateFormat("(\w+),?\s+(\d{1,2})\s*,?\s+(\d{4})", 3, 1, 2, True),
    _DateFormat("(\w+)\s+(\d{1,2})\s*,?\s+(\d{4})", 3, 1, 2, True),
    _DateFormat("(\d{1,2})(?:\w\w?|\.)?\s+(\w*)\s+(\d{4})", 3, 2, 1, True),
    _DateFormat("\w*?,?\s*(\d{1,2})\s+(\w+)\s+(\d{4})", 3, 2, 1, True),
    _DateFormat("(\d{1,2})\.?\s+(\w*)\s+(\d{4})", 3, 2, 1, True),
    _DateFormat("(\d{1,2})[- ](\w+)[- ](\d{2,4})", 3, 2, 1, True),
    _DateFormat("(\w+) (\d{1,2}), (\d{4})", 3, 1, 2, True),
    _DateFormat("(\d{1,2})[-/](\d{1,2})[-/](\d{2})", 3, 2, 1, swapamerican=True),
)

MONTHNAMES = (('jan', 'janv', 'ener', 'gennaio'),
              ('feb', 'fevr', 'feve', 'f\xe9vrier'),
              ('mar', 'mrt', 'maa', 'mar', 'm\xe4rz', 'maerz'),
              ('apr', 'avri', 'abri'),
              ('may', 'mai', 'mei', 'mayo', 'maggio', 'm\xe4rz'),
              ('jun', 'juin', 'giugno'),
              ('jul', 'juil', 'luglio'),
              ('aug', 'aout', 'agos', u'ao\xfbt'),
              ('sep', 'setem', 'settembre'),
              ('oct', 'okt', 'out', 'ottobre'),
              ('nov'),
              ('dec', 'dez', 'dici', 'dicembre', 'd\xe9cembre'))


def _monthnr(monthname):
    """Try to get a month number corresponding to the month
    name (prefix) in monthname"""
    for i, names in enumerate(MONTHNAMES):
        for name in names:
            if monthname.lower().startswith(name.lower()):
                return i + 1


def read_date(string, lax=False, rejectPre1970=False, american=False):
    """Try to read a date(time) string with unknown format

    Attempt a number of date formats to read str

    @param string: the date string to read
    @param lax: if True, return None if no match was found instead of
      raising an error
    @param rejectPre1970: if True, reject dates before 1970 (to catch
      problems with incorrect parses)
    @param american: prefer MDY over DMY
    @return: a \C{datetime.datetime} object
    """
    if string is None:
        return None

    try:
        datestr = string

        time = None
        if ':' in datestr:
            m = re.match(r"(.*?)(\d+:[\d:]+)(\s+PM\b)?(?= \+\d{4} (\d{4}))?", datestr)
            if m:
                datestr, timestr, pm, year = m.groups()
                if year:
                    # HACK: allow (twitter) to specify year AFTER the timezone indicator (???) 
                    datestr += year
                try:
                    time = tuple(map(int, timestr.split(":")))
                except ValueError:
                    time = []
                if len(time) == 3:
                    pass
                elif len(time) == 2:
                    time = time + (0,)
                elif lax:
                    time = None
                else:
                    raise ValueError("Could not parse time part "
                                     + "('%s') of datetime string '%s'"
                                     % (timestr, string))
                if pm and time[0] != 12: time = (time[0] + 12, ) + time[1:]
        for df in _DATEFORMATS:
            date = df.readDate(datestr, american=american)
            if date: break

        datestr = datestr.lower()
        if not date:
            # For 'October 20, 2010'
            for i, prefixes in enumerate(MONTHNAMES):
                if datestr.startswith(prefixes):
                    month_plus_day, year = datestr.split(',')
                    day = month_plus_day.split(' ')[1]
                    date = int(year), i + 1, int(day)

        if not date:
            # For '22 November 2006 Wednesday 10:23 AM (Central European Time)'
            s = datestr.split(' ')
            if len(s) > 2:
                for i, prefixes in enumerate(MONTHNAMES):
                    if s[1].startswith(prefixes):
                        try:
                            date = int(s[2]), i + 1, int(s[0])
                        except:
                            pass
                        finally:
                            break

        if not date:
            if lax: return
            raise ValueError("Could not parse datetime string '%s'" % (string))

        if date[0] < 1970 and rejectPre1970:
            if lax: return None
            raise ValueError("Rejecting datetime string %s -> %s"
                             % (string, date))

        if not time:
            time = (0, 0, 0)
        return datetime.datetime(*(date + time))
    except Exception:
        import traceback

        # trace = traceback.format_exc()
        # warn("Exception on reading datetime %s:\n%s\n%s" % (string, e, trace))

        if lax:
            return None
        else:
            raise


### CACHING ###
def memoize(f):
    cache = LimitedSizeDict(size_limit=200)

    def wrapper(*args):
        if args in cache:
            return cache[args]
        cache[args] = f(*args)
        return cache[args]

    return wrapper


class LimitedSizeDict(OrderedDict):
    def __init__(self, *args, **kwds):
        self.size_limit = kwds.pop("size_limit", None)
        OrderedDict.__init__(self, *args, **kwds)
        self._check_size_limit()

    def __setitem__(self, key, value, **kwargs):
        OrderedDict.__setitem__(self, key, value, **kwargs)
        self._check_size_limit()

    def _check_size_limit(self):
        if self.size_limit is not None:
            while len(self) > self.size_limit:
                self.popitem(last=False)

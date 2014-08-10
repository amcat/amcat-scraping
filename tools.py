from html2text import html2text as html_to_text
from lxml import html, etree
from urlparse import urljoin
import logging, sys, re
from datetime import datetime, date
import time
import argparse
import logging; log = logging.getLogger(__name__)

### MISC ###

def html2text(data):
    if type(data) == list:
        return "".join([html2text(bit) for bit in data])
    elif type(data) in (str, unicode):
        return html_to_text(data)
    elif type(data) in (html.HtmlElement, etree._Element):
        return html_to_text(html.tostring(data)).strip()

def parse_form(form):
    return {inp.get('name') : inp.get('value', '').encode('utf-8') for inp in form.cssselect('input')}

def setup_logging():
    loggers = [logging.getLogger("amcatscraping"),logging.getLogger("__main__")]
    handlers = [logging.StreamHandler(sys.stdout)]
    
    for handler in handlers:
        handler.setLevel(logging.INFO)

    for logger in loggers:
        logger.propagate = False
        logger.setLevel(logging.INFO)
        for handler in handlers:
            logger.addHandler(handler)

def get_arguments(__first__=None, **variations):
    """wrapper for argparse module
    provide either one dict or different named dicts for different subparsers
    sample usage:
    get_arguments({
        'integers' : {
            'metavar' : 'N',
            'type' : int,
            'nargs' : '+',
            'help' : 'an integer for the accumulator'},
        '--sum' : {
            'dest' : 'accumulate',
            'action' : 'store_const',
            'const' : sum,
            'default' : max,
            'help' : 'sum the integers (default: find the max)'}
    })
    """
    assert bool(__first__) ^ bool(variations)

    def addarguments(parser,_dict):
        for args, options in _dict.items():
            if not hasattr(args,'__iter__'):
                args = (args,)
            for arg in args:
                parser.add_argument(arg, **options)

    parser = argparse.ArgumentParser()
    if __first__:
        addarguments(parser, __first__)
    elif variations:
        subparsers = parser.add_subparsers(dest='__command__')
        for cmd, args in variations.items():
            parser_cmd = subparsers.add_parser(cmd)
            addarguments(parser_cmd, args)
    return vars(parser.parse_args())


from importlib import import_module
def run_scraper_and_log(classpath, arguments, db):
    """
    Shortcut to getting a scraper class, running it, and 
    logging the results to the db
    """
    # Get the scraper class
    modulename, classname = classpath.rsplit(".",1)
    module = import_module(modulename)
    scraper = getattr(module,classname)
    # Run the scraper
    log.info("Running {}".format(classpath))
    tstart = datetime.now()
    try:
        articles = scraper(**arguments).run()
    except Exception as e:
        articles = []
        log.exception("running scraper failed")
    else: e = None
    tfinish = datetime.now()

    # Log the details to the db
    details = {
        'time_started' : tstart,
        'time_finished' : tfinish,
        'arguments' : arguments,
        'n_articles' : len(articles),
        'exception' : e}
    runs = db[classpath]['runs']
    runs.append(details)
    db.update(classpath, runs = runs)

### DATES ###

def todate(d):
    return date.fromordinal(d.toordinal())
def todatetime(d):
    return datetime.fromtimestamp(time.mktime(d.timetuple()))

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
        if y < 40: y = 2000 + y
        elif y < 100: y = 1900 + y
        # dmy vs mdy
        if american and self.swapamerican:
            m, d = d, m
        return y, m, d

_DATEFORMATS = (
    _DateFormat("(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})", 1,2,3),
    _DateFormat("(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{4})", 3,2,1,swapamerican=True),
    _DateFormat("(\w+),?\s+(\d{1,2})\s*,?\s+(\d{4})",3,1,2,True),
    _DateFormat("(\w+)\s+(\d{1,2})\s*,?\s+(\d{4})",  3,1,2,True),
    _DateFormat("(\d{1,2})(?:\w\w?|\.)?\s+(\w*)\s+(\d{4})",3,2,1,True),
    _DateFormat("\w*?,?\s*(\d{1,2})\s+(\w+)\s+(\d{4})",3,2,1,True),
    _DateFormat("(\d{1,2})\.?\s+(\w*)\s+(\d{4})",    3,2,1,True),
    _DateFormat("(\d{1,2})[- ](\w+)[- ](\d{2,4})",   3,2,1,True),
    _DateFormat("(\w+) (\d{1,2}), (\d{4})",          3,1,2,True),
    _DateFormat("(\d{1,2})[-/](\d{1,2})[-/](\d{2})", 3,2,1,swapamerican=True),
)

MONTHNAMES = (('jan', 'janv', 'ener', 'gennaio'),
              ('feb', 'fevr', 'feve', 'f\xe9vrier'),
              ('mar', 'mrt', 'maa', 'mar', 'm\xe4rz', 'maerz'),
              ('apr', 'avri', 'abri'),
              ('may', 'mai', 'mei', 'mayo', 'maggio', 'm\xe4rz'),
              ('jun', 'juin','giugno'),
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
                return i+1


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
    if string == None: return None
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
                try: time = tuple(map(int, timestr.split(":")))
                except ValueError: time = []
                if len(time) == 3: pass
                elif len(time) == 2: time = time + (0,)
                elif lax: time = None
                else: raise ValueError("Could not parse time part "
                                       +"('%s') of datetime string '%s'"
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
                    date = int(year), i+1, int(day)

        if not date:
            # For '22 November 2006 Wednesday 10:23 AM (Central European Time)'
            s = datestr.split(' ')
            if len(s)>2:
                for i, prefixes in enumerate(MONTHNAMES):
                    if s[1].startswith(prefixes):
                        try:
                            date = int(s[2]), i+1, int(s[0])
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

        if not time: time = (0, 0, 0)
        return datetime(*(date + time))
    except Exception,e:
        import traceback
        trace = traceback.format_exc()
        #warn("Exception on reading datetime %s:\n%s\n%s" % (string, e, trace))
        if lax: return None
        else: raise



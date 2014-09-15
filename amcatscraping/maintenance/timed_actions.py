import logging; log = logging.getLogger(__name__)
from datetime import datetime, timedelta
from collections import OrderedDict
from importlib import import_module
from croniter import croniter

from amcatscraping.tools import (todatetime, get_arguments,
                                 setup_logging, read_date, 
                                 run_scraper_and_log)
from amcatscraping.maintenance.db import DB

class TimedActions(object):
    """
    Run this script every minute
    It runs scrapers when they are specified to run
    """
    db = DB()
    def __init__(self):
        self.options = get_arguments(OrderedDict([
            ('api_host',{}),
            ('api_user',{}),
            ('api_password',{}),
            ('--print_errors',{'action':'store_const', 'const':True}),
            ("--time",{"type":read_date})
        ]))
        self.api_info = {key : self.options[key] for key in ('api_host','api_user','api_password')}
        self.datetime = self.options["time"] or datetime.now().replace(second=0,microsecond=0)

    def run(self):
        now = datetime.now()
        log.info("{d.year}-{d.month}-{d.day}T{d.hour}:{d.minute}".format(d=now))
        yesterday = self.datetime - timedelta(days = 1)
        for classpath, info in self.db.items():
            # if scraper is periodic and it's cron entry matches the time
            if info['timetype'] == 'periodic' and self._cron_match(info['cron']):
                run = True
                arguments =  dict(info['arguments'].items() + self.api_info.items())

            # if scraper is daterange and it is 2 AM
            elif info['timetype'] == 'daterange' and (self.datetime.hour, self.datetime.minute) == (2,0):
                run = True
                arguments = dict(info['arguments'].items() + self.api_info.items()
                                 + [('min_datetime', yesterday.replace(hour = 0, minute = 0, second = 0)),
                                    ('max_datetime', yesterday.replace(hour = 23, minute = 59))])
            # if neither, don't run
            else: run = False
            if run:
                arguments['print_errors'] = self.options.get('print_errors')
                run_scraper_and_log(classpath, arguments, self.db)

    def _cron_match(self, cron_str):
        parser = croniter(cron_str, self.datetime)
        parser.get_next()
        if parser.get_prev(datetime) == self.datetime:
            return True


if __name__ == "__main__":
    setup_logging()
    TimedActions().run()

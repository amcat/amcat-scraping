import logging; log = logging.getLogger(__name__)
from datetime import datetime, timedelta
from collections import OrderedDict
from importlib import import_module
from croniter import croniter

from amcatscraping.tools import todatetime, get_arguments, setup_logging
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
            ('--print_errors',{'action':'store_const', 'const':True})
        ]))
        self.api_info = {key : self.options[key] for key in ('api_host','api_user','api_password')}
        self.datetime = datetime.now().replace(second=0,microsecond=0)

    def run(self):
        yesterday = todatetime(datetime.today() - timedelta(days = 1))
        for classpath, info in self.db.items():
            # if scraper is periodic and it's cron entry matches the time
            if info['timetype'] == 'periodic' and self._cron_match(info['cron']):
                run = True
                arguments =  dict(info['arguments'].items() + self.api_info.items())

            # if scraper is daterange and it is 2 AM
            elif info['timetype'] == 'daterange' and (self.datetime.hour, self.datetime.minute) == (2,0):
                run = True
                arguments = dict(info['arguments'].items() + self.api_info.items()
                                 + [('min_datetime', yesterday),
                                    ('max_datetime', yesterday.replace(hour = 23, minute = 59))])
            # if neither, don't run
            else: run = False
            if run:
                arguments['print_errors'] = self.options.get('print_errors')
                articles, exception, tstart, tfinish = self._run_scraper(classpath, arguments)
                self._log_run(classpath, time_started = tstart, time_finished = tfinish,
                              arguments = arguments, n_articles = len(articles), exception = exception)

    def _cron_match(self, cron_str):
        parser = croniter(cron_str, self.datetime)
        parser.get_next()
        if parser.get_prev(datetime) == self.datetime:
            return True

    def _run_scraper(self, classpath, arguments):
        scraper = self._get_class(classpath)(**arguments)
        log.info("Running {}".format(classpath))
        tstart = datetime.now()
        try:
            articles = scraper.run()
        except Exception as e:
            articles = []
            log.exception("running scraper failed")
        else: e = None
        tfinish = datetime.now()
        return articles, e, tstart, tfinish

    def _get_class(self, path):
        modulename, classname = path.rsplit(".",1)
        log.debug("module: " + modulename + ", class: " + classname)
        module = import_module(modulename)
        return getattr(module,classname)

    def _log_run(self, classpath, **details):
        runs = self.db[classpath]['runs']
        runs.append(details)
        self.db.update(classpath, runs = runs)

if __name__ == "__main__":
    setup_logging()
    TimedActions().run()

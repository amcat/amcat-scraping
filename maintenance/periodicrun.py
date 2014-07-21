"""Running scrapers daily"""
import logging; log = logging.getLogger(__name__)
from importlib import import_module
from datetime import date, datetime

from amcatscraping.maintenance.db import DB
from amcatscraping.tools import setup_logging, get_arguments


mkdate = 

class PeriodicRun(object):
    db = DB()
    def __init__(self):
        self.options = get_arguments({
            'period' : {
                'choices' : ['hourly','daily','weekly']},
            'date' : {
                'type' : lambda x: date(*map(int,x.split("-")))},
            ('api_host', 'api_user', 'api_password') : {
            }})

    def run(self):
        result = {}
        api_info = [(key,self.options[key]) for key in ['api_host','api_user','api_password']]
        misc_options = [('first_date',self.options['date']),('last_date',self.options['date'])]
        for classpath, info in self.db.items():
            if info['period'] != self.options['period']:
                continue
            arguments = dict(info['arguments'].items() + api_info + misc_options)
            articles, exception, tstart, tfinish = self._run_scraper(classpath, arguments)
            self._log_run(classpath, time_started = tstart, time_finished = tfinish,
                          arguments = arguments, n_articles = len(articles), exception = exception)

            result[classpath] = articles
        self._evaluate(result)

    def _get_class(self, path):
        modulename, classname = path.rsplit(".",1)
        log.debug("module: " + modulename + ", class: " + classname)
        module = import_module(modulename)
        return getattr(module,classname)

    def _run_scraper(self, classpath, arguments):
        scraper = self._get_class(classpath)(**arguments)
        log.info("Running {}".format(classpath))
        tstart = datetime.now()
        try: 
            articles = scraper.run()
        except Exception as e:
            log.exception("running scraper failed")
            articles = []
        else: e = None
        tfinish = datetime.now()
        return articles, e, tstart, tfinish

    def _log_run(self, classpath, **details):
        runs = self.db[classpath]['runs']
        runs.append(
            {key : value for key, value in details.items()}
        )
        self.db.update(classpath,runs = runs)

    def _evaluate(self, result):
        """Did the scrapers run as expected?"""
        #TBA

if __name__ == "__main__":
    setup_logging()
    PeriodicRun().run()

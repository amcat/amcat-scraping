"""Running scrapers daily"""
import logging; log = logging.getLogger(__name__)
from importlib import import_module
import argparse
from datetime import date, datetime

from amcatscraping.maintenance.db import DB

mkdate = lambda x: date(*map(int,x.split("-")))

class Daily(object):
    db = DB()
    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("date",type=mkdate)
        parser.add_argument("api_host")
        parser.add_argument("api_user")
        parser.add_argument("api_password")
        self.options = vars(parser.parse_args())

    def run(self):
        result = {}
        api_info = [(key,self.options[key]) for key in ['api_host','api_user','api_password']]
        misc_options = [('first_date',self.options['date']),('last_date',self.options['date'])]
        for classpath, info in self.db.items():
            log.info("Running {}".format(classpath))
            arguments = dict(info['arguments'].items() + api_info + misc_options)
            scraper = self._get_class(classpath)(**arguments)
            try: articles = scraper.run()
            except Exception as e:
                log.exception("running scraper failed")
                articles = []
            else: e = None

            runs = self.db[classpath]['runs']
            runs.append(
                {'time_ran':datetime.now(),
                 'arguments':arguments,
                 'n_articles':len(articles),
                 'exception':e and e.message})
            self.db.update(classpath,runs = runs)
            result[scraper] = articles
        self._evaluate(result)

    def _get_class(self, path):
        modulename, classname = path.rsplit(".",1)
        log.debug("module: " + modulename + ", class: " + classname)
        module = import_module(modulename)
        return getattr(module,classname)

    def _evaluate(self, result):
        """Did the scrapers run as expected?"""
        #TBA

if __name__ == "__main__":
    from amcatscraping.scraping.tools import setup_logging
    setup_logging()
    Daily().run()

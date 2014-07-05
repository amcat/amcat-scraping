from datetime import datetime, timedelta, date
import logging; log = logging.getLogger(__name__)
import warnings
import argparse

from amcatscraping.celery.tasks import run_scraper
from amcatscraping.scraping.httpsession import Session
from amcatclient.amcatclient import AmcatAPI

def mkdate(datestring):
    return datetime.strptime(datestring, '%Y-%m-%d').date()

class Scraper(object):
    def __init__(self, **kwargs):
        if kwargs: #not invoked from CLI
            self.options = kwargs
        else:
            arguments = self._make_parser().parse_args()
            self.options = vars(arguments)
        self.session = Session() #http session

    def _make_parser(self):
        """Build a parser to interpret the arguments given"""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest='command')
        parser_run = subparsers.add_parser('run')
        parser_test = subparsers.add_parser('test')

        for p in [parser_run,parser_test]:
            p.add_argument("project",type=int)
            p.add_argument('--username')
            p.add_argument('--password')
            p.add_argument('--first_date',type=mkdate)
            p.add_argument('--last_date',type=mkdate)

        parser_run.add_argument("articleset",type=int)
        parser_run.add_argument("api_host")
        parser_run.add_argument("api_user")
        parser_run.add_argument("api_password")

        return parser

    def run(self, input = None):
        log.info("\tgetting articles...")
        articles = list(self._scrape())
        log.info("\t...found {} articles. postprocessing...".format(len(articles)))
        articles = self._postprocess(articles)
        if 'command' in self.options and self.options['command'] == 'test':
            n = len(articles)
            log.info("\tscraper returned {n} articles".format(**locals()))
        else:
            log.info("\t...saving.")
            self._save(
                articles, 
                self.options['api_host'],
                self.options['api_user'],
                self.options['api_password'])
        return articles

    def run_async(self):
        """Run the scraper in an independent process"""
        run_scraper.delay(self)

    def _scrape(self):
        """Scrape the target resource and return a sequence of article dicts"""
        raise NotImplementedError()

    def _postprocess(self, articles):
        """Space to do something with the unsaved articles that the scraper provided"""
        out = []
        for a in articles:
            if a:
                a['insertscript'] = type(self).__name__
                out.append(a)
        return out

    def _save(self, articles, *auth):
        articles = self.__stringify_dates(articles)
        api = AmcatAPI(*auth)
        api.create_articles(
            self.options['project'],
            self.options['articleset'],
            json_data = articles)

    def __stringify_dates(self, articles):
        for article in articles:
            for key, value in article.items():
                if type(value) in (date, datetime):
                    value = str(value)
                    article[key] = value
                if type(key) in (date, datetime):
                    article[str(key)] = value
                    del article[key]
        return articles


class UnitScraper(Scraper):
    """
    Scrapes the resource on a per-unit basis
    children classes should overrride _get_units and _scrape_unit
    """
    def _scrape(self):
        for unit in self._get_units():
            try:
                yield self._scrape_unit(unit)
            except Exception:
                log.exception("\t_scrape_unit failed")
                continue


class DateRangeScraper(Scraper):
    """
    Omits any articles that haven't been published in a given period.
    Provides a first_date and last_date option which children classes can use
    to select data from their resource.
    """
    def __init__(self, *args, **kwargs):
        super(DateRangeScraper, self).__init__(*args, **kwargs)
        assert self.options['first_date'] and self.options['last_date']
        n_days = (self.options['last_date'] - self.options['first_date']).days
        self.dates = [self.options['first_date'] + timedelta(days = x) for x in range(n_days + 1)]

    def _postprocess(self, articles):
        articles = super(DateRangeScraper, self)._postprocess(articles)
        for a in articles:
            if not self.options['first_date'] <= a['date'] <= self.options['last_date']:
                warnings.warn("Not saving '{a}': it is of an incorrect date ({a[date]}).".format(**locals()))
                articles.remove(a)
        return articles

class LoginError(Exception):
    """Exception for login failure"""
    pass

class LoginMixin(object):
    """Logs in to the resource before scraping"""

    def __init__(self,*args,**kwargs):
        super(LoginMixin,self).__init__(*args,**kwargs)
        assert self.options['username'] and self.options['password']

    def _scrape(self, *args, **kwargs):
        username = self.options['username']
        password = self.options['password']
        # Please ensure _login returns True on success
        assert self._login(username, password) 
        return super(LoginMixin, self)._scrape(*args, **kwargs)

    def _login(self, username, password):
        raise NotImplementedError()

class PropertyCheckMixin(object):
    """
    Before saving, this mixin has the scraper check whether all given article props are present
    and fill in the blanks with default values
    When mixing this in, make sure the scraper contains a '_props' member with the following structure:
    {
        'defaults' : {
            '<property1>' : '<value>',
            '<property2>' : '<value>',
            ...
            '<propertyN>' : '<value>'
            },
        'required' : ['<property1>', '<property2>', ..., '<propertyN>'],
        'expected' : ['<property1>', '<property2>', ..., '<propertyN>']
        }
    'required' means all articles should have this property
    'expected' means at least one article should have this property
    """
    
    def _postprocess(self, articles):
        articles = super(PropertyCheckMixin, self)._postprocess(articles)
        articles = self._add_defaults(articles)
        self._check_properties(articles)
        return articles
        
    def _add_defaults(self, articles):
        log.info("\tFilling in defaults...")
        self._props['defaults']['project'] = self.options['project']
        self._props['defaults']['insertscript'] = type(self).__name__
        for prop, default in self._props['defaults'].items():
            for article in articles:
                if not article.get(prop):
                    article[prop] = default
        return articles

    def _check_properties(self, articles):
        log.info("\tChecking properties...")
        for prop in self._props['required']:
            if not all([article.get(prop) or article['metastring'].get(prop) for article in articles]):
                raise ValueError("{prop} missing in at least one article".format(**locals()))
        if articles:
            for prop in self._props['expected']:
                if not any([article.get(prop) or article['metastring'].get(prop) for article in articles]):
                    raise ValueError("{prop} missing in all articles".format(**locals()))


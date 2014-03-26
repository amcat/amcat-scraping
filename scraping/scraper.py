from datetime import datetime, timedelta
import logging; log = logging.getLogger(__name__)
import warnings
import argparse

from amcatscraping.celery.tasks import run_scraper
from amcatscraping.scraping.opener import Opener
from amcatclient.api import AmcatAPI

class Scraper(object):
    def __init__(self, *args,**kwargs):
        parser = self._make_parser()
        if args or kwargs: #not invoked from CLI
            to_parse = [str(a) for a in args]
            for key, value in kwargs.items():
                to_parse.append("--" + key)
                if not type(value) == bool:
                    to_parse.append(value)
            arguments = parser.parse_args(to_parse)
        else:
            arguments = parser.parse_args()
        self.options = vars(arguments)

    def _make_parser(self):
        """Build a parser to interpret the arguments given"""
        parser = argparse.ArgumentParser()
        parser.add_argument("project",type=int)
        parser.add_argument("articleset",type=int)
        parser.add_argument("api_host")
        parser.add_argument("api_user")
        parser.add_argument("api_password")
        return parser

    def run(self, input = None):
        log.info("getting articles...")
        articles = list(self._scrape())
        log.info("...postprocessing...")
        articles = self._postprocess(articles)
        log.info("...saving...")
        self._save(articles, 
                   self.options['api_host'],
                   self.options['api_user'],
                   self.options['api_password'])
        log.info("...done.")
        return articles


    def run_async(self):
        """Run the scraper in an independent process"""
        run_scraper.delay(self)

    def _scrape(self):
        """Scrape the target resource and return a sequence of article dicts"""
        raise NotImplementedError()

    def _postprocess(self, articles):
        """Space to do something with the unsaved articles that the scraper provided"""
        articles = [a for a in articles if a]
        return articles

    def _save(self, articles, *auth):
        api = AmcatAPI(*auth)
        api.create_articles(
            self.options['project'],
            self.options['articleset'],
            json_data = articles)


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
                log.exception("_scrape_unit failed")
                continue


class DateRangeScraper(Scraper):
    """
    Omits any articles that haven't been published in a given period.
    Provides a first_date and last_date option which children classes can use
    to select data from their resource.
    """
    def __init__(self, *args, **kwargs):
        super(DateRangeScraper, self).__init__(*args, **kwargs)
        n_days = (self.options['last_date'] - self.options['first_date']).days
        self.dates = [self.options['first_date'] + timedelta(days = x) for x in range(n_days + 1)]

    def _make_parser(self):
        parser = super(DateRangeScraper, self)._make_parser()
        def mkdate(datestring):
            return datetime.strptime(datestring, '%Y-%m-%d').date()
        parser.add_argument('first_date',type=mkdate)
        parser.add_argument('last_date',type=mkdate)
        return parser

    def _postprocess(self, articles):
        articles = super(DateRangeScraper, self)._postprocess(articles)
        for a in articles:
            if not self.options['first_date'] <= a['date'] <= self.options['last_date']:
                warnings.warn("Not saving '{a}': it is of an incorrect date ({a[date]})".format(**locals()))
                articles.remove(a)
        return articles

class LoginError(Exception):
    """Exception for login failure"""
    pass

class LoginMixin(object):
    """Logs in to the resource before scraping"""

    def _make_parser(self):
        parser = super(LoginMixin, self)._make_parser()
        parser.add_argument('username')
        parser.add_argument('password')
        return parser

    def _scrape(self, *args, **kwargs):
        username = self.options['username']
        password = self.options['password']
        try:
            assert self._login(username, password)
        except LoginError:
            log.exception("login failed")
            raise
        return super(LoginMixin, self)._scrape(*args, **kwargs)

    def _login(self, username, password):
        # Should return True if successful, otherwise raise an error
        raise NotImplementedError()


class OpenerMixin(object):
    """
    Provides a HTTP opener and some convenience functions
    """
    def __init__(self, *args, **kwargs):
        self.opener = Opener()
        super(OpenerMixin, self).__init__(*args, **kwargs)

    def open(self, *args, **kwargs):
        return self.opener.open(*args, **kwargs)

    def open_html(self, *args, **kwargs):
        return self.opener.open_html(*args, **kwargs)

    def navigate_html(self, *args, **kwargs):
        return self.opener.navigate_html(*args, **kwargs)


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
        log.info("Filling in defaults...")
        self._props['defaults']['project'] = self.options['project']
        for prop, default in self._props['defaults'].items():
            for article in articles:
                if not article.get(prop):
                    article[prop] = default
        return articles

    def _check_properties(self, articles):
        log.info("Checking properties...")
        for prop in self._props['required']:
            assert all([article.get(prop) for article in articles])
        for prop in self._props['expected']:
            assert any([article.get(prop) for article in articles])

if __name__ == "__main__":
    s = Scraper()

from datetime import timedelta, date, datetime
import logging; log = logging.getLogger(__name__)
from collections import OrderedDict


from amcatscraping.celery.tasks import run_scraper
from amcatscraping.scraping.httpsession import Session
from amcatscraping.tools import todatetime, todate, get_arguments, read_date

from amcatclient.amcatclient import AmcatAPI

import __main__, os, sys
def getpath(cls):
    """Get class path even if it's __main__"""
    if cls.__module__ == "__main__":
        pythonpath = os.environ.get('PYTHONPATH','')
        filepath = sys.path[0].split(pythonpath,1)[1].strip("/")
        modulepath = ".".join(filepath.split("/"))
        filename = os.path.splitext(os.path.basename(__main__.__file__))[0]
        return modulepath + "." + filename
    else:
        return cls.__module__

class Scraper(object):
    def __init__(self, **kwargs):
        self.options = kwargs or self._get_arguments()
        self.session = Session() #http session

    def _get_arguments(self):
        arglist = self._get_arg_list()
        return get_arguments(OrderedDict(arglist))

    def _get_arg_list(self):
        args = [
            ('project',{'type' : int}),
            ('articleset',{'type' : int}),
            (('api_host','api_user','api_password'), {}),
            ('--print_errors',{'action' : 'store_const', 'const' : True})
        ]
        return args

    def run(self, input = None):
        log.info("\tScraping articles...")
        articles = []
        sys.stdout.write('\t')
        for a in self._scrape():
            articles.append(a)
            sys.stdout.write('.')
            sys.stdout.flush()
        print

        log.info("\tFound {} articles. postprocessing...".format(len(articles)))
        articles = self._postprocess(articles)
        if 'command' in self.options and self.options['command'] == 'test':
            n = len(articles)
            log.info("\tscraper returned {n} articles".format(**locals()))
        else:
            log.info("\tSaving.")
            saved = self._save(
                articles, 
                self.options['api_host'],
                self.options['api_user'],
                self.options['api_password'])
        return saved

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
                a['insertscript'] = getpath(self.__class__) + "." + self.__class__.__name__
                out.append(a)
        return out

    def _save(self, articles, *auth):
        api = AmcatAPI(*auth)
        response = api.create_articles(
            self.options['project'],
            self.options['articleset'],
            json_data = articles)
        ids = [article['id'] for article in response]
        if not any(ids) and ids:
            raise RuntimeError("None of the articles were saved.")
        if not all(ids):
            log.warning("\tWarning: Only {}/{} articles were saved.".format(
                len(filter(None,ids)),
                len(ids)))
        return filter(lambda ar: ar['id'], response)


class UnitScraper(Scraper):
    """
    Scrapes the resource on a per-unit basis
    children classes should overrride _get_units and _scrape_unit
    """
    def _scrape(self):
        for unit in self._get_units():
            try:
                yield self._scrape_unit(unit)
            except Exception as e:
                if self.options['print_errors']:
                    log.exception(e)
                else:
                    sys.stdout.write('x')
                    sys.stdout.flush()
                continue


class DateRangeScraper(Scraper):
    """
    Omits any articles that haven't been published in a given period.
    Provides a first_date and last_date option which children classes can use
    to select data from their resource.
    """
    def _get_arg_list(self):
        args = super(DateRangeScraper, self)._get_arg_list()
        args.append((('min_datetime','max_datetime'),
                     {'type' : lambda x: todatetime(read_date(x))}))
        return args

    def __init__(self, *args, **kwargs):
        super(DateRangeScraper, self).__init__(*args, **kwargs)
        n_days = (self.options['max_datetime'] - self.options['min_datetime']).days
        self.dates = map(todate,
                         [self.options['min_datetime'] + timedelta(days = x) for x in range(n_days + 1)])
        self.mindatetime = self.options['min_datetime']
        self.maxdatetime = self.options['max_datetime']

    def _postprocess(self, articles):
        articles = super(DateRangeScraper, self)._postprocess(articles)
        for a in articles:
            _date = todatetime(a['date'])
            assert self.mindatetime <= _date <= self.maxdatetime
        return articles


class LoginError(Exception):
    """Exception for login failure"""
    pass


class LoginMixin(object):
    """Logs in to the resource before scraping"""

    def _get_arg_list(self):
        args = super(LoginMixin, self)._get_arg_list()
        args.append((('username','password'), {}))
        return args

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
        log.info("\t\tFilling in defaults...")
        self._props['defaults']['project'] = self.options['project']
        self._props['defaults']['metastring'] = {}
        for prop, default in self._props['defaults'].items():
            for article in articles:
                if not article.get(prop):
                    article[prop] = default
        return articles

    def _check_properties(self, articles):
        log.info("\t\tChecking properties...")
        for prop in self._props['required']:
            if not all([article.get(prop) or article['metastring'].get(prop) for article in articles]):
                raise ValueError("{prop} missing in at least one article".format(**locals()))
        if articles:
            for prop in self._props['expected']:
                if not any([article.get(prop) or article['metastring'].get(prop) for article in articles]):
                    raise ValueError("{prop} missing in all articles".format(**locals()))

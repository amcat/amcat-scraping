from django import forms
import logging; log = logging.getLogger(__name__)
import warnings

from amcatscraping.opener import Opener
from amcat.scripts.script import Script
from amcat.models.articleset import ArticleSet
from amcat.models.medium import Medium
from amcatclient.api import AmcatAPI


class ScraperForm(forms.Form):
    articleset = forms.ModelChoiceField(ArticleSet.objects.all())
    api_host = forms.CharField()
    api_user = forms.CharField()
    api_password = forms.CharField()

class Scraper(Script):
    options_form = ScraperForm

    def run(self, input = None):
        articles = list(self._scrape())
        articles = self._postprocess(articles)
        self._save(articles, 
                   self.options['api_host'],
                   self.options['api_user'],
                   self.options['api_password'])

    def _scrape(self):
        """Scrape the target resource and return a sequence of article dicts"""
        raise NotImplementedError()

    def _postprocess(self, articles):
        """Space to do something with the unsaved articles that the scraper provided"""
        return articles

    def _save(self, articles, *auth):
        api = AmcatAPI(*auth)
        api.create_articles(
            self.options['articleset'].project.id,
            self.options['articleset'].id,
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


class DateRangeForm(ScraperForm):
    first_date = forms.DateField()
    last_date = forms.DateField()

class DateRangeScraper(Scraper):
    """
    Omits any articles that haven't been published in a given period.
    Provides a first_date and last_date option which children classes can use
    to select data from their resource.
    """
    options_form = DateRangeForm
    def _postprocess(self, articles):
        articles = super(DateRangeScraper, self)._postprocess(articles)
        for a in articles:
            if not self.options['first_date'] <= a['date'].date() <= self.options['last_date']:
                warnings.warn("Not saving '{a}': it is of an incorrect date ({a[date]})".format(**locals()))
                articles.remove(a)
        return articles


class LoginForm(ScraperForm):
    username = forms.CharField()
    password = forms.CharField()

class LoginDateRangeForm(DateRangeForm, LoginForm):
    """Use this form if you're using both the LoginMixin and the DateRangeScraper"""

class LoginMixin(object):
    """Logs in to the resource before scraping"""
    options_form = LoginForm

    def _scrape(self, *args, **kwargs):
        username = self.options['username']
        password = self.options['password']
        if not self._login(username, password):
            raise Exception("Login failed")
        return super(LoginMixin, self)._scrape(*args, **kwargs)

    def _login(self, username, password):
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
    """
    
    def _postprocess(self, articles):
        articles = super(PropertyCheckMixin, self)._postprocess(articles)
        articles = self._add_defaults(articles)
        self._check_properties(articles)
        return articles
        
    def _add_defaults(self, articles):
        log.info("Filling in defaults...")
        self._props['defaults']['project'] = self.options['articleset'].project.id
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

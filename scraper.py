from amcatscraping.browser import Browser
from amcat.scripts.script import Script
from amcat.models.articleset import ArticleSet
from amcat.models.medium import Medium
from amcatclient.api import AmcatAPI

from django import forms
import logging; log = logging.getLogger(__name__)
from datetime import timedelta
import os

class ScraperForm(forms.Form):
    articleset = forms.ModelChoiceField(ArticleSet.objects.all())

class Scraper(Script):
    options_form = ScraperForm
    def run(self, input = None):
        # 1) Initialize when needed
        self._initialize()

        # 2) Get articles
        articles = list(self._scrape())

        # 3) Postprocess when needed
        articles = self._postprocess(articles)

        # 4) Save articles
        self._save(articles)

    def _initialize(self):
        pass

    def _scrape(self):
        """Scrape the target resource and return a sequence of article dicts"""
        raise NotImplementedError()

    def _postprocess(self, articles):
        pass

    def _save(self, articles):
        host = os.environ.get('AMCAT_API_HOST')
        user = os.environ.get('AMCAT_API_USER')
        passwd = os.environ.get('AMCAT_API_PASSWORD')
        api = AmcatAPI(host, user, passwd)
        api.create_articles(
            self.options['articleset'].project.id,
            self.options['articleset'].id,
            json_data = articles)
        


class QualityForm(ScraperForm):
    username = forms.CharField(required = False)
    password = forms.CharField(required = False)

class QualityScraper(Scraper):
    """
    Scraper with a number of convenience improvements:
    - auto-adds article.project and article.medium
    - optional _login function
    - unit-based scraping, so if one article fails, others don't
    - a browser at it's disposal
    - optionally checks for properties
    - possibility to specify date(s)
    - exception management, logging
    """
    options_form = QualityForm
    browser = Browser()

    def __init__(self, *args, **kwargs):
        if not all([
                os.environ.get('AMCAT_API_HOST'),
                os.environ.get('AMCAT_API_USER'),
                os.environ.get('AMCAT_API_PASSWORD')]):
            raise ValueError("Please specify AMCAT_API_HOST, AMCAT_API_USER, AMCAT_API_PASSWORD")

        if not hasattr(self, 'medium_name'):
            raise AttributeError("Please specify scraper.medium_name")
        super(QualityScraper, self).__init__(*args, **kwargs)

    def run(self, _input = None):
        self._initialize()
        articles = list(self._scrape())
        articles = self._postprocess(articles)
        self._save(articles)


    def _initialize(self):
        username = self.options.get('username')
        password = self.options.get('password')
        if not self._login(username, password):
            raise ValueError("Login failed")

    def _login(self, username, password):
        """To be overridden"""
        return True        


    def _scrape(self):
        for unit in self._get_units():
            try:
                yield self._scrape_unit(unit)
            except Exception:
                continue
            
    def _get_units(self):
        raise NotImplementedError()

    def _scrape_unit(self, unit):
        raise NotImplementedError()


    def _postprocess(self, articles):
        if hasattr(self, '_properties'):
            self._propertycheck(articles)
        for a in articles:
            a['medium'] = Medium.get_or_create(self.medium_name).id
            a['project'] = self.options['articleset'].project.id
        return articles

    def _propertycheck(self, articles):
        props = self._properties
        for prop in props['all']:
            log.info("checking '{prop}' property...".format(**locals()))
            assert all([a.get(prop) for a in articles])
        for prop in props['some']:
            log.info("checking '{prop}' property...".format(**locals()))
            assert any([a.get(prop) for a in articles])


    #### Utility functions ####

    def open(self, url, data = None):
        return self.browser.open(url, data)

    def getdoc(self, url, data = None):
        return self.browser.getdoc(url, data)

    def navigate(self, anchor):
        return self.browser.navigate(anchor)
    


class DateRangeForm(ScraperForm):
    first_date = forms.DateField()
    last_date = forms.DateField()

class DateRangeScraper(QualityScraper):
    """Like the quality scraper, but gives 2 dates between which the scraper must limit it's articles"""
    options_form = DateRangeForm

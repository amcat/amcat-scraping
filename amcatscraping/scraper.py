###########################################################################
# (C) Vrije Universiteit, Amsterdam (the Netherlands)            #
# #
# This file is part of AmCAT - The Amsterdam Content Analysis Toolkit     #
#                                                                         #
# AmCAT is free software: you can redistribute it and/or modify it under  #
# the terms of the GNU Lesser General Public License as published by the  #
# Free Software Foundation, either version 3 of the License, or (at your  #
# option) any later version.                                              #
#                                                                         #
# AmCAT is distributed in the hope that it will be useful, but WITHOUT    #
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or   #
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public     #
# License for more details.                                               #
#                                                                         #
# You should have received a copy of the GNU Lesser General Public        #
# License along with AmCAT.  If not, see <http://www.gnu.org/licenses/>.  #
###########################################################################
from __future__ import print_function
from collections import namedtuple
import json

import time
import datetime
import sys
import logging
import itertools
import collections

from .httpsession import Session
from .tools import to_date
from amcatclient.amcatclient import AmcatAPI


log = logging.getLogger(__name__)

ArticleTree = namedtuple("ArticleTree", ["article", "children"])


def _build_tree(article_children, articles, article_id):
    children = [_build_tree(article_children, articles, a) for a in article_children[article_id]]
    return ArticleTree(articles[article_id], children)


def build_tree(articles):
    articles = {a["id"]: a for a in articles}
    article_children = collections.defaultdict(set)

    for article in articles.values():
        article_children[article["parent"]].add(article["id"])

    return [_build_tree(article_children, articles, article_id) for article_id in article_children[None]]


def count_articles(articles):
    children = filter(None, (a.get("children", ()) for a in articles))
    return len(articles) + sum(map(count_articles, children))


class Scraper(object):
    def __init__(self, project_id, articleset_id, batched=False, batch_size=1000, dry_run=False, api_host=None, api_user=None, api_password=None, **kwargs):
        self.batched = batched
        self.batch_size = batch_size
        self.dry_run = dry_run

        self.project_id = project_id
        self.articleset_id = articleset_id

        self.session = Session()
        self.api = AmcatAPI(api_host, api_user, api_password)

    def scrape(self):
        """Scrape the target resource and return a sequence of article dicts"""
        raise NotImplementedError()

    def update(self, article_tree):
        """Update given articletree. Function should return an iterator with *NEW*
        articles. Each given article has an 'id', which can be used for the parent
        property on new articles.

        @type article_tree: ArticleTree
        @param article_tree: Existing articles"""
        raise NotImplementedError()

    def _save(self, articles):
        articles = self.api.create_articles(
            project=self.project_id,
            articleset=self.articleset_id,
            json_data=articles
        )
        return [article["id"] for article in articles]

    def save(self, articles):
        if self.dry_run:
            log.info("Scraper returned %s articles (not saving due to --dry-run)", count_articles(articles))
            return range(len(articles))

        log.info("Saving {alen} articles..".format(alen=count_articles(articles)))
        return self._save(articles)

    def postprocess(self, articles):
        """Space to do something with the unsaved articles that the scraper provided"""
        for article in map(dict, filter(None, articles)):
            if "metastring" in article:
                article["metastring"] = json.dumps(article["metastring"])
            yield article

    def _run(self, scrape_func):
        articles = []
        article_count = 0

        if not self.batch_size:
            log.info("Running scraper {self.__class__.__name__}..".format(**locals()))
        else:
            log.info("Running scraper {self.__class__.__name__} (batch size: {self.batch_size})".format(**locals()))

        for a in scrape_func():
            sys.stdout.write(".")
            sys.stdout.flush()

            articles.append(a)
            size = count_articles(articles)

            # Check if batch size is reached. If so: save articles, and proceed.
            if self.batch_size and size >= self.batch_size:
                log.info("Accumulated {size} articles. Preprocessing / saving..".format(**locals()))
                yield self.save(list(self.postprocess(articles)))
                articles = []
                article_count += size

        # Save articles not yet saved in loop
        article_count += count_articles(articles)
        log.info("Scraped a total of {article_count} articles.".format(**locals()))
        yield self.save(list(self.postprocess(articles)))

    def run(self):
        articles = list(itertools.chain.from_iterable(self._run(self.scrape)))
        log.info("Saved a total of {alen} articles.".format(alen=len(articles)))
        return articles

    def run_update(self):
        error_msg = "This functionality is currently only available for DateRangeScrapers"
        raise NotImplementedError(error_msg)


class UnitScraper(Scraper):
    """Scrapes the resource on a per-unit basis. Descendants should override
    the methods get_units() and scrape_unit(). Basically, what it does is:

    def scrape(self):
        for unit in self.get_units():
            yield self.scrape_unit(unit)

    """
    def get_units(self):
        return []

    def scrape_unit(self, unit):
        return None

    def _scrape(self, unit):
        try:
            return self.scrape_unit(unit)
        except Exception as e:
            log.exception(e)

    def scrape(self):
        for article in itertools.imap(self.scrape_unit, self.get_units()):
            if article is not None:
                yield article


class DateRangeScraper(Scraper):
    """
    Omits any articles that haven't been published in a given period.
    Provides a first_date and last_date option which children classes can use
    to select data from their resource.
    """
    medium = None

    def __init__(self, min_date, max_date, **kwargs):
        super(DateRangeScraper, self).__init__(**kwargs)

        assert(isinstance(min_date, datetime.date))
        assert(isinstance(max_date, datetime.date))
        assert(not isinstance(min_date, datetime.datetime))
        assert(not isinstance(max_date, datetime.datetime))

        self.min_date = min_date
        self.max_date = max_date
        self.dates = tuple(self._get_dates(self.min_date, self.max_date))

    def _get_dates(self, min_date, max_date):
        for n in range((max_date - min_date).days + 1):
            yield min_date + datetime.timedelta(days=n)

    def postprocess(self, articles):
        articles = list(super(DateRangeScraper, self).postprocess(articles))
        for a in articles:
            assert self.min_date <= to_date(a['date']) <= self.max_date
        return articles

    def _run_update_date(self, medium_id, date):
        log.info("Running update for {date}, medium_id={medium_id}".format(**locals()))

        # Fetch articles from database (including all properties) for one specific day
        log.info("Fetching existing articles..")
        end_date = date + datetime.timedelta(days=1)
        articles = self.api.search(self.articleset_id, "", start_date=date, end_date=end_date, mediumid=medium_id)
        articles = [article["id"] for article in articles]

        if not articles:
            # Ideally, api.list_articles wouldn't return any articles when filtering on an
            # empty list, but it does so we have to check for it explicitly.
            log.info("No existing articles found")
        else:
            articles = list(self.api.list_articles(self.project_id, self.articleset_id, pk=articles))
            log.info("Fetched {} existing articles".format(len(articles)))

            for article in build_tree(articles):
                for new_article in self.update(article):
                    yield new_article

    def _run_update(self):
        log.info("Trying to find medium id..")

        if self.medium is None:
            log.warning("Scraper has no medium name set. Skipping..")
        else:
            results = self.api.request("medium", name=self.medium)['results']

            if not results:
                error_msg = "Could not find medium with name {!r} in database."
                raise ValueError(error_msg.format(self.medium))
            elif len(results) > 1:
                error_msg = "Found multiple mediums with name={!r}"
                raise ValueError(error_msg.format(self.medium))

            medium_id = results[0]["id"]
            articles = (self._run_update_date(medium_id, date) for date in self.dates)
            return itertools.chain.from_iterable(articles)

        return []

    def run_update(self):
        """@raises: NotImplementedError if update functionality is not implemented"""
        log.info("Running update for {self.__class__.__name__}".format(**locals()))
        return list(self._run(self._run_update))


class ContinuousScraper(DateRangeScraper):
    """Blocks until an article of with a date greater than max_datetime is reached.
    min_datetime is ignored, but can be used to update articles. Continious scrapers
    typically don't include comments, but require the user to run update() periodically."""
    def __init__(self, timeout=60, **kwargs):
        """@param timeout: (if applicable) check for updates every N seconds"""
        super(ContinuousScraper, self).__init__(**kwargs)
        self.timeout = timeout

    def _scrape(self):
        while True:
            for article in super(ContinuousScraper, self).scrape():
                yield article
            time.sleep(self.timeout)

    def scrape(self):
        articles = self._scrape()
        articles = itertools.dropwhile(lambda a: to_date(a["date"]) < self.min_date, articles)
        articles = itertools.takewhile(lambda a: to_date(a["date"]) <= self.min_date, articles)
        return articles


class LoginMixin(object):
    """Logs in to the resource before scraping"""
    def __init__(self, username, password, **kwargs):
        super(LoginMixin, self).__init__(**kwargs)
        self.username = username
        self.password = password

    def scrape(self, *args, **kwargs):
        # Please ensure login returns True on success
        if not self.login(self.username, self.password):
            raise ValueError("Login routine returned False. Are your credentials correct?")
        return super(LoginMixin, self).scrape(*args, **kwargs)

    def login(self, username, password):
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

    def postprocess(self, articles):
        articles = super(PropertyCheckMixin, self).postprocess(articles)
        self._add_defaults(articles)
        self._check_properties(articles)
        return articles

    def _add_defaults(self, articles):
        self._props['defaults']['project'] = self.project_id
        self._props['defaults']['metastring'] = {}

        for prop, default in self._props['defaults'].items():
            for article in articles:
                if prop not in article:
                    article[prop] = default

        for article in articles:
            self._add_defaults(article.get("children", ()))

    def _check_properties(self, articles):
        if not articles:
            return

        for prop in self._props['required']:
            if not all(prop in article or prop in article['metastring'] for article in articles):
                raise ValueError("{prop} missing in at least one article".format(**locals()))

        for prop in self._props['expected']:
            if not any(prop in article or prop in article['metastring'] for article in articles):
                raise ValueError("{prop} missing in all articles".format(**locals()))

        for article in articles:
            self._add_defaults(article.get("children", ()))

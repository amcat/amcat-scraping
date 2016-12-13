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
from operator import itemgetter

import json
import os
import time
import datetime
import logging
import itertools

from typing import Iterable, List, Optional, Any, Union

from amcat.models import DateTimeEncoder
from amcat.tools.toolkit import splitlist
from .httpsession import Session
from .tools import to_date, memoize, open_json_cache
from amcatclient.amcatclient import AmcatAPI, APIError
from amcat.models import Article


log = logging.getLogger(__name__)


def article_to_json(article: Article):
    static_fields = article.static_fields() - {"id", "project_id", "project", "properties"}
    static_fields = {fn: getattr(article, fn) for fn in static_fields}
    return dict(static_fields, properties=dict(article.get_properties().items()))


def to_trees(children: Iterable[Union[Article, "ArticleTree"]]) -> Iterable["ArticleTree"]:
    for child in children:
        if isinstance(child, Article):
            yield ArticleTree(child, [])
        else:
            yield child


class ArticleTree:
    def __init__(self, article: Article, children: Iterable[Union[Article, "ArticleTree"]]):
        self.article = article
        self.children = list(to_trees(children))

    def __iter__(self):
        return iter((self.article, self.children))


class Scraper(object):
    publisher = None

    def __init__(self, project_id, articleset_id, batch_size=100, dry_run=False, api_host=None, api_user=None, api_password=None, scrape_comments=True, **kwargs):
        self.batch_size = batch_size
        self.dry_run = dry_run

        self.project_id = project_id
        self.articleset_id = articleset_id

        self.api_host = api_host
        self.api_user = api_user
        self.api_password = api_password
        self.scrape_comments = scrape_comments

        if not dry_run:
            self.api = self._api_auth()
        else:
            self.api = None

        self.session = Session()
        self.setup_session()

    def _api_auth(self) -> AmcatAPI:
        return AmcatAPI(self.api_host, self.api_user, self.api_password)

    def setup_session(self):
        pass

    def scrape(self) -> Iterable[Union[Article, ArticleTree]]:
        """Scrape the target resource and return a sequence of article dicts"""
        raise NotImplementedError("scrape() not implemented.")

    def _save(self, articles: List[Article]) -> Iterable[Article]:
        for batch in splitlist(articles, self.batch_size):
            json_data = [article_to_json(a) for a in batch]
            json_data = json.dumps(json_data, cls=DateTimeEncoder)
            new_articles = self.api.create_articles(self.project_id, self.articleset_id, json_data)
            for article, article_dict in zip(batch, new_articles):
                article.id = article_dict["id"]
                yield article

    def save(self, articles: List[Article], tries=5, timeout=15) -> Iterable[Article]:
        """
        Save given articles to the database in batches.

        :param articles: articles to be saved
        :param tries: number of API errors it should tolerate before giving up
        :param timeout: initial timeout, increases linearly with each try
        :return: articles with id set
        """
        if self.dry_run:
            log.info("Scraper returned %s articles (not saving due to --dry-run)", len(articles))
            return range(len(articles))

        log.info("Saving {alen} articles..".format(alen=len(articles)))

        # AmCAT API is really unstable :-(.
        try:
            return self._save(articles)
        except APIError:
            if tries <= 1:
                raise

            log.exception("Failed saving.. retrying in {} seconds".format(timeout))
            time.sleep(timeout)

            log.info("Trying reauth..")
            try:
                self.api = self._api_auth()
            except Exception:
                log.info("Reauth failed.. retry saving in {} seconds".format(timeout))
                time.sleep(timeout)
            else:
                log.info("Reauth OK.")

            return self.save(articles, tries=tries-1, timeout=timeout + 120)

    def postprocess(self, articles):
        """Space to do something with the unsaved articles that the scraper provided"""
        return articles

    def process_tree(self, article_tree: ArticleTree, parent_hash=None) -> Iterable[Article]:
        article, children = article_tree

        if self.publisher is not None and "publisher" not in article.properties:
            article.set_property("publisher", self.publisher)

        article.parent_hash = parent_hash
        article.compute_hash()
        yield article
        for child in children:
            yield from self.process_tree(child, parent_hash=article.hash)

    def _run(self) -> Iterable[Article]:
        log.info("Running scraper {self.__class__.__name__} (batch size: {self.batch_size})".format(**locals()))

        save_queue = []
        for article_tree in self.scrape():
            # Scrape can yield articles or trees
            if not isinstance(article_tree, ArticleTree):
                article_tree = next(iter(to_trees((article_tree,))))

            # Flatten tree, add to save queue
            save_queue.extend(self.process_tree(article_tree, article_tree.article.parent_hash))

            # Save if we've collected enough articles
            if len(save_queue) >= self.batch_size:
                yield from self.save(save_queue)
                save_queue.clear()

        # Save all others
        if save_queue:
            yield from self.save(save_queue)

    def run(self) -> List[Article]:
        articles = list(self._run())
        log.info("Saved a total of {alen} articles.".format(alen=len(articles)))
        return articles


class UnitScraper(Scraper):
    """Scrapes the resource on a per-unit basis. Descendants should override
    the methods get_units() and scrape_unit(). Basically, what it does is:

    def scrape(self):
        for unit in self.get_units():
            yield self.scrape_unit(unit)

    """
    def get_units(self) -> Iterable[Any]:
        return []

    def scrape_unit(self, unit) -> Optional[Article]:
        return None

    def scrape(self) -> Iterable[Union[Article, ArticleTree]]:
        for article in map(self.scrape_unit, self.get_units()):
            if article is not None:
                yield article


class DateRangeScraper(Scraper):
    """
    Omits any articles that haven't been published in a given period.
    Provides a first_date and last_date option which children classes can use
    to select data from their resource.
    """
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

        for article in articles:
            date = to_date(article.properties["date"])
            is_proper_date = self.min_date <= date <= self.max_date

            if article.parent is None and article.properties.get("parent") is None:
                error_msg = "{date} not within [{self.min_date}, {self.max_date}]"
                raise ValueError(error_msg.format(**locals()))

        return articles

CACHE_DIR = os.path.expanduser("~/.cache")


class DateNotFoundError(Exception):
    pass


class BinarySearchScraper(Scraper):
    """Some websites don't have an archive which is easily orderable on date, but do have
    ascending thread or article ids. This scraper takes advantage of that fact by performing
    a binary search through these ids.
    
    Descendants should implement the following methods:

      * get_latest()
      * get_oldest()
      * get_date(id)

    You should then be able to call get_first_of_date(date).
    
    You should also make sure to call _dump_id_cache() after scraping to save the id cache
    to disk. This scraper caches its id results across subsequent runs."""
    cache_file = os.path.join(CACHE_DIR, "{self.__class__.__name__}_cache.json")

    def __init__(self, *args, **kwargs):
        super(BinarySearchScraper, self).__init__(*args, **kwargs)
        cache_file = self.cache_file.format(**locals())
        self.id_cache = open_json_cache(cache_file, default={})

        dates, ids = zip(*dict(self.id_cache).items()) or [[], []]
        dates = [d.date() for d in map(datetime.datetime.fromtimestamp, dates)]
        self.id_cache = dict(zip(dates, ids))
        
        oldest_date, self.oldest_id = self.get_oldest()
        latest_date, self.latest_id = self.get_latest()
        self.id_cache[oldest_date] = self.oldest_id
        self.id_cache[latest_date] = self.latest_id
        self.valid_ids = self.get_valid_ids()
        self.valid_ids_pos = {id: pos for pos, id in enumerate(self.valid_ids)}

    def _dump_id_cache(self):
        dates, ids = zip(*self.id_cache.items()) or [[], []]
        dates = map(lambda d: int(time.mktime(d.timetuple())), dates)
        json.dump(zip(dates, ids), open(self.cache_file.format(**locals()), "w"))

    def get_valid_ids(self):
        """Returns ordered list of valid ids"""
        return list(range(self.oldest_id, self.latest_id + 1))

    def get_latest(self):
        """@returns (datetime.date, id)"""
        raise NotImplementedError("get_latest() not implemented.")

    def get_oldest(self):
        """@returns (datetime.date, id)"""
        raise NotImplementedError("get_oldest() not implemented.")

    @memoize
    def get_date(self, id):
        """Get date for given id. Must return None if given id does not exist,
        was deleted or otherwise invalid."""
        raise NotImplementedError("get_date() not implemented.")

    @memoize
    def _get_date(self, id):
        """
        """
        oldest_date, oldest_id = self.get_oldest()
        latest_date, latest_id = self.get_latest()

        if id > latest_id:
            raise DateNotFoundError("{id} exceeds latest id".format(id=id))

        if id < oldest_id:
            raise DateNotFoundError("{id} smaller than oldest id".format(id=id))

        date = self.get_date(id)
        if date is None:
            return self._get_date(id - 1)

        self.id_cache[date] = id
        return date

    def _get_first_id_linear(self, date):
        prev_id = id = self.id_cache[date]
        while date == self._get_date(id):
            prev_id = id
            id = self.valid_ids[self.valid_ids_pos[prev_id] - 1]
        return prev_id

    def _get_first_id(self, date, left_date, right_date):
        log.info("Looking for {date}. Left: {left_date}, right: {right_date}".format(**locals()))

        if date == left_date:
            return self._get_first_id_linear(left_date)

        if date == right_date:
            return self._get_first_id_linear(right_date)

        right_id = self.id_cache[right_date]
        right_pos = self.valid_ids_pos[right_id]
        left_id = self.id_cache[left_date]
        left_pos = self.valid_ids_pos[left_id]

        if left_date == right_date or right_pos - left_pos == 1:
            raise DateNotFoundError()

        pivot_pos = (left_pos + right_pos) // 2
        pivot_date = self._get_date(self.valid_ids[pivot_pos])

        if pivot_date < date:
            return self._get_first_id(date, pivot_date, right_date)
        else:
            return self._get_first_id(date, left_date, pivot_date)

    def get_first_by_date(self, date):
        """
        @raises DateNotFoundError, if no unit could be found on 'date'
        @returns id
        """
        # We first search our cache to minimize the calls made to the website we're scraping
        id_cache = sorted(self.id_cache.items(), key=itemgetter(0))

        # First determine left pivot..
        left_date, left_id = self.get_oldest()
        for cached_date, cached_id in id_cache:
            if cached_date > date:
                break

            if cached_date > left_date:
                left_id, left_date = cached_id, cached_date

        # Right pivot..
        right_date, right_id = self.get_latest()
        for cached_date, cached_id in reversed(id_cache):
            if cached_date < date:
                break

            if cached_date < right_date:
                right_id, right_date = cached_id, cached_date

        # Perform binary search for found interval
        return self._get_first_id(date, left_date, right_date)


class BinarySearchDateRangeScraper(DateRangeScraper, BinarySearchScraper):
    """

    """
    def _get_units(self, article_id):
        first_pos = self.valid_ids_pos[article_id]
        return map(self.scrape_unit, self.valid_ids[first_pos:])

    def scrape(self):
        article_id = None

        for date in self.dates:
            try:
                article_id = self.get_first_by_date(date)
            except DateNotFoundError:
                pass
            else:
                break

        if article_id is None:
            return []

        self._dump_id_cache()

        articles = filter(None, self._get_units(article_id))
        articles = filter(lambda a: to_date(a.properties["date"]) >= self.dates[0], articles)
        articles = itertools.takewhile(lambda a: to_date(a.properties["date"]) <= self.dates[-1], articles)
        return articles

    def scrape_unit(self, id):
        raise NotImplementedError("scrape_unit() not implemented.")


class LoginMixin(object):
    """Logs in to the resource before scraping"""
    def __init__(self, username, password, **kwargs):
        self.username = username
        self.password = password
        super(LoginMixin, self).__init__(**kwargs)

    def setup_session(self):
        super(LoginMixin, self).setup_session()

        if not self.login(self.username, self.password):
            raise ValueError("Login routine returned False. Are your credentials correct?")
        
    def login(self, username, password):
        raise NotImplementedError("login() not implemented.")


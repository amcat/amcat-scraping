###########################################################################
# (C) Vrije Universiteit, Amsterdam (the Netherlands)                     #
#                                                                         #
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
import atexit
import datetime
import json
import logging
import sys
import time

from typing import Iterable, List, Optional, Any, Union

from amcatclient.amcatclient import AmcatAPI, APIError
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, \
    StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from amcat.models import Article
from amcat.models import PropertyMappingJSONEncoder
from .httpsession import Session
from .tools import to_date

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


class ScraperAmcatAPI(AmcatAPI):
    def filter_existing_urls(self, project_id, set_ids, urls: List[str]):
        if not urls:
            return ()

        for url in urls:
            if "*" in url or "?" in url:
                raise ValueError("AmCAT does not allow looking for urls that contian * or ?")

        log.info("Checking if {} urls exist in AmCAT DB..".format(len(urls)))

        qs = ('url:"{}"'.format(url) for url in urls)
        q = "l1#" + "(" + ") OR (".join(qs) + ")"

        search = {
            'q': q,
            'project': project_id,
            'sets': set_ids,
            'col': ['id', 'url'],
            'page_size': len(urls),
        }

        response = self.request("search", **search)
        existing_urls = {row["url"] for row in response["results"]}
        return (url for url in urls if url not in existing_urls)


class Scraper(object):
    publisher = None

    def __init__(self, project_id: int, articleset_id: int, batch_size=100, dry_run=False,
                 api_host=None, api_user=None, api_password=None, scrape_comments=True,
                 deduplicate_on_url=True, use_http_url_db=False, options=None, **kwargs):
        """


        @param project_id:
        @param articleset_id:
        @param batch_size:
        @param dry_run:
        @param api_host:
        @param api_user:
        @param api_password:
        @param scrape_comments:
        @param deduplicate_on_url:
        @param kwargs:
        """
        self.batch_size = batch_size
        self.dry_run = dry_run

        self.project_id = project_id
        self.articleset_id = articleset_id

        self.no_api = False # Debugging switch
        self.api_host = api_host
        self.api_user = api_user
        self.api_password = api_password
        self.scrape_comments = scrape_comments
        self.options = options or {}

        if self.no_api:
            self.api = None
            self.dry_run = True
        else:
            self.api = self._api_auth()

        self.session = Session()
        self.deduplicate_on_url = deduplicate_on_url
        self.use_http_url_db = use_http_url_db
        self.duplicate_count = 0
        self.flush_flag = False

    def _api_auth(self) -> ScraperAmcatAPI:
        return ScraperAmcatAPI(self.api_host, self.api_user, self.api_password)

    def setup_session(self):
        pass

    def filter_existing_urls(self, urls: List[str]):
        if self.api is None:
            return urls

        if not urls:
            return []

        return self.api.filter_existing_urls(self.project_id, [self.articleset_id], urls)

    def set_flush_flag(self):
        self.flush_flag = True

    def scrape(self) -> Iterable[Union[Article, ArticleTree]]:
        """Scrape the target resource and return a sequence of article dicts"""
        raise NotImplementedError("scrape() not implemented.")

    def _save(self, articles: List[Article]) -> Iterable[Article]:
        if not articles:
            return []

        json_data = [article_to_json(a) for a in articles]
        json_data = json.dumps(json_data, cls=PropertyMappingJSONEncoder)
        new_articles = self.api.create_articles(self.project_id, self.articleset_id, json_data)
        for article, article_dict in zip(articles, new_articles):
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
        if self.deduplicate_on_url:
            log.info("Deduplicating {alen} articles based on urls in AmCAT DB..".format(alen=len(articles)))
            articles = list(self.deduplicate(articles))

        if self.dry_run:
            log.info("Scraper returned %s articles (not saving due to --dry-run)", len(articles))
            return articles

        if not articles:
            log.info("Articles already in AmCAT DB")
            return []

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

    def deduplicate(self, articles: List[Article]) -> Iterable[Article]:
        """Given a number of articles, return those not yet present in db based
        on the article's url"""
        filtered_urls = self.filter_existing_urls([article.url for article in articles])

        for article in articles:
            if article.url in filtered_urls:
                yield article
            else:
                self.duplicate_count += 1

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

            # Save if we've collected enough articles or if we're forced to flush
            if len(save_queue) >= self.batch_size or self.flush_flag:
                yield from self.save(save_queue)
                save_queue.clear()
                self.flush_flag = False

        # Save all others
        if save_queue:
            yield from self.save(save_queue)

    def run(self) -> List[Article]:
        articles = list(self._run())
        log.info("Saved a total of {alen} articles ({dups} duplicates filtered).".format(alen=len(articles), dups=self.duplicate_count))
        return articles


class Units:
    """Used when scraper wants to yield a list of units at a time."""
    def __init__(self, units):
        self.units = list(units)

    def __iter__(self):
        return iter(self.units)


class UnitScraper(Scraper):
    """Scrapes the resource on a per-unit basis. Descendants should override
    the methods get_units() and scrape_unit(). Basically, what it does is:

    def scrape(self):
        for unit in self.get_units():
            yield self.scrape_unit(unit)

    """
    def filter_existing_urls_by(self, units, get_url):
        units = {get_url(unit): unit for unit in units}
        for non_existing_url in self.filter_existing_urls(list(units.keys())):
            yield units[non_existing_url]

    def get_units(self) -> Iterable[Any]:
        raise NotImplementedError("Subclasses should implement get_units()")

    def scrape_unit(self, unit) -> Optional[Article]:
        raise NotImplementedError("Subclasses should implement get_unit()")

    def scrape(self) -> Iterable[Union[Article, ArticleTree]]:
        units_or_iterable = self.get_units()
        if isinstance(units_or_iterable, Units):
            uiterable = [units_or_iterable]
        else:
            uiterable = units_or_iterable

        for unit_or_units in uiterable:
            if isinstance(unit_or_units, Units):
                units = unit_or_units.units
            else:
                units = [unit_or_units]

            n_units_before = len(units)
            units = list(self.filter_existing_urls_by(units, self.get_url_from_unit))
            n_units_after = len(units)

            self.duplicate_count += n_units_before - n_units_after

            for unit in units:
                log.info("Scraping {}..".format(self.get_url_from_unit(unit)))
                article = self.scrape_unit(unit)
                if article is not None:
                    yield article

    def get_url_from_unit(self, unit: Any) -> str:
        raise NotImplementedError("Subclasses should implement get_url_from_unit()")


class DateRangeScraper(Scraper):
    """
    Omits any articles that haven't been published in a given period.
    Provides a first_date and last_date option which children classes can use
    to select data from their resource.
    """
    def __init__(self, min_date, max_date, **kwargs):
        super().__init__(**kwargs)

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

def quit_browser(browser):
    try:
        browser.quit()
    except:
        pass


class NotVisible(Exception):
    pass


class SeleniumMixin(object):
    do_not_load_images = True

    def setup_session(self):
        options = webdriver.ChromeOptions()
        if self.do_not_load_images:
            prefs = {'profile.managed_default_content_settings.images': 2}
            options.add_experimental_option('prefs', prefs)
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        if not "--no-headless" in sys.argv:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        self.browser = webdriver.Chrome(chrome_options=options)
        atexit.register(quit_browser, self.browser)
        super(SeleniumMixin, self).setup_session()

    def wait(self, selector, timeout=60, visible=True, by=By.CSS_SELECTOR, on=None):
        start = datetime.datetime.now()
        on = on or self.browser

        def check(e):
            if not visible:
                return True
            elif e.is_displayed():
                return True

            return False

        while True:
            seconds_forgone = (datetime.datetime.now() - start).total_seconds()

            try:
                element = on.find_element(by, selector)
                elements = on.find_elements(by, selector)
            except NoSuchElementException:
                if seconds_forgone > timeout:
                    raise
            else:
                for e in [element] + elements:
                    if check(e):
                        return e

                if seconds_forgone > timeout:
                    raise NotVisible("Element present, but not visible: {}".format(selector))

            time.sleep(0.5)

    def get_browser_preferences(self):
        return ()



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


class SeleniumLoginMixin(LoginMixin):
    login_url = None
    login_username_field = None
    login_password_field = None
    login_error_selector = None

    def login(self, username, password):
        self.browser.get(self.login_url)
        self.wait(self.login_username_field).send_keys(username)
        self.wait(self.login_password_field).send_keys(password)
        self.wait(self.login_password_field).send_keys(Keys.ENTER)

        time.sleep(2)

        try:
            self.wait(self.login_error_selector, timeout=3)
        except (NoSuchElementException, NotVisible, StaleElementReferenceException):
            return True
        else:
            return False


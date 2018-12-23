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
import sys
import time

from typing import Iterable, List, Optional, Any, Union

import requests
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.keys import Keys

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

    def _api_auth(self) -> AmcatAPI:
        return AmcatAPI(self.api_host, self.api_user, self.api_password)

    def setup_session(self):
        pass

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

    @functools.lru_cache()
    def get_latest_urls(self):
        if self.no_api:
            return set()

        if self.use_http_url_db:
            url = "{}/media/urls/latest".format(self.api_host)
            log.info("Getting latest urls at {}".format(url))

            urls_resp = requests.get(url)
            if urls_resp.status_code == 404:
                return set()
            elif urls_resp.status_code == 200:
                return set(urls_resp.text.rstrip().split('\n'))
            else:
                raise ValueError("HTTP url cache returned code {}".format(urls_resp.status_code))
        else:
            return self.get_urls(datetime.date.today())

    @functools.lru_cache()
    def get_urls(self, date: datetime.date) -> Set[str]:
        if self.no_api:
            return set()

        if self.use_http_url_db:
            # Fetch from HTTP cache
            url = "{}/media/urls/{}/{}/{}".format(
                self.api_host,
                date.year,
                str(date.month).zfill(2),
                str(date.day).zfill(2)
            )

            log.info("Getting urls for {} at {}".format(date, url))

            urls_resp = requests.get(url)
            if urls_resp.status_code == 404:
                return set()
            elif urls_resp.status_code == 200:
                return set(urls_resp.text.rstrip().split('\n'))
            else:
                raise ValueError("HTTP url cache returned code {}".format(urls_resp.status_code))

        else:
            log.info("Getting urls for {} using traditional API".format(date))

            # Use traditional API:
            return set(map(itemgetter("url"), self.api.list_articles(
                project=self.project_id,
                articleset=self.articleset_id,
                on_date=date.isoformat(),
                minimal=1,
                col=["url"],
                page_size=9999
            )))

    def deduplicate(self, articles: Iterable[Article]) -> Iterable[Article]:
        """Given a number of articles, return those not yet present in db based
        on the article's url"""
        for article in articles:
            if article.url not in self.get_urls(to_date(article.date)):
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
        for unit in self.get_units():
            if self.deduplicate_on_url:
                try:
                    url = self.get_url_from_unit(unit)
                except NotImplementedError:
                    pass
                else:
                    if url in self.get_latest_urls():
                        # Duplicate detected
                        self.duplicate_count += 1
                        continue

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
    def setup_session(self):
        options = webdriver.ChromeOptions()
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


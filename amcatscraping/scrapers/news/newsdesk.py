###########################################################################
#          (C) Vrije Universiteit, Amsterdam (the Netherlands)            #
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
import datetime
import locale
import random
import time
import urllib.parse

import lxml.html
from collections import namedtuple
from typing import Tuple, Iterable

from html2text import html2text
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

from amcat.models import Article
from amcatscraping.scraper import SeleniumLoginMixin, SeleniumMixin, DeduplicatingUnitScraper

NewsdeskUnit = namedtuple("NewsdeskUnit", ["article_element", "article"])

DATA_URL = "http://content.moreover.com/eApolloRequest?data="
SEARCH_URL = "https://newsdesk.moreover.com/search"
MEDIUMS = ["Gedrukte media"]
LANGUAGES = ["Nederlands"]


def get_newsdesk_article_id(url):
    query = urllib.parse.urlparse(url).query
    query = urllib.parse.parse_qs(query)
    return int(query['a'][0])


def dutch_strptime(date, pattern):
    loc = locale.getlocale()
    locale.setlocale(locale.LC_ALL, 'nl_NL.UTF-8')
    try:
        return datetime.datetime.strptime(date, pattern)
    finally:
        locale.setlocale(locale.LC_ALL, loc)


def get_data_urls(article_element):
    for a in article_element.find_elements_by_css_selector("a"):
        href = a.get_attribute("href")
        if href and href.startswith(DATA_URL):
            yield href


class NewsdeskScraper(SeleniumLoginMixin, SeleniumMixin, DeduplicatingUnitScraper):
    login_url = "https://newsdesk.moreover.com/index.html"
    login_username_field = "#username"
    login_password_field = "#password"
    login_error_selector = "form .error_block"

    def is_cached(self, unit: NewsdeskUnit):
        key = self._get_deduplicate_key_from_unit(unit)
        return self.cache.sismember(self._get_redis_key(), key)

    def get_browser_preferences(self):
        yield "intl.accept_languages", "nl"

    def setup_session(self):
        super(NewsdeskScraper, self).setup_session()

        self.browser.get(SEARCH_URL)

        # Enable beta search interface
        self.wait(".switch__input", visible=False)
        beta_script = 'return document.getElementsByClassName("switch__input")[0].checked;'
        beta_enabled = self.browser.execute_script(beta_script)
        if not beta_enabled:
            self.wait(".switch__icon").click()
            self.wait(".toast")
            self.browser.get(SEARCH_URL)

    def get_deduplicate_key_from_unit(self, unit: NewsdeskUnit) -> str:
        return unit.article.url

    def get_deduplicate_key_from_article(self, article: Article) -> str:
        return article.url

    def get_deduplicate_units(self) -> Iterable[NewsdeskUnit]:

        # Set media
        self.wait(".search-filter-media-type__trigger").click()
        self.wait(".search-area__filter-button--clear").click()
        for medium in MEDIUMS:
            self.wait('//label[text() = "{}"]'.format(medium), by=By.XPATH).click()

        # Set langauges
        self.wait(".search-filter-language__trigger").click()
        self.wait(".search-filter-container__filter-button--clear").click()
        for language in LANGUAGES:
            self.wait('label[title="{}"]'.format(language)).click()

        # Set 'search in last 24 hours'
        self.wait(".search-filter-date__trigger").click()
        self.wait('//span[text() = "{}"]'.format("3 dagen"), by=By.XPATH).click()

        # Search!
        self.wait(".rich-search-box__content").click()
        self.wait(".rich-search-box__content").send_keys("*")
        self.wait(".search-area__search-trigger").click()

        # Enlarge search results
        self.wait(".paginator__button")
        self.browser.find_elements_by_css_selector(".paginator__button")[-1].click()

        # Find articles
        while True:
            start = datetime.datetime.now()
            while datetime.datetime.now() - start < datetime.timedelta(seconds=30):
                ajax_mask = self.wait("#article_ajax_mask", visible=False)
                if not ajax_mask.is_displayed():
                    break

            # Yield articles
            articles = self.browser.find_elements_by_css_selector("#article-results-list > div")
            article_units = list(map(self.scrape_unit_meta, articles))
            yield from article_units

            # If first and last article were already in db, we're done
            first_article_cached = self.is_cached(article_units[0])
            last_article_cached = self.is_cached(article_units[-1])
            if first_article_cached and last_article_cached:
                break
            else:
                next_page_button = self.browser.find_elements_by_css_selector(".paginator .paginator__button")[-1]
                if next_page_button.is_enabled():
                    next_page_button.click()
                else:
                    break

    def get_url_and_date_from_unit(self, unit: NewsdeskUnit) -> Tuple[str, datetime.date]:
        return unit.article.url, unit.article.date

    def scrape_unit_meta(self, article_element):
        article_html = article_element.get_attribute("outerHTML")
        article_doc = lxml.html.fromstring(article_html, base_url=SEARCH_URL)

        def get_byline_prop(prop):
            try:
                return article_doc.cssselect(".article_byline__element.{}".format(prop))[0].text_content().strip()
            except IndexError:
                raise ValueError("Article {} has no property '{}'.".format(title, prop))

        text_url = article_doc.cssselect("a.article_headline")[0].get("href")
        url = "newsdesk://{}".format(get_newsdesk_article_id(text_url))

        title = article_doc.cssselect("a.article_headline")[0].text_content().strip()
        publisher = get_byline_prop("source_name")

        date = get_byline_prop("harvest_date")
        date, pub_date = date.split("(gepubliceerd: ")
        date = dutch_strptime(date.strip(), "%d %b %Y %H:%M")
        pub_date = dutch_strptime(pub_date.strip()[:-1], "%d %b %Y %H:%M")

        article = Article(url=url, title=title, date=date)
        article.set_property("publisher", publisher)
        article.set_property("text_url", text_url)
        article.set_property("pubdate_date", pub_date)

        try:
            article.set_property("author", get_byline_prop("author"))
        except ValueError:
            pass

        try:
            article.set_property("wordcount_int", int(get_byline_prop("word_count").split()[0]))
        except ValueError:
            pass

        try:
            article.set_property("country", get_byline_prop("source_country"))
        except ValueError:
            pass

        return NewsdeskUnit(article_element, article)

    def scrape_unit(self, unit: NewsdeskUnit):
        article_element, article = unit

        try:
            article_element.find_element_by_css_selector(".extract_full_link_button").click()
        except NoSuchElementException:
            pass
        else:
            self.wait(".fo-icon-compact.extract_full_link_button", on=article_element)

        inner = self.wait(".extract_inner", on=article_element)
        article_html = inner.get_attribute("innerHTML")
        article.text = html2text(article_html)

        for i, data_url in enumerate(get_data_urls(inner)):
            article.set_property("data{}_url".format(i), data_url)

        # Be gentle with servers
        time.sleep(random.uniform(0.5, 5.0))

        return article

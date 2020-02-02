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

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

from amcat.models import Article
from amcatscraping.scraper import SeleniumLoginMixin, SeleniumMixin, DeduplicatingUnitScraper, NotVisible
from amcatscraping.tools import html2text

NewsdeskUnit = namedtuple("NewsdeskUnit", ["article_element", "article"])

DATA_URL = "http://content.moreover.com/eApolloRequest?data="
#SEARCH_URL = "https://newsdesk.moreover.com/search"
SEARCH_URL ="https://www.newsdesk.lexisnexis.com/search"
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
    seen = set()
    for a in article_element.find_elements_by_css_selector("a"):
        href = a.get_attribute("href")
        if href and href.startswith(DATA_URL):
            if href not in seen:
                yield href
                seen.add(href)

# c = amcatscraping.scrapers.news.newsdesk.CONTEXT
CONTEXT = {}
class NewsdeskScraper(SeleniumLoginMixin, SeleniumMixin, DeduplicatingUnitScraper):
    #login_url = "https://newsdesk.moreover.com/index.html"
    login_url = "https://signin.lexisnexis.com/lnaccess/app/signin?aci=nd&back=https%3A%2F%2Fwww.newsdesk.lexisnexis.com%2Flogin%2Fwam%2Fverify%3Fremember-me%3Dtrue"
    login_username_field = "#userid"
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

    def get_deduplicate_key_from_unit(self, unit: NewsdeskUnit) -> str:
        return unit.article.url

    def get_deduplicate_key_from_article(self, article: Article) -> str:
        return article.url

    def get_deduplicate_units(self) -> Iterable[NewsdeskUnit]:
        CONTEXT['browser'] = self.browser
        try:
            self.wait("._pendo-guide-dismiss_.no-thanks", timeout=5).click()
        except NoSuchElementException:
            pass

        # Set media
        self.wait(".search-filter-media-type__trigger").click()
        self.wait(".search-area__filter-button--clear").click()
        for medium in MEDIUMS:
            self.wait('//label[text() = "{}"]'.format(medium), by=By.XPATH).click()

        # Set langauges
        self.wait(".search-filter-language__trigger").click()
        self.wait(".search-filter-container__filter-button--clear").click()
        for language in LANGUAGES:
            self.wait('//label[text() = "{}"]'.format(language), by=By.XPATH).click()

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
        #    print(start)
            #while datetime.datetime.now() - start < datetime.timedelta(seconds=30):
             #   ajax_mask = self.wait("#article_ajax_mask", visible=False)
              #  if not ajax_mask.is_displayed():
               #     time.sleep(1)
                #    break

            time.sleep(5)

            # Yield articles
            articles = self.browser.find_elements_by_css_selector(".nd-article-list > article")
           # print(f"dit is articlelist{articles}")
            article_units = list(map(self.scrape_unit_meta, articles))
         #   print(f"units{article_units}")

            # If first and last article were already in db, we're done
            first_article_cached = self.is_cached(article_units[0])
            last_article_cached = self.is_cached(article_units[-1])

            yield from article_units

            if first_article_cached and last_article_cached:
                break
            else:
                next_page_button = self.browser.find_elements_by_css_selector(".paginator .paginator__button")[-1]
                if "disable" in next_page_button.get_attribute("class").split():
                    break
                else:
                    next_page_button.click()

    def get_url_and_date_from_unit(self, unit: NewsdeskUnit) -> Tuple[str, datetime.date]:
        return unit.article.url, unit.article.date

    def scrape_unit_meta(self, article_element):
        CONTEXT['unit'] = article_element

        article_html = article_element.get_attribute("outerHTML")
     #   print(f"dit is html{article_html}")
        article_doc = lxml.html.fromstring(article_html, base_url=SEARCH_URL)
        CONTEXT['doc'] = article_element

        def get_byline_prop(prop):
            for meta_element in article_doc.cssselect(f".nd-article__{prop}"):
                prop_value = meta_element.text_content().strip()
                if prop_value:
                    return prop_value
            else:
                raise ValueError("Article {} has no property '{}'.".format(title, prop))

        text_url = article_doc.cssselect("a.nd-article__headline-text")[0].get("href")
        url = "newsdesk://{}".format(get_newsdesk_article_id(text_url))
        title = article_doc.cssselect("a.nd-article__headline-text")[0].text_content().strip()
        publisher = get_byline_prop("source")
        date_text = article_doc.cssselect(".nd-article__date")[0].get("title")
        date = date_text.split("Publicatiedatum:")
        pub_date = date[-1]
        pub_date = dutch_strptime(pub_date.strip()[:-1], "%d %b %Y %H:%M")
        load_date = date[1]
        load_date = dutch_strptime(load_date.strip(), "%d %b %Y %H:%M")

        article = Article(url=url, title=title, date=pub_date)
        article.set_property("publisher", publisher)
        article.set_property("text_url", text_url)

        # Crashes AmCAT API:
        #article.set_property("pubdate_date", pub_date)

        try:
            author = get_byline_prop("author")
            article.set_property("author", author)
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
        text, data_urls = self._get_article_text(article_element)
        article.text = text
        for i, data_url in enumerate(data_urls):
            article.set_property("data{}_url".format(i), data_url)
        return article

    def _get_article_text(self, article_element):
        # Click on headline to open text in new window.
        # First, remember current window handle so we can switch back
        driver = article_element.parent
        main = driver.current_window_handle
        try:
            # open new window and get handle
            existing_handles = driver.window_handles
            article_element.find_element_by_css_selector("a.nd-article__headline-text").click()
            new_handle, = set(driver.window_handles) - set(existing_handles)
            print(f"Got handle: {new_handle}")
            driver.switch_to_window(new_handle)
            try:
                # extract text
                article = self.wait("#article")

                ps = article.find_elements_by_css_selector(".article_extract p")
                print(f"Found {len(ps)} paragraphs")
                if not ps:
                    raise Exception("Could not get text")
                text = "\n\n".join([p.text for p in ps])
                # get data urls
                data_urls = list(get_data_urls(article))[:3]

                time.sleep(random.uniform(0.1, 0.3))
            finally:
                driver.close()
        finally:
            driver.switch_to_window(main)
        return text, data_urls

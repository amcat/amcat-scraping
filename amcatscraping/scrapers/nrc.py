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

import collections
import datetime
import json
import locale
import re

from selenium.common.exceptions import NoSuchElementException

from amcat.models import Article
from amcatscraping.scraper import UnitScraper, DateRangeScraper, \
    Units, SeleniumMixin, SeleniumLoginMixin
from amcatscraping.tools import html2text

AUTHOR_RE = re.compile('"author": \[{"name": "(?P<name>[^"]+)", "@type": "Person"}')

ArticleTuple = collections.namedtuple("ArticleTuple", ["url", "date", "page"])


def dutch_strptime(date, pattern):
    loc = locale.getlocale()
    locale.setlocale(locale.LC_ALL, 'nl_NL.UTF-8')
    try:
        return datetime.datetime.strptime(date, pattern)
    finally:
        locale.setlocale(locale.LC_ALL, loc)


PAGE_NR_RE = re.compile("#\d+$")
def strip_pagenr(url):
    if PAGE_NR_RE.search(url):
        (url, _) = PAGE_NR_RE.split(url)
    return url


class NRCScraper(SeleniumLoginMixin, SeleniumMixin, DateRangeScraper,
                 UnitScraper):
    publisher = None
    edition = None

    cookies_ok_button = "CookiesOK cookie-bar__button"
    krant_url = "https://www.nrc.nl/{edition}/{year}/{month:02d}/{day:02d}/"
    login_url = "https://login.nrc.nl/login"
    login_username_field = "#username"
    login_password_field = "#password"
    login_error_selector = ".feedback.fout > p"
    allow_missing_login = False

    def __init__(self, *args, **kwargs):
        super(NRCScraper, self).__init__(*args, **kwargs)
        self.seen_urls = set()

    def is_valid_url(self, url):
        if "/index/" in url:
            return False

        if not url.startswith("https://www.nrc.nl/"):
            return False

        return True

    def get_url_from_unit(self, unit: ArticleTuple) -> str:
        return unit.url

    def _get_urls(self, date):
        url = self.krant_url.format(
            edition=self.edition,
            year=date.year,
            month=date.month,
            day=date.day
        )

        self.browser.get(url)

        if self.browser.current_url == url:
            pages = self.wait(".paper__pages")
            for page in pages.find_elements_by_css_selector(".c-page"):
                pagenr = page.get_attribute("id")[len("page-"):]
                for article in page.find_elements_by_css_selector(
                        "a.c-page__article"):
                    url = strip_pagenr(article.get_attribute("href"))
                    if self.is_valid_url(url):
                        yield ArticleTuple(url, date, pagenr)

    def _dedup_urls(self, tups):
        seen_urls = set()
        for (url, date, page) in tups:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            yield ArticleTuple(url, date, page)

    def get_units(self):
        for date in self.dates:
            yield Units(
                self._dedup_urls(
                    self._get_urls(date)
                )
            )

    def get_meta(self, tag):
        return (
            self.browser
                .find_element_by_css_selector("meta[property='{}']".format(tag))
                .get_attribute("content")
        )

    def scrape_unit(self, unit: ArticleTuple):
        (url, date, page) = unit

        self.browser.get(url)

        try:
            self.browser.find_element_by_css_selector("main .index-404")
        except NoSuchElementException:
            return

        url = self.browser.current_url
        title = self.get_meta("og:title")
        subject = self.get_meta("ad:subject")
        categories = self.get_meta("ad:categories")
        pagenr = int(page[1:])

        author = None
        author_re = AUTHOR_RE.search(self.browser.page_source)
        if author_re:
            author = author_re.groupdict()["name"].strip()
            author = json.loads('"{}"'.format(author))

        article = self.browser.find_element_by_css_selector(".content.article__content")
        article_html = article.get_attribute("innerHTML")
        text = html2text(article_html)

        article = Article(date=date, title=title, text=text, url=url)
        article.set_property("pagenr_int", pagenr)
        article.set_property("page", page)
        article.set_property("subject", subject)
        article.set_property("categories", categories)

        if author is not None:
            article.set_property("author", author)

        if url not in self.seen_urls:
            self.seen_urls.add(url)
            return article

class NRCNextScraper(NRCScraper):
    publisher = "NRC.NEXT"
    edition = "next"

class NRCHandelsbladScraper(NRCScraper):
    publisher = "NRC Handelsblad"
    edition = "handelsblad"


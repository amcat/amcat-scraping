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
import logging
import re

import itertools

import collections
from typing import Tuple

import lxml.html

from urllib import parse

from amcat.models import Article
from amcatscraping.tools import parse_form, html2text
from amcatscraping.scraper import LoginMixin, UnitScraper, DateRangeScraper

log = logging.getLogger(__name__)

OLDEST_SUPPORTED_NEWSPAPER = datetime.date(2015, 12, 1)
ACCEPT_COOKIE = {"cookieconsent": "true", "cookieLaw": "read"}
ARTICLE_URL_RE = re.compile("""
    ^/HFD_
    (?P<year>\d{4})
    (?P<month>\d{2})
    (?P<day>\d{2})
    _0_
    (?P<page_num>\d{3})
    _
    (?P<article_num>\d{3})
    $
""", re.VERBOSE)

# URLS
BASE_URL = "https://fd.nl"
LOGIN_URL = parse.urljoin(BASE_URL, "/login")
KRANT_URL = parse.urljoin(BASE_URL, "/krant/{year}/{month:02d}/{day:02d}")


ArticleTuple = collections.namedtuple("ArticleTuple", ["date", "page_num", "url"])


def strip_query(url: str) -> str:
    return parse.urljoin(url, parse.urlparse(url).path)


class FinancieelDagbladScraper(LoginMixin, UnitScraper, DateRangeScraper):
    publisher = "Financieel Dagblad"

    def __init__(self, *args, **kwargs):
        super(FinancieelDagbladScraper, self).__init__(*args, **kwargs)
        self.rxst = None

    def login(self, username, password):
        # Set right cookies
        self.session.get(BASE_URL)

        # HACK! FD has intermediate cert which is not downloaded automatically
        # by requests/curl, so we disable ssl certification for the time being
        # Please check whether this has been resolved and re-enable verification!
        login_page = self.session.get(LOGIN_URL, verify=False, cookies=ACCEPT_COOKIE)
        login_doc = lxml.html.fromstring(login_page.content)
        login_form = login_doc.cssselect("form.login")[0]
        login_post_url = parse.urljoin(LOGIN_URL, login_form.get("action"))
        login_fail_url = login_form.cssselect("input[name=failureUrl]")[0].get("value")
        login_fail_url = parse.urljoin(LOGIN_URL, login_fail_url)

        # Login
        post_data = parse_form(login_form)
        post_data.update({"username": username, "password": password})
        response = self.session.post(login_post_url, post_data, verify=False, allow_redirects=False)

        # Check if logging in worked :)
        return response.url != login_fail_url

    def _get_pages(self, date):
        paper_url = KRANT_URL.format(year=date.year, month=date.month, day=date.day)

        response = self.session.get(paper_url)
        if response.url != paper_url:
            # No paper published on this date
            return

        overview = lxml.html.fromstring(response.content.decode())
        for a in overview.cssselect("a"):
            match = ARTICLE_URL_RE.match(a.get("href"))
            if match:
                url = parse.urljoin(BASE_URL, a.get('href'))
                yield ArticleTuple(date, int(match.group("page_num")), url)

    def get_units(self):
        pages = map(self._get_pages, self.dates)
        pages = map(set, pages)
        pages = map(sorted, pages)
        return itertools.chain.from_iterable(pages)

    def get_url_and_date_from_unit(self, unit: ArticleTuple) -> Tuple[str, datetime.date]:
        return unit.url, unit.date

    def scrape_unit(self, article_info: ArticleTuple):
        date, page_num, url = article_info
        text_url = strip_query(self.session.get_redirected_url(url))

        text_doc = self.session.get_html(text_url)

        for image in text_doc.cssselect(".image"):
            image.getparent().remove(image)

        date = datetime.datetime(date.year, date.month, date.day)
        title = text_doc.cssselect("article > h1")[0].text

        section = text_doc.cssselect("article > header > .title")[0].text
        text = html2text(text_doc.cssselect("main > article > .body"))
        article = Article(title=title, date=date, text=text, url=url)

        author_a = text_doc.cssselect("article .author a")
        if author_a:
            author = author_a[0].text.strip()
            article.set_property("author", author)
            if author == section:
                section = "Opinie"

        download = text_doc.cssselect('form[name="download"]')
        if download:
            pdf_url = download[0].get("action")
            article.set_property("pdf_url", pdf_url)

        article.set_property("text_url", text_url)
        article.set_property("image_url", text_url + "?view=img")

        if section:
            article.set_property("section", section.strip())

        return article


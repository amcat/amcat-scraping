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
from urllib.parse import urljoin

import lxml.html
import collections
import itertools
import datetime
import logging
import re


from typing import Tuple
from urllib import parse

from requests import cookies, HTTPError

from amcat.models import Article
from amcatscraping.tools import parse_form, html2text
from amcatscraping.scraper import LoginMixin, UnitScraper, DateRangeScraper
from amcatscraping.httpsession import RedirectError

log = logging.getLogger(__name__)

OLDEST_SUPPORTED_NEWSPAPER = datetime.date(2015, 12, 1)
ARTICLE_URL_RE = re.compile("""
    ^/HFD_
    (?P<year>\d{4})
    (?P<month>\d{2})
    (?P<day>\d{2})
    _\d+_
    (?P<page_num>\d{3})
    _
    (?P<article_num>\d{3})
    $
""", re.VERBOSE)

# URLS
BASE_URL = "https://fd.nl/"
LOGIN_URL = parse.urljoin(BASE_URL, "login")
KRANT_URL = parse.urljoin(BASE_URL, "krant/{year}/{month:02d}/{day:02d}")


ArticleTuple = collections.namedtuple("ArticleTuple", ["date", "page_num", "url"])


def strip_query(url: str) -> str:
    return parse.urljoin(url, parse.urlparse(url).path)


class FinancieelDagbladScraper(LoginMixin, UnitScraper, DateRangeScraper):
    publisher = "Financieel Dagblad"

    def __init__(self, *args, **kwargs):
        super(FinancieelDagbladScraper, self).__init__(*args, **kwargs)
        self.rxst = None
        self.session.sleep = 1

    def login(self, username, password):
        # Set right cookies
        self.session.get(BASE_URL)
        self.session.cookies.set_cookie(cookies.create_cookie(domain='fd.nl', name='cookieconsent', value='true'))

        login_page = self.session.get(LOGIN_URL)
        login_doc = lxml.html.fromstring(login_page.content)
        login_form = login_doc.cssselect(".modal-content form")[0]
        login_post_url = parse.urljoin(LOGIN_URL, login_form.get("action"))

        # Login
        post_data = parse_form(login_form)
        post_data.update({"username": username, "password": password})
        response = self.session.post(login_post_url, post_data, verify=False, allow_redirects=True)

        # Check if logging in worked :)
        return response.url == BASE_URL

    def _get_pages(self, date):
        paper_url = KRANT_URL.format(year=date.year, month=date.month, day=date.day)

        response = self.session.get(paper_url)
        if response.url != paper_url:
            logging.warning("No paper published on this date")
            return

        overview = lxml.html.fromstring(response.content.decode())
        for publication in overview.cssselect(".digikrant-section a"):
            publication_url = urljoin(paper_url, publication.get("href"))
            paper = self.session.get_html(publication_url)

            for a in paper.cssselect("a"):
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

        try:
            text_url = strip_query(self.session.get_redirected_url(url))
        except RedirectError as e:
            if e.status_code == 404:
                return None
            raise

        try:
            text_doc = self.session.get_html(text_url)
        except HTTPError as e:
            if e.response.status_code == 404:
                logging.warning(f"{url} returned 404 skipping")
                return None
            else:
                raise



        for image in text_doc.cssselect(".image"):
            image.getparent().remove(image)

        date = datetime.datetime(date.year, date.month, date.day)
        try:
            title = text_doc.cssselect("article > h1")[0].text.strip()
        except:
            return None

        text = html2text(text_doc.cssselect("main > article > .body"))
        if not text.strip():
            return None

        article = Article(title=title, date=date, text=text, url=url)

        if text_doc.cssselect("article > header.themed"):
            # New headers style
            author = text_doc.cssselect("article > header .author")[0].text
            section = text_doc.cssselect("article > header .title")[0].text
            article.set_property("author", author)
        else:
            # Old header style
            section = text_doc.cssselect("article > header > .title")
            section = section[0].text if section else "NOSECTION"
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


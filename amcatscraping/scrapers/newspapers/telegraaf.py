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

import logging
import itertools
import collections
import datetime
import time
import re

from datetime import date
from selenium import webdriver
from typing import Tuple

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.keys import Keys

from amcat.models import Article
from amcatscraping.scraper import UnitScraper, DateRangeScraper, LoginMixin
from amcatscraping.tools import parse_form, setup_logging

log = logging.getLogger(__name__)


ArticleTuple = collections.namedtuple("Article", ["article_id", "pagenr", "section", "date"])

ARTICLE_URL = "http://www.telegraaf.nl/telegraaf-i/article/{article_id}"
LOGIN_URL = "https://www.telegraaf.nl/wuz/loginbox?nocache"
WEEK_URL = "http://www.telegraaf.nl/telegraaf-i/week"


AUTHOR_RE = re.compile("^door (?P<author>.+)$")


def mkdate(string):
    return date(*map(int, string.split("-")))


class TelegraafScraper(LoginMixin, UnitScraper, DateRangeScraper):
    publisher = "De Telegraaf"

    def __init__(self, username, password, **kwargs):
        super().__init__(username, password, **kwargs)

    def wait(self, css_selector, timeout=30, visible=True):
        start = datetime.datetime.now()

        while True:
            try:
                element = self.browser.find_element_by_css_selector(css_selector)
            except NoSuchElementException:
                if (datetime.datetime.now() - start).total_seconds() > timeout:
                    raise
            else:
                if not visible:
                    return element
                elif element.is_displayed():
                    return element

            time.sleep(0.5)

    def login(self, username, password):
        # In the Telegraaf's eternal search for quality, they decided to rely on
        # complicated inter-iframe communication and javascript logic to generate
        # cookies needed to fetch articles. We therefore simulate logging in and
        # reading an article with a real browser. We then steal them cookies and
        # use it for normal scraping.
        log.info("Starting Firefox..")
        self.browser = webdriver.Firefox()

        try:
            self.browser.set_window_size(1920, 1080)
            log.info("Accepting cookies on telegraaf.nl..")
            self.browser.get('http://telegraaf.nl/')
            self.browser.implicitly_wait(30)
            self.wait(".CookiesOK").click()
            log.info("Selecting first article..")
            self.browser.get("https://www.telegraaf.nl/telegraaf-i/")
            self.wait(".newspapers > li").click()
            log.info("Logging in..")
            self.wait(".js-link-login > a").click()
            self.browser.switch_to.frame(self.wait(".tglogin-overlay-window__iframe"))
            self.wait("#email").send_keys(self.username)
            self.wait("#password").send_keys(self.password)
            self.wait("#password").send_keys(Keys.RETURN)
            self.browser.switch_to.default_content()
            log.info("Wait for log in refresh..")
            self.wait(".js-link-username")
            log.info("Waiting for article to load..")
            self.wait(".article > a").click()
            self.wait("#article")

            log.info("Copying cookies..")
            for cookie in self.browser.get_cookies():
                cookie.pop("expiry")
                cookie.pop("httpOnly")
                self.session.cookies.set(**cookie)

            return True
        finally:
            self.browser.quit()

    def get_units(self):
        data = self.session.get("http://www.telegraaf.nl/telegraaf-i/newspapers").json()
        papers = [paper for paper in data if mkdate(paper['date']) in self.dates]

        for paper in papers:
            for page in paper['pages']:
                for article_id in page['articles']:
                    section = [s['title'] for s in paper['sections'] if page['page_number'] in s['pages']][0]
                    yield ArticleTuple(article_id, page['page_number'], section, mkdate(paper['date']))

    def get_url_and_date_from_unit(self, unit: ArticleTuple) -> Tuple[str, datetime.date]:
        return ARTICLE_URL.format(article_id=unit.article_id), unit.date

    def scrape_unit(self, article):
        article_id, pagenr, section, date = article

        if section == "Advertentie":
            return None

        url = ARTICLE_URL.format(article_id=article_id)

        data = collections.defaultdict(str, **self.session.get(url).json())
        if list(data.keys()) == ["authenticate_url"]:
            raise Exception("Login for Telegraaf failed")

        if not data.get('headline'):
            return None

        article = Article(url=url, title=data.get("headline"), date=date)
        article.set_property("section", section)
        article.set_property("pagenr_int", int(pagenr))

        body = dict.fromkeys(itertools.chain.from_iterable(data["body"]), "")

        for dic in data['body']:
            for k, v in dic.items():
                body[k] += v + "\n\n"

        lead = body.get("lead", "")
        byline = body.get("paragraph") or body.get("byline", "")
        article.text = lead + byline

        if not article.text:
            return None

        if body.get("subheadline"):
            article.set_property("subheadline", body.get("subheadline"))

        if body.get("media-caption"):
            article.set_property("mediacaption", body.get("media-caption"))

        newspaper_id = "/{}/".format(data["newspaper_id"])
        article.set_property("text_url", article.url.replace("/article/", newspaper_id))
        article.set_property("image_url", article.url.replace("/article/", newspaper_id) + "/original")

        author_match = AUTHOR_RE.match(article.text.splitlines()[0])
        if author_match:
            article.set_property("author", author_match.groupdict()["author"].strip())
            article.text = "\n".join(article.text.splitlines()[1:]).strip()

        return article


if __name__ == "__main__":
    setup_logging()
    TelegraafScraper().run()

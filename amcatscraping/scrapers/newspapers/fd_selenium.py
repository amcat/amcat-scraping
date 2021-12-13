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
import hashlib

import logging
import datetime
import locale
import time
from urllib import parse

from urllib.parse import urljoin

from collections import namedtuple
from typing import Tuple

from selenium.common.exceptions import ElementClickInterceptedException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from amcat.models import Article
from amcatscraping.scraper import SeleniumLoginMixin, SeleniumMixin, DeduplicatingUnitScraper, DateRangeScraper, \
    NotVisible, SkipArticle
from amcatscraping.tools import html2text
from amcatscraping.httpsession import RedirectError
import calendar
import re
from random import randint
from time import sleep

log = logging.getLogger(__name__)

BASE_URL = "https://fd.nl/"
LOGIN_URL = parse.urljoin(BASE_URL, "login")
KRANT_URL = parse.urljoin(BASE_URL, "krant/{year}/{month:02d}/{day:02d}")
FDUnit = namedtuple("FDUnit", ["url", "date", "page"])


def strip_query(url: str) -> str:
    return parse.urljoin(url, parse.urlparse(url).path)


def dutch_strptime(date, pattern):
    loc = locale.getlocale()
    locale.setlocale(locale.LC_ALL, 'nl_NL.UTF-8')
    try:
        return datetime.datetime.strptime(date, pattern)
    finally:
        locale.setlocale(locale.LC_ALL, loc)

class FDScraper(SeleniumLoginMixin, SeleniumMixin, DateRangeScraper, DeduplicatingUnitScraper):
    publisher = "Financieele Dagblad"
    cookies_ok_button = "button#save"
    editions = None
    login_url = "https://fd.nl/krant"
    login_username_field = "input#username"
    login_password_field = "input#password"
    login_error_selector = ".login .modal-content .alert-error"
    allow_missing_login = False

    def click(self, element):
        try:
            element.click()
        except ElementClickInterceptedException:
            self.click(element.find_element_by_xpath(".."))

    def login(self, username, password):
        self.browser.get(self.login_url)
        time.sleep(3)
        iframe = self.wait("#gdpr-consent-notice", timeout=5)
        self.browser.switch_to.frame(iframe)
        self.browser.find_element_by_css_selector("button#save").send_keys(Keys.ENTER)
        self.browser.switch_to.default_content()
        time.sleep(2)
        self.wait("button.profile-button.menu-button").click()
        self.wait("a.fd-button.m").click()
        self.wait(self.login_username_field).send_keys(username)
        self.wait("button.button").click()
        self.wait(self.login_password_field).send_keys(password)
        self.wait("button.button").click()
        time.sleep(3)

        try:
            error = self.wait(self.login_error_selector, timeout=2)
        except (NoSuchElementException, NotVisible):
            # login error not found, good!
            return True
        else:
            logging.error(f"Login failed: {error.text}")
            return False

    def _get_deduplicate_units(self, date: datetime.datetime, edition=None):
        # Select edition
        logging.info(f"Selecting date {date}")
        KRANT_URL = parse.urljoin(BASE_URL, f"krant/{date.year}/{date.month}/{date.day}")
        print(f"KRANT IS {KRANT_URL}")
        self.browser.get(KRANT_URL)
        time.sleep(2)
        if self.browser.current_url != KRANT_URL:
            logging.warning(f"Redirected from {KRANT_URL} to {self.browser.current_url}, probably no paper today, skipping")
            return []

        units = []
        for page in self.browser.find_elements_by_css_selector("section.page"):
            pagenr = int(page.get_attribute("id").replace("page-", ""))
            for art in page.find_elements_by_xpath("./a"):
                url = art.get_attribute("href")
                if url.startswith("https://fd.nl/HFD"):
                    units.append(FDUnit(url, date, pagenr))
        return units


    def get_url_and_date_from_unit(self, unit: FDUnit) -> Tuple[str, datetime.date]:
        return unit.url, unit.date

    def get_deduplicate_key_from_article(self, article: Article) -> str:
        print(f"article {article.url}")
        return article.url

    def get_deduplicate_key_from_unit(self, unit: FDUnit) -> str:
        return unit.url

    def scrape_unit(self, unit: FDUnit) -> Article:
        print(f"article is {unit}")
        sleep(randint(1,10))
        self.browser.get(unit.url)
        try:
            title = self.wait("h1.heading")
            title = title.text
        except NoSuchElementException:
            logging.warning(f"Could not find article {unit}")
            title = " "
        try:
            author = self.wait("span.author")
            author = author.text
        except NoSuchElementException:
            logging.warning(f"Could not find intro in {unit}")
            author = " "
        try:
            intro_ps = self.wait("div.inline-content.article-summary.block", timeout=5)
            intro = intro_ps.text
        except NoSuchElementException:
            logging.warning(f"Could not find intro in {unit}")
            intro = " "
        try:
            body_ps = self.browser.find_elements_by_css_selector("div.body.body-text.serif.xs p")
            body = "\n\n".join(p.text for p in body_ps)
        except NoSuchElementException:
            raise SkipArticle()

        text = intro + body
        return Article(
            title=title,
            url=unit.url,
            author = author,
            text=text,
            pagenr_int=unit.page,
            date=unit.date
        )

    def get_deduplicate_units(self):
        for date in self.dates:
            if self.editions is not None:
                for edition in self.editions:
                    yield from self._get_deduplicate_units(date, edition)
            else:
                yield from self._get_deduplicate_units(date)


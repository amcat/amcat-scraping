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
import time
import datetime
import locale
import time

from urllib.parse import urljoin

from collections import namedtuple
from typing import Tuple

from selenium.common.exceptions import ElementClickInterceptedException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from amcat.models import Article
from amcatscraping.scraper import SeleniumLoginMixin, SeleniumMixin, DeduplicatingUnitScraper, DateRangeScraper, NotVisible
from amcatscraping.tools import html2text

TelegraafUnit = namedtuple("TelegraafUnit", ["url", "date", "section", "title", "text"])


def dutch_strptime(date, pattern):
    loc = locale.getlocale()
    locale.setlocale(locale.LC_ALL, 'nl_NL.UTF-8')
    try:
        return datetime.datetime.strptime(date, pattern)
    finally:
        locale.setlocale(locale.LC_ALL, loc)

class TelegraafScraper(SeleniumLoginMixin, SeleniumMixin, DateRangeScraper, DeduplicatingUnitScraper):
    cookies_ok_button = "form .CookiesOK"
    editions = None
    login_url = "https://digitalpublishing.telegraaf.nl/static/krant/#login"
    login_username_field = "#id_email"
    login_password_field = "#id_password"
    login_error_selector = ".content > .error"
    allow_missing_login = False

    def click(self, element):
        try:
            element.click()
        except ElementClickInterceptedException:
            self.click(element.find_element_by_xpath(".."))

    def login(self, username, password):
        self.browser.get(self.login_url)
        #try:
        #    self.wait(self.cookies_ok_button).click()
        #except NoSuchElementException:
        #    if self.allow_missing_login:
        #        return True
        #    raise

        self.wait(".Header-User__login-link").click()
        self.wait(self.login_username_field).send_keys(username)
        self.wait(self.login_password_field).send_keys(password)
        self.wait(self.login_password_field).send_keys(Keys.ENTER)

        try:
            self.wait(self.login_error_selector, timeout=2)
        except (NoSuchElementException, NotVisible):
            return True
        else:
            return False

    def get_url_and_date_from_unit(self, unit: TelegraafUnit) -> Tuple[str, datetime.date]:
        return unit.url, unit.date

    def get_deduplicate_key_from_article(self, article: Article) -> str:
        return article.url

    def get_deduplicate_key_from_unit(self, unit: TelegraafUnit) -> str:
        return unit.url

    def _get_deduplicate_units(self, date, edition=None):
        self.browser.get("https://digitalpublishing.telegraaf.nl/static/krant/")


        found = False
        for day_container in self.browser.find_elements_by_css_selector(".Day__date-container"):
            paper_date_string = " ".join(day_container.text.split()[1:3] + ["2018"])
            paper_date = dutch_strptime(paper_date_string, "%d %B %Y").date()
            print(paper_date_string, paper_date, date, paper_date==date)
            if date == paper_date:
                self.wait(".Day__button", on=day_container).click()
                found = True
                break 

        if found:
            time.sleep(3)
            self.wait("#nav-list").click()
            time.sleep(3)
            for section_container in self.browser.find_elements_by_css_selector(".article-list-container .section-list-container"):
                section = section_container.find_elements_by_css_selector("h3")[0].text.strip()
                for article_section in section_container.find_elements_by_css_selector("li.article-list-item a"):
                    title = article_section.text.strip()
                    article_section.click()
                    self.browser.switch_to_frame(self.wait("#article-holder iframe"))
                    article_html = self.wait("body").get_property("outerHTML")
                    text = html2text(article_html)
                    self.browser.switch_to_default_content()
                    url = self.browser.current_url

                    yield TelegraafUnit(url, date, section, title, text)

    def get_deduplicate_units(self):
        for date in self.dates:
            if self.editions is not None:
                for edition in self.editions:
                    yield from self._get_deduplicate_units(date, edition)
            else:
                yield from self._get_deduplicate_units(date)

    def scrape_unit(self, unit: TelegraafUnit):
        return Article(
            title=unit.title,
            url=unit.url,
            text=unit.text,
            date=unit.date,
            section=unit.section
        )

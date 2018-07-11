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

from urllib.parse import urljoin

from collections import namedtuple
from typing import Tuple

from selenium.common.exceptions import ElementClickInterceptedException, NoSuchElementException
from selenium.webdriver.common.by import By

from amcat.models import Article
from amcatscraping.scraper import SeleniumLoginMixin, SeleniumMixin, DeduplicatingUnitScraper, DateRangeScraper
from amcatscraping.tools import html2text

EPagesUnit = namedtuple("EPagesUnit", ["url", "date", "title", "page", "screenshot", "text"])


def dutch_strptime(date, pattern):
    loc = locale.getlocale()
    locale.setlocale(locale.LC_ALL, 'nl_NL.UTF-8')
    try:
        return datetime.datetime.strptime(date, pattern)
    finally:
        locale.setlocale(locale.LC_ALL, loc)

class EPagesScraper(SeleniumLoginMixin, SeleniumMixin, DateRangeScraper, DeduplicatingUnitScraper):
    cookies_ok_button = None
    editions = None
    login_url = None
    login_username_field = "#username"
    login_password_field = "#password"
    login_error_selector = ".message.message--error"

    def click(self, element):
        try:
            element.click()
        except ElementClickInterceptedException:
            self.click(element.find_element_by_xpath(".."))

    def login(self, username, password):
        self.browser.get(self.login_url)
        self.wait(self.cookies_ok_button).click()
        return super(EPagesScraper, self).login(username, password)

    def get_url_and_date_from_unit(self, unit: EPagesUnit) -> Tuple[str, datetime.date]:
        return unit.url, unit.date

    def get_deduplicate_key_from_article(self, article: Article) -> str:
        return article.url

    def get_deduplicate_key_from_unit(self, unit: EPagesUnit) -> str:
        return unit.url

    def _get_deduplicate_units(self, date, edition=None):
        # Select edition
        self.browser.get(self.login_url)

        if edition is not None:
            self.click(self.wait('//div[text() = "{}"]'.format(edition), by=By.XPATH))

        # Go to archive and select paper of this date
        self.wait("#goToArchive").click()

        for archive_issue in self.browser.find_elements_by_css_selector("archive-issue"):
            try:
                archive_date = archive_issue.find_element_by_css_selector(".issueDate").text.strip()
            except NoSuchElementException:
                continue
            if not archive_date:
                continue
            if dutch_strptime(archive_date, "%d %B %Y").date() == date:
                archive_issue.click()
                break
        else:
            return

        # Scrape unit
        self.browser.switch_to_frame(self.wait("#issue"))

        seconds_forgone = 0
        start = datetime.datetime.now()
        while seconds_forgone < 30:
            seconds_forgone = (datetime.datetime.now() - start).total_seconds()

            try:
                self.wait("#articleMenuItem").click()
            except ElementClickInterceptedException:
                pass
            else:
                break

        articles = list(self.browser.find_elements_by_css_selector(".articleListItem"))
        for article in articles:
            page = int(article.get_attribute("data-page"))
            refid = article.get_attribute("data-refid")
            url = urljoin(self.browser.current_url + "/", refid)

            def collect_headers(els):
                for el in els:
                    el_text = el.get_property("textContent").strip()
                    if el_text:
                        yield (el, el_text)

            h1s = list(collect_headers(article.find_elements_by_css_selector(".articleListItem > h1")))
            h2s = list(collect_headers(article.find_elements_by_css_selector(".articleListItem > h2")))
            h3s = list(collect_headers(article.find_elements_by_css_selector(".articleListItem > h3")))

            if h1s:
                _, title = h1s.pop(0)
            elif h2s:
                _, title = h2s.pop(0)
            else:
                _, title = h3s.pop(0)

            try:
                content = article.find_element_by_css_selector("div.content").get_property("outerHTML")
            except NoSuchElementException:
                continue

            subtitles = [element.get_property("outerHTML") for element, _ in h1s + h2s + h3s]
            article_html = "".join(subtitles) + content
            text = html2text(article_html)

            #try:
            #    author = article.find_element_by_css_selector(".byline").get_property("textContent").strip()
            #except NoSuchElementException:
            #    pass
            #else:
            #    print(author)

            # Screenshot code:
            # article.click()
            # self.browser.switch_to_frame(self.wait("#articleViewContent > iframe"))
            # screenshot = self.wait("#page article").screenshot_as_base64
            # self.browser.switch_to_default_content()
            # self.browser.switch_to_frame(self.wait("#issue"))
            # self.wait("#articleNavigationBack").click()
            # time.sleep(0.5)
            screenshot = None

            yield EPagesUnit(url, date, title, page, screenshot, text)

    def get_deduplicate_units(self):
        for date in self.dates:
            if self.editions is not None:
                for edition in self.editions:
                    yield from self._get_deduplicate_units(date, edition)
            else:
                yield from self._get_deduplicate_units(date)

    def scrape_unit(self, unit: EPagesUnit):
        return Article(
            title=unit.title,
            url=unit.url,
            text=unit.text,
            pagenr_int=unit.page,
            date=unit.date
        )

class AlgemeenDagbladScraper(EPagesScraper):
    cookies_ok_button = "a.fjs-accept"
    publisher = "Algemeen Dagblad"
    login_url = "http://krant.ad.nl/"
    editions = ["Algemeen Dagblad"]


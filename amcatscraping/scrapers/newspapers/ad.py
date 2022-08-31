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
import re
import time
import datetime
import locale

from urllib.parse import urljoin

from collections import namedtuple
from typing import Tuple
from selenium import webdriver

from selenium.common.exceptions import ElementClickInterceptedException, NoSuchElementException, ElementNotVisibleException
from selenium.webdriver.common.by import By

from amcat.models import Article
from amcatscraping.scraper import SeleniumLoginMixin, SeleniumMixin, DeduplicatingUnitScraper, DateRangeScraper, NotVisible
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
    """
    Note: This does not work in newer Firefox versions, possibly because of DOM shadow roots.
    It is tested with geckodriver-v0.21.0 and firefox_61.0.1.
    To test, you can install an old version of firefox and prepend it to your path
    To run firefox standalone, make sure to
    - create a profile with prefs.js including user_pref("app.update.enabled", false);
    - call firefox with ./firefox --profile /path/to/profile --new-instance
    """
    cookies_ok_button = None
    editions = None
    login_url = None
    login_username_field = "#username"
    login_password_field = "#password"
    login_error_selector = ".message.message--error"
    logout = "paper-button#logout"
    allow_missing_login = True
    BROWSER=None

    def get_browser(self):
        options = webdriver.ChromeOptions()
        options.add_argument("start-maximized")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument("--disable-blink-features")
        options.add_argument("--disable-blink-features=AutomationControlled")

        browser = webdriver.Chrome()
        browser.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        EPagesScraper.BROWSER = browser
        return browser

    def click(self, element):
        try:
            element.click()
        except ElementClickInterceptedException:
            self.click(element.find_element_by_xpath(".."))

    def login(self, username, password):
        self.browser_get(self.login_url)
        time.sleep(1)
        try:
            self.wait(self.login_username_field)
        except NoSuchElementException:
            if self.allow_missing_login:
                return True
            raise
        self.accept_cookie()
        success = super(EPagesScraper, self).login(username, password)
        if success:
            self.accept_cookie2()
        return success

    def accept_cookie(self, timeout=3):
        try:
            logging.info("Waiting for cookie screen")
            self.wait(self.cookies_ok_button, timeout=3).click()
        except (NoSuchElementException, NotVisible):
            logging.info("No cookie screen found, hope it's OK")

    def scroll_if_needed(self, element):
        if not element.is_displayed():
            self.browser.execute_script("arguments[0].scrollIntoView(true)", element)

    def try_click(self, element):
        self.scroll_if_needed(element)
        try:
            element.click()
        except ElementClickInterceptedException:
            self.browser.execute_script("arguments[0].scrollIntoView(true)", element)
            element.click()

    def wait_shadow(self, *args, **kargs):
        stop = time.time() + 10
        while time.time() < stop:
            try:
                return self.shadow.find_element(*args, **kargs)
            except (NoSuchElementException, ElementNotVisibleException):
                time.sleep(1)
        return self.shadow.find_element(*args, **kargs)

    def wait_shadow_click(self, *args, **kargs):
        stop = time.time() + 10
        while True:
            try:
                return self.shadow.find_element(*args, **kargs).click()
            except (NoSuchElementException, ElementNotVisibleException, ElementClickInterceptedException):
                if time.time() > stop:
                    raise
                time.sleep(1)

    def accept_cookie2(self, timeout=5):
        try:
            logging.info("Waiting for second consent screen")
            self.wait_shadow_click("#allowoptions > div > paper-button.paper_green")
        except (NoSuchElementException, NotVisible, ElementNotVisibleException):
            logging.info("Second  consent screen not found, hope it's OK!")

    def get_url_and_date_from_unit(self, unit: EPagesUnit) -> Tuple[str, datetime.date]:
        print(unit.url, unit.date)
        return unit.url, unit.date

    def get_deduplicate_key_from_article(self, article: Article) -> str:
        print(f"article {article.url}")
        return article.url

    def get_deduplicate_key_from_unit(self, unit: EPagesUnit) -> str:
        return unit.url

    def _get_deduplicate_units(self, date: datetime.datetime, edition=None):
        # Select edition
        logging.info(f"Selecting date {date}")
        self.accept_cookie(timeout=1)

        # select the right region/edition
        self.browser_get(self.login_url)
        if edition is not None:
            regions = self.shadow.find_elements("#regionsContainer > paper-button.regionItem")
            for region in regions:
                if region.text == "ALGEMEEN DAGBLAD":
                    region.click()
            self.accept_cookie2()

        # Go to archive and select paper of this date
        button = self.wait_shadow("paper-button.showMoreButton")
        self.try_click(button)

        # make sure right header is not hidden
        header = self.wait_shadow('#rightHeader')
        self.execute_script('arguments[0].removeAttribute("hidden");', header)

        self.choose_date(date)
        self.choose_paper(date)

        # Scrape unit
        self.browser.switch_to.frame(self.shadow.find_element('iframe#issue'))
        self.wait_shadow_click("#articleMenuItem")

        article_list_buttons = self.shadow.find_elements("#articleListSectionsButtons > button")
        article_list_buttons = list(article_list_buttons) or [lambda: None]
        for article_list_button in article_list_buttons:
            if not "selected" in article_list_button.get_attribute("class"):
                article_list_button.click()
            articles = list(self.shadow.find_elements(".articleListItem"))
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

    def choose_paper(self, date):
        # Hij opent nu een soort tweede date picker met de kranten van de gekozen week
        # We zoeken de krant met de goede datum in de archive view
        archive = self.wait_shadow("#archiveView")
        archive.find_element_by_xpath(f".//div[@data-date={date}]").click()
        return

      #  pages = self.wait_shadow_click('div#currentPage')
       # archive_issues = pages.find_elements_by_css_selector("archive-issue")
       # for archive_issue in archive_issues:
        #    archive_date = archive_issue.get_attribute("data-date")
         #   print(archive_date, "->", archive_date and dutch_strptime(archive_date, "%Y-%m-%d").date())
          #  if archive_date and dutch_strptime(archive_date, "%Y-%m-%d").date() == date:
           #     archive_issue.click()
            #    break
        #else:
         #   logging.warning(f"Could not find date {date}")


    def choose_date(self, date):
        self.wait_shadow('archive-calendar-button').click()
        p = self.wait_shadow(".datepicker")
        # find correct year
        while True:
            picked_year = p.find_element_by_css_selector("date-picker-button").get_attribute("navdate")
            m = re.match(r"\w+ \w+ \d+ (\d{4})", picked_year)
            if not m:
                raise Exception(f"Could not parse date {picked_year}")
            picked_year = int(m.group(1))
            if picked_year == date.year:
                break
            p.find_element_by_id("buttonleft").click()
        # find correct month
        p.find_element_by_id(f"month{date.month}").click()
        day_button = p.find_element_by_id(f"day{date.day}")
        if "disabled" in day_button.get_attribute("class"):
            logging.warning(f"No newspaper for {date}, Sunday?")
            return
        day_button.click()
        p.find_element_by_id("chooseButton").click()

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

    def execute_script(self, param, element):
        pass


class AlgemeenDagbladScraper(EPagesScraper):
   # cookies_ok_button = "a.fjs-accept"
    cookies_ok_button = "paper-button#acceptButton"
    #cookies_ok_button = "paper-material"
    publisher = "Algemeen Dagblad"
    login_url = "http://krant.ad.nl/"
    editions = ["Algemeen Dagblad"]

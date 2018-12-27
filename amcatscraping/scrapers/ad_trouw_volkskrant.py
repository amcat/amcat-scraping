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
import json
import time
import datetime
import locale

from urllib.parse import urljoin
from collections import namedtuple

from selenium.common.exceptions import ElementClickInterceptedException, \
    NoSuchElementException, WebDriverException

from amcat.models import Article
from amcatscraping.scraper import SeleniumLoginMixin, SeleniumMixin, \
    DateRangeScraper, Units, UnitScraper
from amcatscraping.tools import html2text, listify

EPagesUnit = namedtuple("EPagesUnit", ["url", "date", "title", "page", "screenshot", "text"])


def dutch_strptime(date, pattern):
    loc = locale.getlocale()
    locale.setlocale(locale.LC_ALL, 'nl_NL.UTF-8')
    try:
        return datetime.datetime.strptime(date, pattern)
    finally:
        locale.setlocale(locale.LC_ALL, loc)

class EPagesScraper(SeleniumLoginMixin, SeleniumMixin, DateRangeScraper, UnitScraper):
    cookies_ok_button = None
    editions = None
    login_url = None
    login_username_field = "#username"
    login_password_field = "#password"
    login_error_selector = ".message.message--error"
    allow_missing_login = True
    do_not_load_images = False

    def click(self, element):
        try:
            element.click()
        except ElementClickInterceptedException:
            self.click(element.find_element_by_xpath(".."))
        except WebDriverException as e:
            if "Other element would receive the click" in str(e):
                self.click(element.find_element_by_xpath(".."))
            raise

    def click_script(self, el):
        return self.browser.execute_script("return arguments[0].click();", el)

    def login(self, username, password):
        self.browser.get(self.login_url)
        try:
            self.wait(self.cookies_ok_button).click()
        except NoSuchElementException:
            if self.allow_missing_login:
                return True
            raise
        return super(EPagesScraper, self).login(username, password)

    def shadow(self, selectors, tries=5):
        *selectors, last_selector = selectors
        selectors = ['querySelector("{}").shadowRoot'.format(s) for s in selectors]
        script = 'return document.{}.querySelector("{}");'.format(".".join(selectors), last_selector)

        n = 0
        while True:
            try:
                return self.browser.execute_script(script)
            except Exception as e:
                if n >= tries:
                    raise
                else:
                    n += 1
                    time.sleep(n)

    def shadow_root(self, element, selector):
        return self.browser.execute_script("return arguments[0].shadowRoot.querySelector(arguments[1]);", element, selector)

    def get_url_from_unit(self, unit: EPagesUnit) -> str:
        return unit.url

    def _get_units(self, date, edition=None):
        # Select edition
        self.browser.get(self.login_url)

        if edition is not None:
            regions = self.shadow(["#main", "#main", "#regionPicker", "#mainContainer"])
            for button in regions.find_elements_by_css_selector("paper-button"):
                name = json.loads(button.get_attribute("data-region"))["name"]
                if name == edition:
                    self.click(button)

        # Go to archive and select paper of this date
        time.sleep(2)
        main = self.shadow(["#main", "#main", "#coverView", "#others"])
        self.click_script(self.wait("paper-button.showMoreButton", on=main))

        time.sleep(2)
        archive = self.shadow(["#main", "#main", "#archiveView", "#currentPage"])
        self.wait("archive-issue", on=archive)

        for archive_issue in archive.find_elements_by_css_selector("archive-issue"):
            issue_date_root = self.shadow_root(archive_issue, ".issueDate")
            if issue_date_root is None:
                continue

            archive_date = issue_date_root.text.strip()
            if not archive_date:
                continue
            if dutch_strptime(archive_date, "%d %B %Y").date() == date:
                self.click(archive_issue)
                break
        else:
            return

        # Scrape unit
        time.sleep(2)
        iframe = self.shadow(["#main", "#main", "issue-view", "#issue"])
        self.browser.switch_to_frame(iframe)
        self.click_script(self.wait("#articleMenuItem"))

        time.sleep(2)

        article_list_buttons = self.browser.find_elements_by_css_selector("#articleListSectionsButtons > button")
        article_list_buttons = list(article_list_buttons) or [None]

        for article_list_button in article_list_buttons:
            if article_list_button is not None:
                self.click_script(article_list_button)
            time.sleep(2)
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

    @listify(wrapper=Units)
    def get_units(self):
        for date in self.dates:
            if self.editions is not None:
                for edition in self.editions:
                    yield from self._get_units(date, edition)
            else:
                yield from self._get_units(date)

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


class VolkskrantScraper(EPagesScraper):
    cookies_ok_button = ".button--accept"
    login_url = "http://krant.volkskrant.nl/"
    publisher = "Volkskrant"
    allow_missing_login = True


class TrouwScraper(EPagesScraper):
    cookies_ok_button = ".btn.btn--accept"
    login_url = "http://krant.trouw.nl/"
    publisher = "Trouw"

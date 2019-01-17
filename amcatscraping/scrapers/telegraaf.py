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
import hashlib
import datetime
import locale
import time
from urllib import parse


from collections import namedtuple

from selenium.common.exceptions import ElementClickInterceptedException, NoSuchElementException
from selenium.webdriver.common.keys import Keys

from amcat.models import Article
from amcatscraping.scraper import SeleniumLoginMixin, SeleniumMixin, \
    DateRangeScraper, NotVisible, Units, UnitScraper
from amcatscraping.tools import html2text

TelegraafUnit = namedtuple("TelegraafUnit", ["article_element", "url", "date", "page_range"])


def dutch_strptime(date, pattern):
    loc = locale.getlocale()
    locale.setlocale(locale.LC_ALL, 'nl_NL.UTF-8')
    try:
        return datetime.datetime.strptime(date, pattern)
    finally:
        locale.setlocale(locale.LC_ALL, loc)

class TelegraafScraper(SeleniumLoginMixin, SeleniumMixin, DateRangeScraper, UnitScraper):
    publisher = "De Telegraaf"
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

    def click_script(self, el):
        return self.browser.execute_script("return arguments[0].click();", el)

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

        time.sleep(3)

        try:
            self.wait(self.login_error_selector, timeout=2)
        except (NoSuchElementException, NotVisible):
            return True
        else:
            return False

    def get_url_from_unit(self, unit: TelegraafUnit) -> str:
        return unit.url

    def next_button(self):
        return self.wait("#next-page-button", visible=False)

    def _get_units(self, date, edition=None):
        self.browser.get("https://digitalpublishing.telegraaf.nl/static/krant/")

        found = False
        for day_container in self.browser.find_elements_by_css_selector(".Day__date-container"):
            paper_date_string = " ".join(day_container.text.split()[1:3] + [str(datetime.date.today().year)])
            paper_date = dutch_strptime(paper_date_string, "%d %B %Y").date()
            if date == paper_date:
                self.wait(".Day__button", on=day_container).click()
                found = True
                break 

        if found:
            self.wait("#next-page-button")
            while self.next_button().is_displayed():
                units = []
                for article in self.browser.find_elements_by_css_selector(".pages-swiper-slide-active .article-layer"):
                    id = article.get_property("id")
                    url = self.browser.current_url
                    (scheme, netloc, path, params, query, fragment) = parse.urlparse(url)
                    page_range = fragment.split("/")[-1]
                    query += "&hash=" + hashlib.sha256(str((id, date, page_range)).encode()).hexdigest()[:20]
                    url = parse.urlunparse((scheme, netloc, path, params, query, fragment))

                    # HACK: we cannot use ? or * in url due to query DSL
                    # limitations.. unfortunately, Telegraaf uses them
                    url = url.replace("?", "_")

                    units.append(TelegraafUnit(article, url, date, page_range))

                yield Units(units)

                self.next_button().click()
                time.sleep(5)

    def get_units(self):
        for date in self.dates:
            if self.editions is not None:
                for edition in self.editions:
                    yield from self._get_units(date, edition)
            else:
                yield from self._get_units(date)

    def scrape_unit(self, unit: TelegraafUnit):
        article, url, date, page_range = unit

        self.click_script(article)
        time.sleep(1.5)

        try:
            self.browser.switch_to_frame(self.wait("iframe.article-contents", timeout=10))
        except NotVisible:
            print("Warning: article skipped because frame was not visible")
            return None

        article_html = self.wait("body").get_property("outerHTML")
        text = html2text(article_html)

        try:
            title = self.wait("body > .head", timeout=2).text.strip()
        except:
            return None
        finally:
            self.browser.switch_to_default_content()

            # Close modal
            self.wait(".article-modal-default-button").click()

            time.sleep(1.5)

        return Article(
            title=title,
            url=url,
            text=text,
            date=date,
            pagerange=page_range
        )

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
import logging

from urllib.parse import urljoin
from collections import namedtuple

from selenium.common.exceptions import ElementClickInterceptedException, \
    NoSuchElementException, WebDriverException, StaleElementReferenceException
from selenium.webdriver.common.keys import Keys

from amcat.models import Article
from amcatscraping.scraper import SeleniumLoginMixin, SeleniumMixin, \
    DateRangeScraper, Units, UnitScraper
from amcatscraping.tools import html2text, listify

EPagesUnit = namedtuple("EPagesUnit", ["url", "date", "title", "page", "text"])

log = logging.getLogger(__name__)

def dutch_strptime(date, pattern):
    loc = locale.getlocale()
    locale.setlocale(locale.LC_ALL, 'nl_NL.UTF-8')
    try:
        return datetime.datetime.strptime(date, pattern)
    finally:
        locale.setlocale(locale.LC_ALL, loc)


def get_article_id_from_url(url):
    url = list(url.split("/"))
    return "/".join(url[url.index("articles") + 1:])


def get_url(base_url, ref_id):
    return urljoin(base_url, str(ref_id))


def get_page_from_url(url):
    return int(get_article_id_from_url(url).split("/")[1])


def collect_headers(els):
    for el in els:
        el_text = el.get_property("textContent").strip()
        if el_text:
            yield (el, el_text)


def parse_article(article, date, page, url):
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
        return None

    subtitles = [element.get_property("outerHTML") for element, _ in h1s + h2s + h3s]
    article_html = "".join(subtitles) + content
    text = html2text(article_html)

    return EPagesUnit(url, date, title, page, text)


class EPagesScraper(SeleniumLoginMixin, SeleniumMixin, UnitScraper, DateRangeScraper):
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

    def shadow_root(self, element, selector):
        return self.browser.execute_script("return arguments[0].shadowRoot.querySelector(arguments[1]);", element,
                                           selector)

    def get_url_from_unit(self, unit: EPagesUnit) -> str:
        return unit.url

    def _get_units(self, date, edition=None):
        # Select edition
        self.browser.get(self.login_url)

        if edition is not None:
            regions = self.wait_shadow("#main >>> #main >>> #regionPicker >>> #mainContainer")
            for button in regions.find_elements_by_css_selector("paper-button"):
                name = json.loads(button.get_attribute("data-region"))["name"]
                if name == edition:
                    self.click(button)

        # Go to archive and select paper of this date
        time.sleep(2)
        self.click_script(self.wait_shadow("#main >>> #main >>> #coverView >>> #others paper-button.showMoreButton"))

        time.sleep(2)
        archive = self.wait_shadow("#main >>> #main >>> #archiveView >>> #currentPage")
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
        time.sleep(10)
        iframe = self.wait_shadow("#main >>> #main >>> issue-view >>> #issue")
        self.browser.switch_to_frame(iframe)
        self.click_script(self.wait("#articleMenuItem"))

        time.sleep(5)

        article_list_buttons = self.browser.find_elements_by_css_selector("#articleListSectionsButtons > button")
        article_list_buttons = list(article_list_buttons) or [None]

        base_url = self.browser.current_url + "/"
        seen_article_ids = set()

        # Get articles from article list
        for article_list_button in article_list_buttons:
            if article_list_button is not None:
                self.click_script(article_list_button)

            time.sleep(5)
            articles = list(self.browser.find_elements_by_css_selector(".articleListItem"))
            scraped_articles = list()
            for article in articles:
                page = int(article.get_attribute("data-page"))
                refid = article.get_attribute("data-refid")
                url = get_url(base_url, refid)
                seen_article_ids.add(get_article_id_from_url(url))
                article = parse_article(article, date, page, url)
                if article is not None:
                    scraped_articles.append(article)
            self.set_flush_flag()
            yield Units(scraped_articles)

        # Article list skips articles sometimes, so we need to flick through the pages manually too..
        self.wait("html").send_keys(Keys.ESCAPE)

        time.sleep(3)

        scraped_articles = list()
        while True:
            book_scroller = self.wait("#bookScroller")

            for path in book_scroller.find_elements_by_tag_name("path"):
                try:
                    article_id = path.get_attribute("data-article")
                except Exception as e:
                    print("Skipping article: " + str(e))
                    continue
                if article_id is None:
                    continue
                if article_id in seen_article_ids:
                    continue

                seen_article_ids.add(article_id)
                url = get_url(base_url, article_id)
                page = get_page_from_url(url)

                scraped_articles.append(
                    EPagesUnit(url=url, date=date, title=None, page=page, text=None)
                )

            time.sleep(1.5)

            try:
                self.click_script(self.wait("#forwardArrows #nextPageArrow", timeout=2))
            except:
                break

        yield Units(scraped_articles)

    def get_units(self):
        for date in self.dates:
            if self.editions is not None:
                for edition in self.editions:
                    yield from self._get_units(date, edition)
            else:
                yield from self._get_units(date)

    def scrape_unit(self, unit: EPagesUnit):
        if unit.text is None and unit.title is None:
            self.browser.get(unit.url)

            # This is an article not scraped at the overview page. We need to scrape it separately.
            time.sleep(10)
            iframe = self.wait_shadow("#main >>> #main >>> issue-view >>> #issue")
            self.browser.switch_to_frame(iframe)

            article_iframe = self.wait("#articleViewContent > iframe")
            self.browser.switch_to_frame(article_iframe)

            title = self.wait("article h1").text.strip()
            text = html2text(self.wait("article").get_property("outerHTML"))

            unit = EPagesUnit(unit.url, unit.date, title, unit.page, text)

        title = unit.title.strip()
        if not title:
            title = "[NO TITLE]"

        return Article(
            title=title,
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

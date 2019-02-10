###########################################################################
# (C) Vrije Universiteit, Amsterdam (the Netherlands)                     #
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
import http.cookies
import locale
import logging
import re
import dateutil
import feedparser
import iso8601
import lxml
import lxml.html
import time

from selenium.common.exceptions import NoSuchElementException
from urllib.parse import urljoin, urlparse, unquote

from amcat.models import Article
from amcatscraping.scraper import SeleniumMixin, \
    SeleniumLoginMixin, UnitScraper, Units
from amcatscraping.tools import html2text, listify, strip_query

log = logging.getLogger(__name__)

REMOVE_TAGS = {"img"}


def get_publisher(url):
    hostname = urlparse(url).hostname
    publisher = ".".join(hostname.split(".")[-2:])
    return publisher


def dutch_strptime(date, pattern):
    loc = locale.getlocale()
    locale.setlocale(locale.LC_ALL, 'nl_NL.UTF-8')
    try:
        return datetime.datetime.strptime(date, pattern)
    finally:
        locale.setlocale(locale.LC_ALL, loc)


class GenericScraper(SeleniumMixin, UnitScraper):
    cookie_button = None
    index_url = None
    article_url_re = None
    article_url_cssselector = "a"
    has_ccm_cookies = False
    cookies = None

    # Cookies know to prevent banners
    default_cookies = {
        "nl_cookiewall_version": "4",
        "nmt_closed_cookiebar": "1",
        "accept_cookies": "1",
        "cookieconsent_dismissed": "yes"
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.cookies = self.options.get("cookies", self.cookies)
        self.index_url = self.options.get("index_url", self.index_url)
        self.article_url_re = re.compile(self.options.get("article_url", self.article_url_re))
        self.publisher = self.options.get("publisher", get_publisher(self.index_url))
        self.now = datetime.datetime.now()

    def setup_session(self):
        super().setup_session()

        self.browser.get(self.index_url)
        self.wait("html")

        if self.cookies:
            for name, morsel in http.cookies.BaseCookie(self.cookies).items():
                self.browser.add_cookie({'name': name, 'value': morsel.value})

        for name, value in self.default_cookies.items():
            self.browser.add_cookie({'name': name, 'value': value})

        if self.cookie_button:
            self.wait(self.cookie_button).click()

        if self.has_ccm_cookies:
            self.wait(".ccm_col_content_cookieitem-radiowrap label")
            for label in self.browser.find_elements_by_css_selector(
                    ".ccm_col_content_cookieitem-radiowrap > label:first-child"):
                label.click()
                time.sleep(0.3)
            time.sleep(0.3)
            self.wait("button.ccm_btn").click()
            time.sleep(0.3)

    def get_raw_html(self, wait_for="html", timeout=60):
        self.wait(wait_for, timeout=timeout)
        return self.wait("html").get_attribute("outerHTML")

    def get_date(self, doc):
        raise NotImplementedError("get_timestamp() not implemented")

    def get_html(self, wait_for="html", timeout=60):
        return lxml.html.fromstring(self.get_raw_html(wait_for=wait_for, timeout=timeout),
                                    base_url=self.browser.current_url)

    def get_url_from_unit(self, unit: str):
        return unit

    @listify(wrapper=Units)
    def get_units(self):
        self.browser.get(self.index_url)

        index = self.get_html()

        units = index.cssselect(self.article_url_cssselector)

        seen = set()
        for a in units:
            absolute_url = urljoin(self.index_url, a.get("href"))
            if self.article_url_re.search(absolute_url):
                if absolute_url not in seen:
                    yield absolute_url
                    seen.add(absolute_url)
            else:
                print("Ignoring: {}".format(absolute_url))

    def scrape_unit(self, url):
        self.browser.get(url)

        if self.__class__.get_date is not GenericScraper.get_date:
            doc = self.get_html()

            try:
                date = self.get_date(doc)
            except NotImplementedError:
                date = self.now
            except Exception as e:
                log.warning("get_date() failed for {} with: {}".format(url, e))
                date = self.now
        else:
            date = self.now

        self.browser.execute_script("javascript:(function(){readConvertLinksToFootnotes=false;readStyle='style-newspaper';readSize='size-medium';readMargin='margin-wide';_readability_script=document.createElement('script');_readability_script.type='text/javascript';_readability_script.src='https://hmbastiaan.nl/martijn/downloads/readability.js?x='+(Math.random());document.documentElement.appendChild(_readability_script);_readability_css=document.createElement('link');_readability_css.rel='stylesheet';_readability_css.href='https://hmbastiaan.nl/martijn/downloads/readability.css?1';_readability_css.type='text/css';_readability_css.media='all';document.documentElement.appendChild(_readability_css);_readability_print_css=document.createElement('link');_readability_print_css.rel='stylesheet';_readability_print_css.href='https://hmbastiaan.nl/martijn/downloads/readability-print.css';_readability_print_css.media='print';_readability_print_css.type='text/css';document.getElementsByTagName('head')[0].appendChild(_readability_print_css);})();")

        try:
            doc = self.get_html(wait_for="#readability-page-1", timeout=20)
        except NoSuchElementException:
            # Readability couldn't parse this document
            return Article(date=date, title=self.browser.title, url=url,
                           text="GENERICPARSEERROR: COULD NOT PARSE DOCUMENT")

        for tag in REMOVE_TAGS:
            for element in doc.cssselect(tag):
                element.getparent().remove(element)

        try:
            article = doc.cssselect("#readability-content")[0]
        except NoSuchElementException:
            log.exception("Failed to readability: {}".format(url))
            return None

        article_html = lxml.html.tostring(article).decode()

        title = doc.cssselect("#readInner > h1")[0].text_content().strip()
        text = html2text(article_html)

        article = Article(date=date, title=title, text=text, url=url)

        return article


class GenericRSSScraper(GenericScraper):
    article_url_re = ".+"
    rss_url = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.url_date_cache = {}

    @listify(wrapper=Units)
    def get_units(self):
        feed = feedparser.parse(self.rss_url)

        for entry in feed['entries']:
            url = entry["links"][0]["href"]
            date = dateutil.parser.parse(entry['published'])
            self.url_date_cache[urlparse(url)[1:3]] = date
            yield url

    def get_date(self, doc):
        return self.url_date_cache[urlparse(unquote(doc.base_url))[1:3]]


class Nu(GenericScraper):
    index_url = "https://www.nu.nl"
    article_url_re = "/[\w-]+/[0-9]+/.+.html"
    cookie_button = "#sanoma-consent-accept-button"
    blocked = [
        "/advertorial/",
        "/voetbal/",
        "/video/",
    ]

    @listify(wrapper=Units)
    def get_units(self):
        for url in map(strip_query, super().get_units()):
            if any (b in url for b in self.blocked):
                continue
            yield url

    def get_date(self, doc):
        date = doc.cssselect(".pubdate.large")[0].text_content().strip()
        try:
            date = datetime.datetime.strptime(date, '%d-%m-%y %H:%M')
        except:
            date = dutch_strptime(date, "%d %B %Y %H:%M")
        return date

    def scrape_unit(self, url):
        unit = super().scrape_unit(url)

        for b in self.blocked:
            if b in self.browser.current_url:
                unit.title = "[FILTERED]"
                unit.text = "[FILTERED]"
                break

        return unit


class AD(SeleniumLoginMixin, GenericScraper):
    login_url = "https://www.ad.nl/inloggen"
    login_username_field = "#email"
    login_password_field = "#password"
    login_error_selector = ".message-block--error"

    index_url = "https://www.ad.nl/"
    article_url_re = "/[\w-]+/[\w-]+~[a-z0-9]+/"
    article_url_cssselector = ".articles-list.fjs-articles-list a"

    def get_date(self, doc):
        date = doc.cssselect(".article__meta time")[0].text_content().strip()
        date = datetime.datetime.strptime(date, '%d-%m-%y, %H:%M')
        return date


class Volkskrant(SeleniumLoginMixin, GenericScraper):
    login_url = "https://www.volkskrant.nl/login"
    login_username_field = "#email"
    login_password_field = "#password"
    login_error_selector = ".form__error"

    cookie_button = ".modal .button--accept"
    index_url = "https://www.volkskrant.nl/"
    article_url_re = "/[\w-]+/[\w-]+~[a-z0-9]+/"

    def get_date(self, doc):
        date = doc.cssselect("time.artstyle__byline__datetime")[0].get("datetime")
        return iso8601.iso8601.parse_date(date, default_timezone=None)

    def login(self, username, password):
        super().login(username, password)
        self.wait("article")
        return True


class Trouw(SeleniumLoginMixin, GenericScraper):
    login_url = "https://www.trouw.nl/account/login?url=/"
    login_username_field = "#loginform_loginId"
    login_password_field = "#loginform_password"
    login_error_selector = ".form__error-description.fjs-login-error"

    cookie_button = ".btn.btn--accept"
    index_url = "https://www.trouw.nl/"
    article_url_re = "/[\w-]+/[\w-]+~[a-z0-9]+/"

    def get_date(self, doc):
        date = self.browser.execute_script('return window.APP.article["publicationDateAndTime"]')
        return dutch_strptime(date, "%H:%M, %d %B %Y")


class FD(SeleniumLoginMixin, GenericScraper):
    login_url = "https://fd.nl/login"
    login_username_field = 'input[name="username"]'
    login_password_field = 'input[name="password"]'
    login_error_selector = "form .errors li"
    cookie_button = "#cookieconsent1"

    index_url = "https://fd.nl/laatste-nieuws"
    article_url_cssselector = "article > a"
    article_url_re = ".+"

    def get_date(self, doc):
        date = self.browser.execute_script("return siteData.publicationTime;")
        return datetime.datetime.strptime(date, "%Y/%m/%d %H:%M:%S")


class NRCBinnenland(SeleniumLoginMixin, GenericScraper):
    login_url = "https://nrc.nl/login"
    login_username_field = 'input[name="username"]'
    login_password_field = 'input[name="password"]'
    login_error_selector = ".feedback.fout"

    index_url = "https://www.nrc.nl/sectie/binnenland/"
    article_url_re = "/nieuws/\d{4}/\d{2}/\d{2}/[\w-]+"

    def get_html(self, *args, **kwargs):
        doc = super().get_html(*args, **kwargs)
        for elem in doc.cssselect(".block__sidebar"):
            elem.getparent().remove(elem)
        return doc

    def get_date(self, doc):
        date = doc.cssselect(".article__byline__text.prettydate")[0].get("datetime")
        return iso8601.iso8601.parse_date(date, default_timezone=None)


class Telegraaf(SeleniumLoginMixin, GenericScraper):
    login_url = "https://accounts.tnet.nl/inloggen/"
    login_username_field = 'input[name="email"]'
    login_password_field = 'input[name="password"]'
    login_error_selector = "form .error"

    index_url = "https://www.telegraaf.nl/"
    article_url_re = "/nieuws/\d+/"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        section = self.options.get("section")
        if section:
            self.index_url += "nieuws/{}/".format(section)

    def login(self, username, password):
        self.browser.get(self.index_url)
        self.wait(".CookiesOK").click()
        return super().login(username, password)


class NOS(GenericScraper):
    index_url = "https://www.nos.nl/"
    article_url_re = "/artikel/"
    has_ccm_cookies = True

    @listify(wrapper=Units)
    def get_units(self):
        sections = self.options.get("sections", "").strip()
        if not sections:
            return super(NOS, self).get_units()

        for section in map(str.strip, sections.split(",")):
            self.index_url = "https://www.nos.nl/nieuws/{}/".format(section)
            yield from super(NOS, self).get_units()

    def get_date(self, doc):
        date = doc.cssselect("article .meta time")[0].get("datetime")
        return iso8601.iso8601.parse_date(date, default_timezone=None)


class RTLNieuws(GenericScraper):
    index_url = "https://www.rtlnieuws.nl/"
    article_url_re = "/artikel/"

    @listify(wrapper=Units)
    def get_units(self):
        sections = self.options.get("sections", "").strip()
        if not sections:
            return super().get_units()

        for section in map(str.strip, sections.split(",")):
            self.index_url = "https://www.rtlnieuws.nl/{}".format(section)
            yield from super().get_units()

    def get_date(self, doc):
        date = doc.cssselect("article .time-created")[0].text_content().strip()
        return dutch_strptime(date, "%d %B %Y %H:%M")

    def setup_session(self):
        super().setup_session()
        self.browser.get(self.index_url)
        self.wait(".accept-button").click()


class EenVandaag(GenericScraper):
    index_url = "https://eenvandaag.avrotros.nl/"
    article_url_re = "/item/"
    has_ccm_cookies = True

    def get_date(self, doc):
        date = doc.cssselect('meta[itemProp="datePublished"]')[0].get("content")
        date = datetime.datetime.strptime(date, '%d-%m-%Y')
        return date


class SocialeVraagstukken(GenericScraper):
    index_url = "https://www.socialevraagstukken.nl/"
    article_url_cssselector = "article h2 a"
    article_url_re = ".+"

    def get_date(self, doc):
        date = doc.cssselect("time.published")[0].get("datetime")
        return iso8601.iso8601.parse_date(date, default_timezone=None)


class Zembla(GenericScraper):
    index_url = "https://zembla.bnnvara.nl/nieuws"
    article_url_re = "/nieuws/[\w-]+$"
    has_ccm_cookies = True

    def get_date(self, doc):
        date = doc.cssselect("time.date")[0].get("datetime")
        return iso8601.iso8601.parse_date(date, default_timezone=None)


class DeMonitor(GenericScraper):
    index_url = "https://demonitor.kro-ncrv.nl"
    article_url_re = "/artikelen/[\w-]+"
    has_ccm_cookies = True

    def get_date(self, doc):
        date = doc.cssselect(".dm-article-show-header-content div > span")[0].text_content().strip()
        return dutch_strptime(date, "%A %d %B %Y")


class Kassa(GenericScraper):
    has_ccm_cookies = True
    index_url = "https://kassa.bnnvara.nl/nieuws"
    article_url_re = "/nieuws/[\w-]+"

    def get_date(self, doc):
        date = doc.cssselect("article .meta time")[0].text_content().strip()
        return dutch_strptime(date, "%A %d %B %Y")


class PW(GenericScraper):
    index_url = "https://www.pw.nl/nieuws/alle-nieuws"
    article_url_re = "/nieuws/\d{4}/[\w-]+"

    def get_date(self, doc):
        date = doc.cssselect(".documentModified")[0].text_content().strip()
        date = datetime.datetime.strptime(date, '%d-%m-%Y')
        return date


class Radar(GenericScraper):
    has_ccm_cookies = True
    index_url = "https://radar.avrotros.nl/nieuws/"
    article_url_re = "/nieuws/item/[\w-]+"

    def get_date(self, doc):
        date = doc.cssselect("article time")[0].text_content().strip()
        date = datetime.datetime.strptime(date, '%d-%m-%Y')
        return date


class BinnenlandsBestuur(GenericRSSScraper):
    index_url = "https://www.binnenlandsbestuur.nl/"
    rss_url = "https://www.binnenlandsbestuur.nl/rss/default.lynkx?category=147960"


class AMWeb(GenericRSSScraper):
    rss_url = "http://www.amweb.nl/rss_feeds/all.rss"
    index_url = "http://www.amweb.nl/"
    cookie_button = ".general-cta-btn"


class Skipr(GenericRSSScraper):
    index_url = "https://www.skipr.nl/"
    rss_url = "https://www.skipr.nl/actueel/rss.xml"


class ZorgwelzijnNonPremium(GenericScraper):
    index_url = "https://www.zorgwelzijn.nl/nieuws-zorg-welzijn/"
    article_url_cssselector = ".td_module_106:not(.premium-content-slogan) .entry-title a"
    article_url_re = ".+"

    def get_date(self, doc):
        date = doc.cssselect('meta[property="article:published_time"]')[0].get("content")
        return dateutil.parser.parse(date)


class ZorgvisieNonPremium(ZorgwelzijnNonPremium):
    index_url = "https://www.zorgvisie.nl/nieuws/"


class MedischContact(GenericScraper):
    index_url = "https://www.medischcontact.nl/nieuws/laatste-nieuws.htm"
    article_url_re = "/nieuws/laatste-nieuws/artikel/[\w-]+"
    cookie_button = "a.cc-popup-compliance-accept.cc-akkord"

    def get_date(self, doc):
        date = doc.cssselect('meta[name="pubdate"]')[0].get("content")
        return dateutil.parser.parse(date)

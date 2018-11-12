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
import time

from urllib.parse import urljoin, urlparse

import dateutil
import feedparser
import iso8601
import lxml
import lxml.html

from amcat.models import Article
from amcatscraping.scraper import DeduplicatingUnitScraper, SeleniumMixin, SeleniumLoginMixin
from amcatscraping.tools import html2text

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
   
class GenericScraper(SeleniumMixin, DeduplicatingUnitScraper):
    index_url = None
    article_url_re = None
    article_url_cssselector = "a"
    cookies = None

    # Cookies know to prevent banners
    default_cookies = {
        "Cookie_Category_Advertising" : "false",
        "Cookie_Category_Analytics" : "false",
        "Cookie_Category_Miscellaneous" : "false",
        "Cookie_Category_Necessary" : "true",
        "Cookie_Category_Recommendations": "false",
        "Cookie_Category_Social": "false",
        "Cookie_Consent": "false",
        "nl_cookiewall_version": "4",
        "cookieconsent": "true",
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

        if self.cookies:
            for name, morsel in http.cookies.BaseCookie(self.cookies).items():
                self.browser.add_cookie({'name': name, 'value': morsel.value})

        for name, value in self.default_cookies.items():
            self.browser.add_cookie({'name': name, 'value': value})

    def get_raw_html(self, url, wait_for="html"):
        self.browser.get(url)
        self.wait(wait_for)
        return self.wait("html").get_attribute("outerHTML")

    def get_date(self, doc):
        raise NotImplementedError("get_timestamp() not implemented")

    def get_html(self, url, wait_for="html"):
        return lxml.html.fromstring(self.get_raw_html(url, wait_for=wait_for), base_url=url)

    def get_deduplicate_key_from_unit(self, unit) -> str:
        return unit

    def get_deduplicate_key_from_article(self, article: Article) -> str:
        return article.url

    def get_deduplicate_units(self):
        index = self.get_html(self.index_url)

        units = index.cssselect(self.article_url_cssselector)
        n_units = len(units)

        for i, a in enumerate(units):
            absolute_url = urljoin(self.index_url, a.get("href"))
            if self.article_url_re.search(absolute_url):
                print("{}/{}: {}".format(i, n_units, absolute_url))
                yield absolute_url

    def scrape_unit(self, url):
        reader_url = "about:reader?url={}".format(url)
        doc = self.get_html(reader_url, wait_for="div.content p")

        for tag in REMOVE_TAGS:
            for element in doc.cssselect(tag):
                element.getparent().remove(element)

        article = doc.cssselect("div.content")[0]
        article_html = lxml.html.tostring(article).decode()

        title = doc.cssselect("h1.reader-title")[0].text_content().strip()
        text = html2text(article_html)

        if self.__class__.get_date is not GenericScraper.get_date:
            # Get contents of un-firefox-read-ed article
            self.wait(".reader-toolbar .close-button").click()
            time.sleep(0.3)
            doc_html = self.wait("html").get_attribute("outerHTML")
            doc = lxml.html.fromstring(doc_html, base_url=url)

            try:
                date = self.get_date(doc)
            except NotImplementedError:
                date = self.now
            except Exception as e:
                log.warning("get_date() failed for {} with: {}".format(url, e))
                date = self.now
        else:
            date = self.now

        article = Article(date=date, title=title, text=text, url=url)

        return article

class GenericRSSScraper(GenericScraper):
    article_url_re = ".+"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.url_date_cache = {}

    def get_deduplicate_units(self):
        feed = feedparser.parse(self.index_url)

        for entry in feed['entries']:
            url = entry["links"][0]["href"]
            date = dateutil.parser.parse(entry['published'])
            self.url_date_cache[url] = date
            yield url

    def get_date(self, doc):
        return self.url_date_cache[doc.base_url]



class Nu(GenericScraper):
    index_url = "https://www.nu.nl"
    article_url_re = "/[\w-]+/[0-9]+/.+.html"

    def get_date(self, doc):
        date = doc.cssselect(".footer .published .small")[0].text_content().strip()
        date = datetime.datetime.strptime(date, '%d-%m-%y %H:%M')
        return date
 
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

    index_url = "https://www.trouw.nl/"
    article_url_re = "/[\w-]+/[\w-]+~[a-z0-9]+/"

    def get_date(self, doc):
        date = self.browser.execute_script('return window.APP.article["publicationDateAndTime"]')
        return dutch_strptime(date, "%H:%M, %-d %B %Y")

class FD(SeleniumLoginMixin, GenericScraper):
    login_url = "https://fd.nl/login"
    login_username_field = 'input[name="username"]'
    login_password_field = 'input[name="password"]'
    login_error_selector = "form .errors li"

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
        date = doc.cssselect("header .date time")[0].get("datetime")
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        section = self.options.get("section")
        if section:
            self.index_url += "nieuws/{}/".format(section)

    def get_date(self, doc):
        date = doc.cssselect("article .meta time")[0].get("datetime")
        return iso8601.iso8601.parse_date(date, default_timezone=None)

class RTLNieuws(GenericScraper):
    index_url = "https://www.rtlnieuws.nl/"
    article_url_cssselector = "h1.article__title a"
    article_url_re = ".+"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        section = self.options.get("section")
        if section:
            self.index_url += section
            self.article_url_re = re.compile("/{}/[\w-]+".format(section))

    def get_date(self, doc):
        date = doc.cssselect("article .timer")[0].text_content().strip()
        return dutch_strptime(date, "%d %B %Y %H:%M")

    def setup_session(self):
        super().setup_session()
        self.browser.get(self.index_url)
        self.wait(".accept-button").click()

class EenVandaag(GenericScraper):
    index_url = "https://eenvandaag.avrotros.nl/"
    article_url_re = "/item/"

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
    article_url_re = "/nieuws/[\w-]+"

    def get_date(self, doc):
        date = doc.cssselect("time.date")[0].get("datetime")
        return iso8601.iso8601.parse_date(date, default_timezone=None)

class DeMonitor(GenericScraper):
    index_url = "https://demonitor.kro-ncrv.nl"
    article_url_re = "/artikelen/[\w-]+"

    def get_date(self, doc):
        date = doc.cssselect(".dm-article-show-header-content div > span")[0].text_content().strip()
        return dutch_strptime(date, "%A %d %B %Y")

class Kassa(GenericScraper):
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
    index_url = "https://radar.avrotros.nl/nieuws/"
    article_url_re = "/nieuws/detail/[\w-]+"

    def get_date(self, doc):
        date = doc.cssselect("article time")[0].get("datetime")
        return iso8601.iso8601.parse_date(date, default_timezone=None)

class BinnenlandsBestuur(GenericRSSScraper):
    index_url = "https://www.binnenlandsbestuur.nl/rss/default.lynkx?category=147960"

class AMWeb(GenericRSSScraper):
    index_url = "http://www.amweb.nl/rss_feeds/all.rss"

class Skipr(GenericRSSScraper):
    index_url = "https://www.skipr.nl/actueel/rss.xml"

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

    def get_date(self, doc):
        date = doc.cssselect('meta[name="pubdate"]')[0].get("content")
        return dateutil.parser.parse(date)


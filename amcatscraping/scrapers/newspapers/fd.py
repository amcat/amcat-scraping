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

from html2text import html2text
import lxml.html

from urlparse import urljoin, urlparse, parse_qs
import re

from amcatscraping.article import Article
from amcatscraping.tools import setup_logging, parse_form
from amcatscraping.scraper import (LoginMixin, PropertyCheckMixin,
                                   UnitScraper, DateRangeScraper)


log = logging.getLogger(__name__)

# URLS
LOGIN_URL = "https://fd.nl/login"
BASE_URL = "http://digikrant.fd.nl/"
ARCHIVE_URL = "http://digikrant-archief.fd.nl/"
INIT_URL = BASE_URL + "go?url=digikrant-archief.fd.nl/vw/edition.do?dp=FD%26altd=true%26date=%Y%m%d%26ed=00"
FRONTPAGE_URL = ARCHIVE_URL + "vw/edition.do?dp=FD&altd=true&date=%Y%m%d&ed=00&rxst={rxst}"
PAGE_URL = ARCHIVE_URL + "vw/page.do?id={id}&pagedisplay=true&date=%Y%m%d"
ARTICLE_URL = ARCHIVE_URL + "vw/txt.do?id={id}"
RXST_URL = BASE_URL + "go?url=digikrant-archief.fd.nl/vw/edition.do?forward=true%26dp=FD%26altd=true%26date=20140401%26uid=2711728%26oid=%26abo=DIGIPLUS%26ed=00"

# REs
ARTICLE_ID_RE = re.compile("FD-[0-9-]+")
NO_PAPER_AVAILABLE = re.compile(
    "Er is geen uitgave van ([0-9a-zA-Z ]+) aanwezig."
)


class FinancieelDagbladScraper(LoginMixin, PropertyCheckMixin, UnitScraper, DateRangeScraper):
    def __init__(self, *args, **kwargs):
        super(FinancieelDagbladScraper, self).__init__(*args, **kwargs)
        self.rxst = None

    def login(self, username, password):
        # Set right cookies
        self.session.get(BASE_URL)

        login_page = self.session.get(LOGIN_URL)
        login_doc = lxml.html.fromstring(login_page.content)
        login_form = login_doc.cssselect("form.login")[0]
        login_post_url = login_form.get("action")
        login_fail_url = login_form.cssselect("input[name=failureUrl]")[0].get("value")

        # Login
        post_data = parse_form(login_form)
        post_data.update({"username": username, "password": password})
        response = self.session.post(login_post_url, post_data)

        # Check if logging in worked :)
        return response.url != login_fail_url

    def _get_rxst(self):
        if self.rxst is not None:
            return self.rxst

        redirect = self.session.get(RXST_URL, allow_redirects=False).headers["location"]
        params = parse_qs(urlparse(redirect).query)
        self.rxst = params['rxst'][0]
        log.info("Found token {}".format(self.rxst))
        return self.rxst

    def _get_section_table(self, page):
        return (line.strip() for line in page if line.strip().startswith("sectionTable.add"))

    def _get_pages(self, date):
        frontpage_url = date.strftime(FRONTPAGE_URL).format(rxst=self._get_rxst())

        front_page_content = self.session.get(frontpage_url).content
        if not NO_PAPER_AVAILABLE.findall(front_page_content):
            container = self.session.get_html(frontpage_url)
            frame_url = container.cssselect("#pageframe")[0].get("src")
            absolute_frame_url = urljoin(ARCHIVE_URL, frame_url)

            doc = self.session.get_html(absolute_frame_url)
            pages = doc.cssselect("#selectPage option")

            for page in pages:
                page_nr, section = page.text.split("-")
                page_nr = page_nr.strip()[1:]
                section = section.strip()
                page_url = date.strftime(PAGE_URL).format(id=page.get("value"))
                yield page_nr, section, page_url

    def _get_articles(self, date, url):
        page_doc = self.session.get_html(url)

        for td in page_doc.cssselect("td[onclick]"):
            aids = ARTICLE_ID_RE.findall(td.get("onclick"))
            yield date.strftime(ARTICLE_URL).format(id=aids[0])

    def get_units(self):
        for date in self.dates:
            for page_nr, section, page_url in self._get_pages(date):
                for article_url in set(self._get_articles(date, page_url)):
                    yield page_nr, section, date, article_url

    def scrape_unit(self, props):
        page_nr, section, date, url = props

        article = self.session.get_html(url)

        text = article.cssselect("td > font.artbody")
        if not text:
            return None

        text = article.cssselect("td > font.artbody")[1:]
        text = map(html2text, map(lxml.html.tostring, text))
        text = "\n\n".join(p.replace("\n", "") for p in text)

        if not article.cssselect("td.artheader"):
            return None

        article_properties = {
            "headline": article.cssselect("td.artheader")[0].text,
            "subsection": article.cssselect("td.artlabel")[0].text,
            "pagenr": page_nr,
            "section": section,
            "text": text,
            "date": date,
            "url": url
        }

        author = article.cssselect(".artauthor")
        if author:
            article_properties["author"] = author[0].text.split(":")[1].strip()

        if article_properties["text"].strip():
            return Article(article_properties)

    _props = {
        'defaults': {
            'medium': 'Financieel Dagblad',
            'insertscript': 'FinancieelDagbladScraper'
        },
        'required': ['date', "subsection", 'headline', 'section', 'pagenr', 'text'],
        'expected': []
    }

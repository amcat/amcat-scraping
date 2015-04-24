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
from html2text import html2text
import lxml.html
from urlparse import urljoin
import re

from amcatscraping.article import Article
from amcatscraping.tools import setup_logging, parse_form
from amcatscraping.scraper import (LoginMixin, PropertyCheckMixin,
                                   UnitScraper, DateRangeScraper)


# This is a magic value stolen from the browser (you can retrieve it using
# development tools in Chromium / Firefox). I'm not sure how to fetch it
# programmatically. Its past midnight and I can't be bothered much, so this
# will have to do for now. I hope it's a non-expiring magic value.
RXST = "WmNQM0ZYMWlvMU11ZFZWQnA2SG9QZz09"


# URLS
LOGIN_URL = "https://fd.nl/login"
BASE_URL = "http://digikrant.fd.nl/"
ARCHIVE_URL = "http://digikrant-archief.fd.nl/"
INIT_URL = BASE_URL + "go?url=digikrant-archief.fd.nl/vw/edition.do?dp=FD%26altd=true%26date=%Y%m%d%26ed=00"
FRONTPAGE_URL = ARCHIVE_URL + "vw/edition.do?dp=FD&altd=true&date=%Y%m%d&ed=00&rxst={rxst}"
PAGE_URL = ARCHIVE_URL + "vw/page.do?id={id}&pagedisplay=true&date=%Y%m%d"
ARTICLE_URL = ARCHIVE_URL + "vw/txt.do?id={id}"

# REs
ARTICLE_ID_RE = re.compile("FD-[0-9-]+")


class FinancieelDagbladScraper(LoginMixin, PropertyCheckMixin, UnitScraper, DateRangeScraper):
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

    def _get_section_table(self, page):
        return (line.strip() for line in page if line.strip().startswith("sectionTable.add"))

    def _get_pages(self, date):
        container = self.session.get_html(date.strftime(FRONTPAGE_URL).format(rxst=RXST))
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

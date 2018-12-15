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
from typing import Tuple
from urllib import parse

import collections
import lxml.html
import re

from amcat.models import Article
from amcatscraping.tools import setup_logging, parse_form
from amcatscraping.scraper import LoginMixin, UnitScraper, DateRangeScraper


OVERVIEW_URL = "https://login.nrc.nl/overview"

PUBLISHED_PREFIX = "Dit artikel werd gepubliceerd in"
PUBLISHED_POSTFIX = " (?P<paper>[\.\w ]+) op (?P<date>[\w ,]+), pagina (?P<page>[\w -]+)"
PUBLISHED_RE = re.compile(PUBLISHED_PREFIX + PUBLISHED_POSTFIX)

ArticleTuple = collections.namedtuple("ArticleTuple", ["url", "date"])


class NRCScraper(LoginMixin, UnitScraper, DateRangeScraper):
    nrc_version = None

    def login(self, username, password):
        login_page = self.session.get(OVERVIEW_URL)
        login_doc = lxml.html.fromstring(login_page.content)
        login_url = login_page.url

        post = parse_form(login_doc.cssselect("#fm1")[0])
        post.update({"username": username, "password": password})

        response = self.session.post(login_url, post)
        return response.url.endswith("/overview")

    def get_units(self):
        for date in self.dates:
            for doc in self.__getsections(date):
                for a in doc.cssselect("ul.article-links li > a"):
                    yield ArticleTuple(parse.urljoin(a.base_url, a.get('href')), date)

    def get_url_from_unit(self, unit: ArticleTuple) -> str:
        return unit.url

    def __getsections(self, date):
        monthminus = date.month - 1
        url1 = "http://digitaleeditie.nrc.nl/digitaleeditie/{self.nrc_version}/{date.year}/{monthminus}/{date.year}{date.month:02d}{date.day:02d}___/section1.html".format(**locals())
        doc1 = self.session.get_html(url1)
        yield doc1
        for a in doc1.cssselect("ul.main-sections li:not(.active) a.section-link"):
            yield self.session.get_html(parse.urljoin(a.base_url, a.get("href")))

    def scrape_unit(self, unit):
        print(unit)
        url = unit.url
        doc = self.session.get_html(url)
        text = "\n\n".join([t.text_content() for t in doc.cssselect("em.intro,div.column-left p")])

        if not text:
            return None

        datestr = url.split("/")[7].strip("_")
        location = doc.cssselect("em.location")
        person = doc.cssselect("p.by span.person")

        published = doc.cssselect(".published")[0].text_content().strip()
        published = PUBLISHED_RE.match(published).groupdict()

        try:
            pagenr = int(url.split("/")[8].split("_")[1])
        except IndexError:
            pagenr = int(published["page"].split("-")[0])

        section_span = doc.cssselect("#Content ul.main-sections li.active span")
        if section_span:
            section = section_span[0].text
        else:
            section = doc.cssselect("#Content .breadcrums a.previous")[0].text

        date = datetime.datetime(*map(int, [datestr[:4], datestr[4:6], datestr[6:]]))
        title = doc.cssselect("#MainContent h2")[0].text_content().strip() or "-"

        article = Article(date=date, title=title, text=text, url=url)

        author = person and person[0].text_content() or None
        if author:
            article.set_property("author", author)

        location = location and location[0].text or None
        if location:
            article.set_property("location", location)

        subtitle = "\n".join([h3.text_content() for h3 in doc.cssselect("div.column-left h3")])

        article.set_property("subtitle", subtitle)
        article.set_property("section", section)
        article.set_property("pagenr_int", pagenr)

        return article


if __name__ == '__main__':
    setup_logging()
    NRCScraper().run()

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

import logging

from requests import HTTPError

from amcat.models import Article
from amcatscraping.tools import setup_logging, parse_form
from amcatscraping.scraper import LoginMixin, UnitScraper, DateRangeScraper
from datetime import datetime

OVERVIEW_URL = "https://login.nrc.nl/overview"

PUBLISHED_PREFIX = "Dit artikel werd gepubliceerd in"
PUBLISHED_POSTFIX = " (?P<paper>[\.\w ]+) op (?P<date>[\w ,]+), pagina (?P<page>[\w -]+)"
PUBLISHED_RE = re.compile(PUBLISHED_PREFIX + PUBLISHED_POSTFIX)

NRCUnit = collections.namedtuple("NRCUnit", ["docid", "url", "date", "pages", "sections", "image", "pdf"])


class NRCScraper(LoginMixin, UnitScraper, DateRangeScraper):
    nrc_version = None

    def login(self, username, password):
        login_page = self.session.get(OVERVIEW_URL)

        login_doc = lxml.html.fromstring(login_page.content)
        login_url = login_page.url

        login_form = parse_form(login_doc.cssselect("#fm1")[0])
        login_form.update({"username": username, "password": password, "rememberMe": "on"})

        response = self.session.post(login_url, login_form, allow_redirects=False)

        # check whether we are truly logged in
        x = self.session.get("https://login.nrc.nl/overview")
        open("/tmp/test.html", "wb").write(x.content)

        return response.status_code == 302 # if login incorrect, it returns 401

    def get_units(self):
        for date in self.dates:
            if date.weekday() == 6: # sunday
                continue
            data_url = f"https://www.nrc.nl/de/data/NH/{date.year}/{date.month}/{date.day}/"
            logging.warning(f"Scraping {data_url}")
            r = self.session.get(data_url)
            if r.status_code == 500:
                logging.warning("HTTP 500, was there news on {date}?")
                continue
            if r.status_code == 404:
                logging.warning("HTTP 404, was there news on {date}?")
                continue
            r.raise_for_status()
            data = r.json()
            units = {}
            for page in data['pages']:
                for box in page['boxes']:
                    if box['type'] != 'editorial':
                        continue
                    if box['url'].startswith("https://images.nrc.nl/"):
                        logging.warning(f"Skipping image url {box['url']}")
                        continue
                    #if not box['url'].startswith("/nieuws/"):
                     #   raise Exception(f"Unexpected url: {box['url']}")
                    doc_id = box['document_id']
                    if doc_id not in units:
                        url = parse.urljoin("https://www.nrc.nl", box['url'])
                        units[doc_id] = NRCUnit(doc_id, url, date, set(), set(),
                                                box['clipping_image_url'], box['clipping_pdf_url'])
                    u = units[doc_id]
                    if box['clipping_image_url'] != u.image:
                        raise Exception(f"{u.url}: u.image {u.image} != box.image {box['clipping_image_url']}")
                    if box['clipping_pdf_url'] != u.pdf:
                        raise Exception(f"{u.url}: u.pdf {u.pdf} != box.pdf {box['clipping_pdf_url']}")
                    u.pages.add(page['number'] if page['book'] == 1 else int(page['index']))
                    for section in page['sections']:
                        u.sections.add(section)
            yield from units.values()

    def get_url_and_date_from_unit(self, unit: NRCUnit) -> Tuple[str, datetime.date]:
        return unit.url, unit.date

    def scrape_unit(self, unit: NRCUnit):
        m = re.match(r"https://www.nrc.nl/nieuws/(\d{4})/(\d{2})/(\d{2})/", unit.url)
        if not m:
            logging.warning(f"Invalid URL: {unit.url}")
            return None
        year = int(m.group(1))
        month = int(m.group(2))
        day = int(m.group(3))
        online_date = datetime(year, month, day)
        try:
            html = self.session.get_content(unit.url)
        except HTTPError as e:
            if e.response.status_code == 404:
                logging.warning(f"No article found for {unit.url}")
                return  # some articles don't exist, i.e. cartoons without text
            raise

        doc = lxml.html.fromstring(html, base_url=unit.url)
        intro = doc.cssselect("div.intro")
        if not intro:
            logging.debug(f"Invalid intro: {unit.url}")
            intro = ""
        else:
            intro2 = intro[0].text_content()
        headline = doc.cssselect(".article-header-container h1")
        if not headline:
            headline2 = "-"
            logging.warning(f"No headline {unit.url}")
        else:
            headline2 = headline[0].text_content()
            if not headline2:
                headline2 = "-"
                logging.warning(f"Empty headline {unit.url}")
        author = doc.cssselect("ul.article__byline__text.unstyled a")
        if not author:
            logging.debug(f"Invalid author: {unit.url}")
            author2 = ""
        else:
            author2 = author[0].text_content()
        text = doc.cssselect("div.article__content")
        if not text:
            text = doc.cssselect("div.article__header-and-content")
        text2 = text[0].text_content()
        text2 = re.sub(r"\s*\n\s*", "\n\n", text2).strip()
        text2 = re.sub(r"[ \t]+", " ", text2).strip()
        if intro:
            text3 = f"{intro2},{text2}"
        else:
            text3 = f"{text2}"

        article = Article(date=unit.date,
                          online_date=online_date,
                          title=headline2,
                          text=text3,
                          url=unit.url,
                          image_url=unit.image,
                          pdf_url=unit.pdf,
                          page_tag=unit.pages,
                          section_tag=unit.sections,
                          raw_html=html,
                          author=author2)
        return article


if __name__ == '__main__':
    setup_logging()
    NRCScraper().run()

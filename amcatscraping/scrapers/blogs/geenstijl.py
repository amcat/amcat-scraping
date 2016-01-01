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
from __future__ import print_function, unicode_literals

from collections import defaultdict
import datetime
import logging
import requests

from amcatscraping.scraper import UnitScraper, DateRangeScraper, PropertyCheckMixin
from amcatscraping.tools import html2text, read_date
from amcatscraping.article import Article


ARCHIEF_URL = "http://www.geenstijl.nl/mt/archieven/maandelijks/%Y/%m/"

# These urls are deaud.
IGNORE_URLS = {
    "http://www.geenstijl.nl/mt/archieven/2012/10/man_flasht_mes_op_groest.html",
    "http://www.geenstijl.nl/mt/archieven/2014/02/bord_op_schoot.html"
}


log = logging.getLogger(__name__)


def _parse_comment_footer(footer):
    author, date, time = footer.rsplit("|", 2)

    day, month, year = date.split("-")
    hour, minute = time.split(":")

    timestamp = datetime.datetime(int(year)+2000, int(month), int(day), int(hour), int(minute))

    return author, timestamp


class GeenstijlScraper(PropertyCheckMixin, UnitScraper, DateRangeScraper):
    medium = "Geenstijl"

    def __init__(self, **kwargs):
        super(GeenstijlScraper, self).__init__(**kwargs)
        self.articles = defaultdict(set)
        self.session.encoding = "iso-8859-1"
        # accepteer de cookies
        requests.utils.add_dict_to_cookiejar(self.session.cookies, {"cpc": "10"})

    def get_units(self):
        for date in self.dates:
            day_string = date.strftime("%d-%m-%y")
            
            if day_string not in self.articles:
                self._get_archive(date)

            for article_url in self.articles[day_string]:
                if article_url not in IGNORE_URLS:
                    yield date, article_url

    def _get_archive(self, date):
        """Fill article-link cache with all articles written in the same month as 'date'"""
        url = date.strftime(ARCHIEF_URL)
        doc = self.session.get_html(url)
        for li in doc.cssselect("li"):
            if not li.text:
                continue

            link = li.cssselect("a")[0].get("href")
            self.articles[li.text.strip()].add(link.strip())

    def _parse_comment(self, comment, base_headline, base_url):
        text = html2text(comment.cssselect("p"))
        article_id = comment.get("id")
        headline = "{base_headline}#{article_id}".format(**locals())
        url = "{base_url}#{article_id}".format(**locals())
        author, timestamp = _parse_comment_footer(comment.cssselect("footer")[0].text_content())

        return Article({
            "date": timestamp,
            "headline": headline,
            "text": text.strip() or ".",
            "author": author,
            "medium": "GeenStijl comments",
            "url": url
        })

    def _get_comments(self, headline, article_url, doc):
        for comment in doc.cssselect("#comments article"):
            yield self._parse_comment(comment, headline, article_url)

    def scrape_unit(self, date_and_article_url):
        date, article_url = date_and_article_url
        log.info("Fetching {}".format(article_url))
        article_doc = self.session.get_html(article_url)

        article_el = article_doc.cssselect("#content > article")

        if not article_el:
            log.error("Could not find article on {article_url}".format(**locals()))
            return None

        headline = article_el[0].cssselect("h1")[0].text
        text = html2text(article_el[0].cssselect("p"))

        try:
            footer = article_el[0].cssselect("footer")[0]
        except IndexError as e:
            # Contains <embed> tag which is not closed gracefully :-(
            log.exception(e)
            return None

        author = footer.text.rsplit("|", 1)[0].strip()
        timestamp = read_date(article_el[0].cssselect("footer > time")[0].get("datetime"))
        if not headline:
            return None

        properties = {
            "date": timestamp,
            "headline": headline,
            "text": text.strip() or ".",
            "author": author,
            "url": article_url
        }

        children = self._get_comments(headline, article_url, article_doc)

        return Article(properties, children)

    def update(self, article_tree):
        article = article_tree.article
        article_doc = self.session.get_html(article["url"])
        comments = self._get_comments(article["headline"], article["url"], article_doc)
        urls = {comment.article["url"] for comment in article_tree.children}

        for comment in comments:
            if comment["url"] not in urls:
                comment['parent'] = article["id"]
                yield comment


    _props = {
        'defaults': {
            'medium': "Geenstijl"
        },
        'required': ['date', 'text', 'headline', 'author'],
        'expected': []
    }



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
from collections import defaultdict
import datetime

from amcatscraping.scraper import UnitScraper, DateRangeScraper
from amcatscraping.tools import html2text, read_date


ARCHIEF_URL = "http://www.geenstijl.nl/mt/archieven/maandelijks/%Y/%m/"


def get_day_string(day):
    return "%d-%m-%y"


def _parse_comment_footer(footer):
    author, date, time = footer.rsplit("|", 2)

    day, month, year = date.split("-")
    hour, minute = time.split(":")

    timestamp = datetime.datetime(int(year)+2000, int(month), int(day), int(hour), int(minute))

    return author, timestamp


class GeenstijlScraper(UnitScraper, DateRangeScraper):
    def __init__(self, *args, **kwargs):
        super(GeenstijlScraper, self).__init__(*args, **kwargs)
        self.articles = defaultdict(set)
        self.session.encoding = "iso-8859-1"

    def _get_units(self):
        for date in self.dates:
            day_string = date.strftime("%d-%m-%y")

            if day_string not in self.articles:
                self._get_archive(date)

            for article_url in self.articles[day_string]:
                yield date, article_url

    def _get_archive(self, date):
        """Fill article-link cache with all articles written in the same month as 'date'"""
        doc = self.session.get_html(date.strftime(ARCHIEF_URL))

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

        return {
            "date": timestamp,
            "headline": headline,
            "text": text,
            "author": author,
            "url": url
        }

    def _scrape_unit(self, date_and_article_url):
        date, article_url = date_and_article_url
        article_doc = self.session.get_html(article_url)

        article_el = article_doc.cssselect("#content > article")[0]
        headline = article_el.cssselect("h1")[0].text
        text = html2text(article_el.cssselect("p"))
        footer = article_el.cssselect("footer")[0]
        author = footer.text.rsplit("|", 1)[0].strip()
        timestamp = read_date(article_el.cssselect("time")[0].get("datetime"))

        comments = article_doc.cssselect("#comments article")

        return {
            "date": timestamp,
            "headline": headline,
            "text": text,
            "author": author,
            "url": article_url,
            "children": [self._parse_comment(c, headline, article_url) for c in comments]
        }




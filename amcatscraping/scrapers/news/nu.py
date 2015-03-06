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
import feedparser

from amcatscraping.scraper import UnitScraper, ContinuousScraper
from amcatscraping.tools import read_date, html2text

RSS_URL = "http://www.nu.nl/rss"


class NuScraper(ContinuousScraper, UnitScraper):
    def __init__(self, *args, **kwargs):
        super(NuScraper, self).__init__(*args, **kwargs)
        self.seen_ids = set()

    def get_units(self):
        for entry in feedparser.parse(RSS_URL)["entries"]:
            if entry["id"] not in self.seen_ids:
                yield entry
                self.seen_ids.add(entry["id"])

    def get_article_properties(self, url):
        article_doc = self.session.get_html(url)

        # Bylines are sometimes included in the main body text. We won't put in
        # any effort to pluck out those cases though..
        byline = article_doc.cssselect(".article.header .item-excerpt")
        if byline:
            yield "byline", html2text(byline[0])

        yield "section", article_doc.cssselect(".breadcrumb li.active")[0].text_content().strip()
        yield "text", html2text(article_doc.cssselect(".article.body")[0]).strip()

    def scrape_unit(self, entry):
        feed_properties = {
            "date": read_date(str(entry["published"])),
            "author": entry["author"],
            "url": entry["link"],
            "headline": entry["title"],
            "medium": "nu.nl"
        }

        article_properties = self.get_article_properties(feed_properties["url"])
        article_properties = dict(feed_properties, **dict(article_properties))
        return article_properties


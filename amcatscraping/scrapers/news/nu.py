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
import iso8601
import redis
import dateparser

from typing import Iterable

from amcat.models import Article
from amcatscraping.scraper import UnitScraper
from amcatscraping.tools import html2text

RSS_URL = "http://www.nu.nl/rss"


class NuScraper(UnitScraper):
    medium = "nu.nl"

    def __init__(self, *args, **kwargs):
        super(NuScraper, self).__init__(*args, **kwargs)
        self.cache = redis.from_url("redis://127.0.0.1:6379/1")

    def get_cache_key(self):
        return "nu_scraper_article_ids_{self.project_id}_{self.articleset_id}".format(self=self)

    def add_to_cache(self, id: str):
        self.cache.sadd(self.get_cache_key(), id)

    def is_saved_article(self, id: str):
        return self.cache.sismember(self.get_cache_key(), id)

    def save(self, *args, **kwargs) -> Iterable[Article]:
        for article in super(NuScraper, self).save(*args, **kwargs):
            yield self.add_to_cache(article.get_property("nuid"))

    def get_units(self):
        for entry in feedparser.parse(RSS_URL)["entries"]:
            if not self.is_saved_article(entry["id"]):
                yield entry

    def get_article_section_text(self, url):
        article_doc = self.session.get_html(url)

        yield article_doc.cssselect(".breadcrumb li.active")[0].text_content().strip()
        text = html2text(article_doc.cssselect(".article.body")[0]).strip()

        # Bylines are sometimes included in the main body text. We won't put in
        # any effort to pluck out those cases though..
        byline = article_doc.cssselect(".article.header .item-excerpt")
        if byline:
            text += "\n\n"
            text += html2text(byline[0])
        yield text

    def parse_date(self, date: str):
        # Date example: Sun, 11 Dec 2016 23:03:56 +0100
        timezone = date.split(" ")[-1]
        date = dateparser.parse(date)
        date = date.isoformat() + timezone
        return iso8601.iso8601.parse_date(date)

    def scrape_unit(self, entry):
        article = Article()
        section, text = self.get_article_section_text(entry["link"])
        article.set_property("nuid", entry["id"])
        article.set_property("title", entry["title"])
        article.set_property("date", self.parse_date(str(entry["published"])))
        article.set_property("url", entry["link"])
        article.set_property("section", section)
        article.set_property("text", text)
        return article


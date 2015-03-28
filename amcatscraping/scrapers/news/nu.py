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
import json
import requests
import feedparser
from amcatscraping.article import Article

from amcatscraping.scraper import UnitScraper, ContinuousScraper
from amcatscraping.tools import read_date, html2text

RSS_URL = "http://www.nu.nl/rss"


def parse_comment(comment):
    date = read_date(comment.cssselect(".tijdsverschil")[0].get("publicationdate"))
    comment_nr = comment.cssselect(".reactie-nummer")[0].text

    deleted = False

    try:
        author = comment.cssselect(".reactie-kop > strong")[0].text_content().strip()
        text = html2text(comment.cssselect(".reactie-body")[0])
    except IndexError:
        author = "[deleted]"
        text = "."
        deleted = True

    return {
        "date": date,
        "text": text,
        "author": author,
        "metastring": {
            "comment_id": int(comment.get("id")),
            "comment_nr": int(comment_nr),
            "deleted": deleted
        }
    }


def get_comments(session, link, offset=1):
    article_url = "{link}?pageStart={offset}".format(**locals())
    article_doc = session.get_html(article_url)
    article_doc.cssselect("#commentForm")[0].drop_tree()

    h1 = article_doc.cssselect(".articleheader h1")[0]
    headline = h1.text_content().strip()
    refers_to = h1.cssselect("a")[0].get("href")

    tags = list({tag.text.strip() for tag in article_doc.cssselect(".bericht-tags-links > a")})

    latest_comment_nr = 0
    for li in article_doc.cssselect("ol.reacties > li"):
        comment = parse_comment(li)
        comment.update({
            "headline": "{}#{}".format(headline, comment['metastring']['comment_nr']),
            "url": "{}#{}".format(article_url, comment['metastring']['comment_id'])
        })

        comment["metastring"]["tags"] = tags
        yield Article(comment)

        latest_comment_nr = comment["metastring"]["comment_nr"]

    n_replies = int(article_doc.cssselect(".bericht-tools .bericht-reacties")[0].text.split()[0])
    if latest_comment_nr and n_replies > latest_comment_nr + 1:
        for comment in get_comments(session, link, offset=latest_comment_nr+1):
            yield comment


class NuScraper(ContinuousScraper, UnitScraper):
    medium = "nu.nl"

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
            "medium": self.medium
        }

        article_properties = self.get_article_properties(feed_properties["url"])
        article_properties = dict(feed_properties, **dict(article_properties))
        return Article(article_properties)

    def update(self, article_tree):
        article, children = article_tree
        article_doc = self.session.get_html(article['url'])

        nujij_button = article_doc.cssselect(".social-buttons > .nujij a")[0]
        nujij_url = nujij_button.get("href")
        nujij_url = requests.get(nujij_url).url

        medium = {
            "medium": self.medium,
            "parent": article["id"]
        }

        metastrings = (json.loads(comment.article["metastring"]) for comment in children)
        comment_nrs = {ms["comment_nr"] for ms in metastrings}

        if int(nujij_button.cssselect(".counter")[0].text.strip()):
            for comment in get_comments(self.session, nujij_url):
                if comment.properties["metastring"]["comment_nr"] not in comment_nrs:
                    comment.properties.update(medium)
                    yield comment

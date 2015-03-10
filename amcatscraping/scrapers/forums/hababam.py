###########################################################################
# (C) Vrije Universiteit, Amsterdam (the Netherlands)                     #
# #
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
from lxml.etree import XMLSyntaxError

import json
import logging
import datetime
import itertools
from operator import attrgetter, itemgetter
from urlparse import urljoin

from amcatscraping.scraper import BinarySearchDateRangeScraper, LoginMixin
from amcatscraping.tools import read_date, memoize, html2text


HABABAM_URL = "http://forums.hababam.nl/showthread.php?t={thread_id}&page={pagenr}"

# To keep te scraper to perform well on entirely new runs (new machines),
# we should update this value every once in a while.
LATEST_ID = 187737

log = logging.getLogger(__name__)


def _parse_timestamp(timestamp):
    timestamp = timestamp.replace(u"\xa0", " ").strip()
    date, time = timestamp.lower().strip().split(" ")

    if date.strip() == "vandaag":
        today = datetime.date.today()
        year, month, day = today.year, today.month, today.day
    elif date.strip() == "gisteren":
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        year, month, day = yesterday.year, yesterday.month, yesterday.day
    else:
        return read_date(timestamp)

    hour, minute = time.strip().split(":")
    return datetime.datetime(year, month, day, int(hour), int(minute))


class HababamScraper(BinarySearchDateRangeScraper, LoginMixin):
    medium = "hababam"

    @memoize
    def get_html(self, thread_id, page_nr=1):
        url = HABABAM_URL.format(thread_id=thread_id, pagenr=page_nr)
        log.info("Fetching {url}..".format(url=url))
        doc = self.session.get_html(url, allow_redirects=False)

        # Remove advertising
        for post in doc.cssselect("ol.posts > li"):
            if not post.cssselect(".userinfo"):
                post.drop_tree()

        return doc

    def get_oldest(self):
        return datetime.date(2005, 4, 3), 2

    def get_date(self, id):
        if not self._exists_single(id):
            return None

        timestamp = self.get_html(id).cssselect(".posts .date")[0].text_content()
        return _parse_timestamp(timestamp).date()

    @memoize
    def _exists_single(self, thread_id):
        try:
            return not self.get_html(thread_id).cssselect(".standard_error")
        except XMLSyntaxError:
            return False

    def _exists(self, thread_id, n=5):
        return any(self._exists_single(thread_id + i) for i in range(n))

    def _get_latest(self, thread_id, step=2 ** 8, tries=3):
        if not self._exists(thread_id + step):
            if step == 1:
                return thread_id
            return self._get_latest(thread_id, step // 2)
        return self._get_latest(thread_id + step, step)

    @memoize
    def get_latest(self, step=2 ** 12):
        log.info("Determining latest id..")
        latest_id = max(itertools.chain([LATEST_ID], self.id_cache.values()))
        latest_id = self._get_latest(latest_id)
        return self.get_date(latest_id), latest_id

    def parse_post(self, thread_id, title, doc, post):
        timestamp = post.cssselect(".posthead .date")[0]
        date = _parse_timestamp(timestamp.text_content())
        post_id = post.cssselect(".posthead .postcounter")[0].get("name")
        post_count = post.cssselect(".posthead .postcounter")[0].text.strip("#")
        base_url = HABABAM_URL.format(thread_id=thread_id, pagenr=1)
        url = "{base_url}#{post_id}".format(**locals())
        text = html2text(post.cssselect(".postbody .content")[0]).strip()

        # Find pagenr
        pagination = doc.cssselect("#pagination_top")[0]
        selected = pagination.cssselect("span.selected")

        if not selected:
            pagenr = 1
        else:
            pagenr = int(selected[0].text_content().strip())

        # Author info
        userinfo = post.cssselect(".userinfo")[0]
        author = userinfo.cssselect(".username")[0].text_content().strip()
        author_url = urljoin(base_url, userinfo.cssselect(".username")[0].get("href"))

        return {
            "date": date,
            "url": url,
            "text": text or ".",
            "author": author,
            "pagenr": pagenr,
            "headline": u"{}#{}".format(title, post_count),
            "medium": self.medium,
            "metastring": {
                "thread_id": thread_id,
                "author_url": author_url,
                "post_id": int(post_id.strip("post")),
                "post_count": int(post_count),
            }
        }

    def scrape_unit(self, thread_id):
        if not self._exists_single(thread_id):
            return None

        doc = self.get_html(thread_id)
        posts = doc.cssselect("ol.posts > li")
        title = doc.cssselect("#pagetitle .threadtitle a")[0].text.strip()
        article = self.parse_post(thread_id, title, doc, posts[0])
        article["headline"] = title
        return article

    def _get_comments(self, thread_id, title, pagenr=1):
        doc = self.get_html(thread_id, pagenr)

        for post in doc.cssselect("ol.posts > li"):
            yield self.parse_post(thread_id, title, doc, post)

        if any(pn.get("rel") == "next" for pn in doc.cssselect("#pagination_top .prev_next a")):
            for post in self._get_comments(thread_id, title, pagenr+1):
                yield post

    def update(self, article_tree):
        articles = map(attrgetter("article"), [article_tree] + list(article_tree.children))

        for article in articles:
            article["metastring"] = json.loads(article["metastring"])

        urls = map(itemgetter("url"), articles)
        pagenr = max(map(itemgetter("pagenr"), articles))
        thread_id = articles[0]["metastring"]["thread_id"]

        for article in self._get_comments(thread_id, articles[0]["headline"], pagenr):
            if article["url"] not in urls:
                article["parent"] = articles[0]["id"]
                yield article



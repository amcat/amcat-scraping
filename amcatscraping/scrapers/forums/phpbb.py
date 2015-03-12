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
import colored_traceback.always

import os
import json
import datetime
import logging
import itertools
from operator import attrgetter, itemgetter
from urlparse import urljoin
import re

from amcatscraping.scraper import BinarySearchDateRangeScraper, CACHE_DIR
from amcatscraping.tools import read_date, memoize, html2text, open_json_cache
from lxml.etree import XMLSyntaxError


log = logging.getLogger(__name__)


PHPBB_URL = "http://{self.domain}/showthread.php?t={thread_id}&page={pagenr}"
PHPBB_ARCHIVE_URL = "http://{self.domain}/archive/index.php"
PHPBB_SUBARCHIVE_URL = PHPBB_ARCHIVE_URL + "/f-{archive_id}-{title}-p-{pagenr}.html"
PHPBB_SUBARCHIVE_RE = re.compile("f-(?P<id>[0-9]+)-(?P<title>[a-z0-9-]*)-p-(?P<pagenr>[0-9]+).html")
PHPBB_THREAD_URL_RE = re.compile("t-(?P<thread_id>[0-9]+)-(?P<title>[a-z0-9-]*).html")


def parse_subarchive_url(url):
    url = url.rsplit("/", 1)[1]
    id, title, pagenr = PHPBB_SUBARCHIVE_RE.match(url).groups()
    return int(id), title, int(pagenr)


def parse_thread_url(url):
    url = url.rsplit("/", 1)[1]
    thread_id, title = PHPBB_THREAD_URL_RE.match(url).groups()
    return int(thread_id), title


class PHPBBScraper(BinarySearchDateRangeScraper):
    medium = None
    domain = "forums.example.com"
    valid_ids_cache_file = os.path.join(CACHE_DIR, "{self.__class__.__name__}_valid_ids_cache.json")

    def _get_valid_ids(self, known_ids, archive_id, title, pagenr):
        url = PHPBB_SUBARCHIVE_URL.format(**locals())
        log.info("Fetching {url}..".format(url=url))
        links = self.session.get_html(url).cssselect("#content a")
        links = filter(None, (u.get("href") for u in links))
        ids = [parse_thread_url(u)[0] for u in links]

        for id in ids:
            yield id

        # Proceed to previous page if all found ids are unknown
        if all(id not in known_ids for id in ids) and pagenr > 1:
            for id in self._get_valid_ids(known_ids, archive_id, title, pagenr - 1):
                yield id

    @memoize
    def get_valid_ids(self):
        log.info("Determining valid ids (this may take very long on new machines)..")
        cache_file = self.valid_ids_cache_file.format(**locals())
        id_cache = set(open_json_cache(cache_file, default=set()))
        archive = self.session.get_html(PHPBB_ARCHIVE_URL.format(**locals()))
        links = filter(None, (a.get('href') for a in archive.cssselect("#content a")))

        new_ids = set()
        for subarchive in itertools.imap(self.session.get_html, links):
            url = subarchive.cssselect(".pagenumbers")[0].cssselect("a")[-1].get("href")
            new_ids |= set(self._get_valid_ids(id_cache, *parse_subarchive_url(url)))

        ids = new_ids | id_cache
        json.dump(list(ids), open(cache_file, "w"))
        return sorted(ids)

    @memoize
    def _exists(self, thread_id):
        try:
            return not self.get_html(thread_id).cssselect(".standard_error")
        except XMLSyntaxError:
            return False

    def get_date(self, thread_id):
        if not self._exists(thread_id):
            return None

        timestamp = self.get_html(thread_id).cssselect(".posts .date")[0].text_content()
        return self.parse_timestamp(timestamp).date()

    @memoize
    def get_latest(self, step=2 ** 12):
        log.info("Determining latest id..")
        latest_id = self.get_valid_ids()[-1]
        return self.get_date(latest_id), latest_id

    def parse_timestamp(self, timestamp):
        timestamp = timestamp.replace(u"\xa0", " ").strip()
        date, time = timestamp.lower().strip().split(" ")

        if date.strip() in ("vandaag", "today"):
            today = datetime.date.today()
            year, month, day = today.year, today.month, today.day
        elif date.strip() in ("gisteren", "yesterday"):
            yesterday = datetime.date.today() - datetime.timedelta(days=1)
            year, month, day = yesterday.year, yesterday.month, yesterday.day
        else:
            return read_date(timestamp)

        hour, minute = time.strip().split(":")
        return datetime.datetime(year, month, day, int(hour), int(minute))

    @memoize
    def get_html(self, thread_id, pagenr=1):
        url = PHPBB_URL.format(**locals())
        log.info("Fetching {url}..".format(url=url))
        doc = self.session.get_html(url, allow_redirects=False)

        # Remove advertising
        for post in doc.cssselect("ol.posts > li"):
            if not post.cssselect(".userinfo"):
                post.drop_tree()

        return doc

    def parse_post(self, thread_id, title, doc, post):
        timestamp = post.cssselect(".posthead .date")[0]
        date = self.parse_timestamp(timestamp.text_content())
        post_id = post.cssselect(".posthead .postcounter")[0].get("name")
        post_count = post.cssselect(".posthead .postcounter")[0].text.strip("#")
        base_url = PHPBB_URL.format(self=self, thread_id=thread_id, pagenr=1)
        url = "{base_url}#{post_id}".format(**locals())
        text = html2text(post.cssselect(".postbody .content")[0]).strip()

        sections = doc.cssselect("#breadcrumb .navbit > a")[1:]
        sections = [s.text_content().strip() for s in sections]

        # Find pagenr
        pagination = doc.cssselect("#pagination_top")[0]
        selected = pagination.cssselect("span.selected")

        if not selected:
            pagenr = 1
        else:
            pagenr = int(selected[0].text_content().strip())

        # Author info
        author = post.cssselect(".username")[0].text_content().strip()
        author_url = urljoin(base_url, post.cssselect(".username")[0].get("href"))

        return {
            "date": date,
            "url": url,
            "text": text or ".",
            "section": sections[-1],
            "author": author,
            "pagenr": pagenr,
            "headline": u"{}#{}".format(title, post_count),
            "medium": self.medium,
            "metastring": {
                "thread_id": thread_id,
                "author_url": author_url,
                "post_id": int(post_id.strip("post")),
                "post_count": int(post_count),
                "sections": sections
            }
        }

    def scrape_unit(self, thread_id):
        if not self._exists(thread_id):
            return None

        doc = self.get_html(thread_id)
        posts = doc.cssselect("ol.posts > li")
        title = doc.cssselect("#pagetitle .threadtitle a")[0].text.strip()
        article = self.parse_post(thread_id, title, doc, posts[0])
        article["headline"] = title
        article["children"] = list(self._get_comments(thread_id, title))
        return article

    def _get_comments(self, thread_id, title, pagenr=1):
        doc = self.get_html(thread_id, pagenr)

        for post in doc.cssselect("ol.posts > li")[int(pagenr == 1):]:
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


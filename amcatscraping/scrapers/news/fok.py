from operator import itemgetter

import lxml.html
import time
import logging
import datetime
import json
import os
import errno

from amcatscraping.scraper import PropertyCheckMixin, UnitScraper, BinarySearchDateRangeScraper
from amcatscraping.tools import read_date, memoize, html2text

ARTILCE_URL = "http://frontpage.fok.nl/nieuws/{article_id}"
FRONTPAGE_URL = "http://frontpage.fok.nl/"
CACHE_DIR = os.path.expanduser("~/.cache")
CACHE_FILE = os.path.join(CACHE_DIR, "fok_id_cache.json")

log = logging.getLogger(__name__)

DAYS = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]


@memoize
def get_diff(date, weekday):
    diff_map = {DAYS[date.isoweekday() - 1 - n]: n for n in range(7)}
    return datetime.timedelta(days=diff_map[weekday])


def parse_comment_date(date):
    """Parses dates of the form:

    vandaag, 15:34 uur
    zaterdag, 15:34 uur
    maandag 20 mei 2013, 14:48 uur"""
    day, hour = date.lower().split(",")

    # Date of form 'dayname day montn year...', which read_date can handle
    if day.count(" ") > 1:
        return read_date(date)

    if day == "vandaag":
        date = datetime.date.today()
    elif day == "gisteren":
        date = datetime.date.today() - datetime.timedelta(days=1)
    elif day in DAYS:
        today = datetime.date.today()
        date = today - get_diff(today, day)
    else:
        raise ValueError("{day} not recognised as valid dayname".format(**locals()))

    hour, minute = hour.strip().split(" ")[0].split(":")
    return datetime.datetime(date.year, date.month, date.day, int(hour), int(minute))


class FOKScraper(PropertyCheckMixin, BinarySearchDateRangeScraper):
    medium = "FOK - Frontpage"

    def setup_session(self):
        self.session.cookies["allowcookies"] = "ACCEPTEER ALLE COOKIES"
        self.session.cookies["allowallcookies"] = "1"

    def get_oldest(self):
        return datetime.date(1999, 9, 30), 134577

    @memoize
    def get_latest(self):
        first_link = self.session.get_html(FRONTPAGE_URL).cssselect("#main .indexPage li")
        first_link = first_link[0].cssselect("a")[0].get("href")
        first_link = first_link[len(FRONTPAGE_URL):]
        article_id = int(first_link.split("/")[1])
        return self.get_date(article_id), article_id

    @memoize
    def get_date(self, article_id):
        log.info("Fetching {}".format(ARTILCE_URL.format(**locals())))
        doc = self.session.get_html(ARTILCE_URL.format(**locals()))

        if not doc.cssselect("article"):
            return None

        return read_date(doc.cssselect("time")[0].get("datetime")).date()

    def _get_dates(self, min_date, max_date):
        if min_date < datetime.date(1999, 9, 30):
            raise ValueError("FOK's oldest articles was posted on 1999-09-30")
        return super(FOKScraper, self)._get_dates(min_date, max_date)

    def get_comment_elements(self, page):
        for comment in page.cssselect("#comments #commentThread > div[data-userid]"):
            yield comment

        # Try to scrape next page
        this_page = page.cssselect(".page.currentPage")
        if this_page:
            siblings = this_page[0].getparent().getchildren()

            try:
                next_page = siblings[siblings.index(this_page[0]) + 1]
            except IndexError:
                pass
            else:
                url = next_page.get("href")
                log.info("Fetching {}".format(url))
                next_page = self.session.get_html(url)
                for comment in self.get_comment_elements(next_page):
                    yield comment

    def get_comments(self, headline, url, section, page):
        for comment in self.get_comment_elements(page):
            top_bar = comment.cssselect(".commentTopBar")[0]

            author = top_bar.cssselect(".author a")[0].text
            if author is None:
                author = "[deleted user]"

            text = html2text(comment.cssselect(".commentContent")[0])
            comment_id = comment.get("id")
            user_id = comment.get("data-userid")
            livecomment_id = comment.get("data-livecomment")
            date = parse_comment_date(top_bar.cssselect(".posttime a")[0].text.strip())

            yield {
                "author": author,
                "headline": headline,
                "section": section,
                "text": text.strip() or ".",
                "date": date,
                "url": url + "#" + comment_id,
                "metastring": {
                    "author_id": user_id,
                    "comment_id": comment_id,
                    "livecomment_id": livecomment_id
                },
            }

    def scrape_unit(self, article_id):
        url = ARTILCE_URL.format(**locals())
        log.info("Fetching {}".format(url))
        doc = self.session.get_html(url)
        article = doc.cssselect("article")

        # Was article removed by moderator?
        if not article:
            return None

        article[0].cssselect("footer")[0].drop_tree()
        author = article[0].cssselect(".by span.mainFont")[0].text.strip()
        headline = article[0].cssselect("h1")[0].text.strip()
        date = read_date(article[0].cssselect("time")[0].get("datetime"))
        section = doc.cssselect("#crumbs li")[-1].cssselect("a")[0].text.strip()
        text = html2text(article[0].cssselect("p")).strip()

        return {
            "author": author,
            "headline": headline,
            "date": date,
            "section": section,
            "text": text.strip() or ".",
            "url": url,
            "metastring": {
                "article_id": article_id
            },
            "children": list(self.get_comments(headline, url, section, doc))
        }

    def update(self, article_tree):
        article, children = article_tree
        log.info("Fetching {}".format(article["url"]))
        doc = self.session.get_html(article["url"])
        comments = self.get_comments(article["headline"], article["url"], article["section"], doc)
        urls = {comment.article["url"] for comment in children}

        for comment in comments:
            if comment["url"] not in urls:
                comment["parent"] = article["id"]
                yield comment

    _props = {
        'defaults': {
            'medium': "FOK - Frontpage"
        },
        'required': ['date', 'text', 'headline', 'author'],
        'expected': []
    }

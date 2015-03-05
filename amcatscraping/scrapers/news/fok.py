from operator import itemgetter

import time
import logging
import datetime
import json
import os
import errno

from amcatscraping.scraper import PropertyCheckMixin, UnitScraper, DateRangeScraper
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


class FOKScraper(PropertyCheckMixin, UnitScraper, DateRangeScraper):
    def __init__(self, *args, **kwargs):
        super(FOKScraper, self).__init__(*args, **kwargs)
        self.session.cookies["allowcookies"] = "ACCEPTEER ALLE COOKIES"
        self.session.cookies["allowallcookies"] = "1"
        self.session.caching = True

        first_link = self.session.get_html(FRONTPAGE_URL).cssselect("#main .indexPage li")[0]
        first_link = first_link.cssselect("a")[0].get("href")
        first_link = first_link[len(FRONTPAGE_URL):]

        self.oldest_id = 134577
        self.latest_id = int(first_link.split("/")[1])

        # To not bombard FOK with needless requests each time, we cache
        # known article ids to help us with binary search
        try:
            os.makedirs(CACHE_DIR)
        except OSError as exception:
            if exception.errno != errno.EEXIST:
                raise

        try:
            self.id_cache = json.load(open(CACHE_FILE))
        except (IOError, ValueError):
            self.id_cache = {}

        dates, ids = zip(*dict(self.id_cache).items()) or [[], []]
        dates = [d.date() for d in map(datetime.datetime.fromtimestamp, dates)]
        self.id_cache = dict(zip(dates, ids))
        self.id_cache[datetime.date(1999, 9, 30)] = self.oldest_id
        self.id_cache[self._get_date(self.latest_id)] = self.latest_id

    def _dump_id_cache(self):
        dates, ids = zip(*self.id_cache.items()) or [[], []]
        dates = map(lambda d: int(time.mktime(d.timetuple())), dates)
        json.dump(zip(dates, ids), open(CACHE_FILE, "w"))

    @memoize
    def _get_date(self, article_id):
        log.info("Fetching {}".format(ARTILCE_URL.format(**locals())))
        doc = self.session.get_html(ARTILCE_URL.format(**locals()))

        if not doc.cssselect("article"):
            return self._get_date(article_id - 1)

        date = read_date(doc.cssselect("time")[0].get("datetime")).date()
        self.id_cache[date] = article_id
        return date

    def _get_first_id_linear(self, date):
        article_id = self.id_cache[date]
        while date == self._get_date(article_id):
            article_id -= 1
        return article_id

    def _get_first_id(self, date, left_date, right_date):
        log.info("Looking for {date}. Left: {left_date}, right: {right_date}".format(**locals()))

        if date == left_date:
            return self._get_first_id_linear(left_date)

        if date == right_date:
            return self._get_first_id_linear(right_date)

        if left_date == right_date or self.id_cache[right_date] - self.id_cache[left_date] == 1:
            return self.id_cache[left_date]

        left_id = self.id_cache[left_date]
        right_id = self.id_cache[right_date]
        pivot_id = (left_id + right_id) // 2
        pivot_date = self._get_date(pivot_id)

        if pivot_date < date:
            return self._get_first_id(date, pivot_date, right_date)
        else:
            return self._get_first_id(date, left_date, pivot_date)

    def get_first_id(self, date):
        """Determine the ID of the first article seen on 'date'. If no article is
        found on this day, the first article id before or after will be returned."""
        id_cache = sorted(self.id_cache.items(), key=itemgetter(0))

        # First determine left pivot..
        left_id, left_date = self.oldest_id, datetime.date(1999, 9, 30)
        for cached_date, cached_id in id_cache:
            if cached_date > date:
                break

            if cached_date > left_date:
                left_id, left_date = cached_id, cached_date

        # Right pivot..
        right_id, right_date = self.latest_id, datetime.datetime.now().date()
        for cached_date, cached_id in reversed(id_cache):
            if cached_date < date:
                break

            if cached_date < right_date:
                right_id, right_date = cached_id, cached_date

        # Binary search, here we go.
        return self._get_first_id(date, left_date, right_date)

    def _get_dates(self, min_datetime, max_datetime):
        if min_datetime < datetime.date(1999, 9, 30):
            raise ValueError("FOK's oldest articles was posted on 1999-09-30")
        return super(FOKScraper, self)._get_dates(min_datetime, max_datetime)

    def _get_units(self):
        first_date = list(self.dates)[0]
        last_date = list(self.dates)[-1]
        article_id = self.get_first_id(first_date)

        # Consume pages which do not fall in date range
        while self._get_date(article_id) < first_date:
            article_id += 1

        self._dump_id_cache()

        # Begin scraping!
        while self._get_date(article_id) <= last_date:
            yield article_id
            article_id += 1

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
                next_page = self.session.get_html(next_page.get("href"))
                for comment in self.get_comment_elements(next_page):
                    yield comment

    def get_comments(self, headline, url, section, page):
        for comment in self.get_comment_elements(page):
            top_bar = comment.cssselect(".commentTopBar")[0]
            author = top_bar.cssselect(".author a")[0].text.strip()
            text = html2text(comment.cssselect(".commentContent")[0])
            comment_id = comment.get("id")
            user_id = comment.get("data-userid")
            livecomment_id = comment.get("data-livecomment")
            date = parse_comment_date(top_bar.cssselect(".posttime a")[0].text.strip())

            yield {
                "author": author,
                "headline": headline,
                "section": section,
                "text": text,
                "date": date,
                "url": url + "#" + comment_id,
                "metastring": {
                    "author_id": user_id,
                    "comment_id": comment_id,
                    "livecomment_id": livecomment_id
                },
            }

    def _scrape_unit(self, article_id):
        url = ARTILCE_URL.format(**locals())
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
            "text": text,
            "url": url,
            "metastring": {
                "article_id": article_id
            },
            "children": list(self.get_comments(headline, url, section, doc))
        }

    _props = {
        'defaults': {
            'medium': "FOK - Frontpage"
        },
        'required': ['date', 'text', 'headline', 'author'],
        'expected': []
    }
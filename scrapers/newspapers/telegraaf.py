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

import re
import collections
from datetime import date
import itertools

from amcatscraping.scraping.scraper import UnitScraper, DateRangeScraper, LoginMixin, PropertyCheckMixin
from amcatscraping.tools import parse_form, setup_logging


Article = collections.namedtuple("Article", ["article_id", "pagenr", "section", "date"])

ARTICLE_URL = "http://www.telegraaf.nl/telegraaf-i/article/{article_id}"
LOGIN_URL = "http://www.telegraaf.nl/wuz/loginbox/epaper?nocache"
WEEK_URL = "http://www.telegraaf.nl/telegraaf-i/week"


def mkdate(string):
    return date(*map(int, string.split("-")))



class TelegraafScraper(LoginMixin,PropertyCheckMixin,UnitScraper,DateRangeScraper):
    def _login(self, username, password):
        self.session.get(WEEK_URL)

        form = parse_form(self.session.get_html(LOGIN_URL).cssselect("#user-login")[0])
        form.update({
            "name": username, "password": password,
            "rhash": "f8ac71adde5cdb382ab5e485a8c3447210a6b69b",
            "redir": WEEK_URL
        })

        self.session.headers.update({
            "Host": "www.telegraaf.nl",
            "Referer": LOGIN_URL
        })

        return "close-iframe" in self.session.post(LOGIN_URL, form).url

    def _get_units(self):
        data = self.session.get("http://www.telegraaf.nl/telegraaf-i/newspapers").json()
        papers = [paper for paper in data if mkdate(paper['date']) in self.dates]
        for paper in papers:
            for page in paper['pages']:
                for article_id in page['articles']:
                    section = [s['title'] for s in paper['sections'] if page['page_number'] in s['pages']][0]
                    yield Article(article_id, page['page_number'], section, mkdate(paper['date']))

    def _scrape_unit(self, article):
        article_id, pagenr, section, date = article

        if section == "Advertentie":
            return None

        url = ARTICLE_URL.format(article_id=article_id)
        data = collections.defaultdict(str, **self.session.get(url).json())

        article = {
            'url': url, 'metastring': {}, 'pagenr': pagenr,
            'section': section, 'date': date,
            "headline": data.get("headline")
        }

        if not article['headline']:
            return None

        body = dict.fromkeys(itertools.chain.from_iterable(data["body"]), "")

        for dic in data['body']:
            for k, v in dic.items():
                body[k] += v + "\n\n"

        lead = body.get("lead", "")
        byline = body.get("paragraph") or body.get("byline", "")
        article['text'] = lead + byline

        if not article['text']:
            return None

        article['metastring'].update({
            'subheadline': body.get('subheadline'),
            'media_caption': body.get('media-caption')
        })

        for line in article['text'].split("\n\n"):
            if line.startswith("door "):
                article['author'] = line.lstrip("door ")
            
            if re.search('[A-Z ]+, [a-z]+', line):
                article['metastring']['dateline'] = line

        return article

    _props = {
        'defaults': {
            'medium': "De Telegraaf",
            },
        'required': ['url', 'pagenr', 'section', 'text', 'date', 'headline'],
        'expected': ['dateline', 'author']
    }

if __name__ == "__main__":
    setup_logging()
    TelegraafScraper().run()

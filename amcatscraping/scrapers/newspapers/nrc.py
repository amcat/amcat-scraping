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

from datetime import date
from urlparse import urljoin
import lxml.html

from amcatscraping.tools import setup_logging, parse_form
from amcatscraping.scraper import (LoginMixin, PropertyCheckMixin,
                                   UnitScraper, DateRangeScraper)


OVERVIEW_URL = "https://login.nrc.nl/overview"


class NRCScraper(LoginMixin, PropertyCheckMixin, UnitScraper, DateRangeScraper):
    nrc_version = "NN"

    def __init__(self, *args, **kwargs):
        super(NRCScraper, self).__init__(*args, **kwargs)

    def _login(self, username, password):
        login_page = self.session.get(OVERVIEW_URL)
        login_doc = lxml.html.fromstring(login_page.content)
        login_url = login_page.url

        post = parse_form(login_doc.cssselect("#fm1")[0])
        post.update({"username": username, "password": password})

        response = self.session.post(login_url, post)
        return response.url.endswith("/overview")

    def _get_units(self):
        for date in self.dates:
            for doc in self.__getsections(date):
                for a in doc.cssselect("ul.article-links li > a"):
                    yield urljoin(a.base_url, a.get('href'))

    def __getsections(self, date):
        monthminus = date.month - 1
        url1 = "http://digitaleeditie.nrc.nl/digitaleeditie/{self.nrc_version}/{date.year}/{monthminus}/{date.year}{date.month:02d}{date.day:02d}___/section1.html".format(**locals())
        doc1 = self.session.get_html(url1)
        yield doc1
        for a in doc1.cssselect("ul.main-sections li:not(.active) a.section-link"):
            yield self.session.get_html(urljoin(a.base_url, a.get("href")))

    def _scrape_unit(self, url):
        doc = self.session.get_html(url)
        datestr = url.split("/")[7].strip("_")
        location = doc.cssselect("em.location")
        person = doc.cssselect("p.by span.person")
        article = {
            'date': date(*map(int, [datestr[:4], datestr[4:6], datestr[6:]])),
            'headline': doc.cssselect("#MainContent h2")[0].text_content(),
            'section': doc.cssselect("#Content ul.main-sections li.active span")[0].text,
            'pagenr': int(url.split("/")[8].split("_")[1]),
            'author': person and person[0].text_content() or None,
            'text': "\n\n".join([t.text_content() for t in doc.cssselect("em.intro,div.column-left p")]),
            'metastring': {
                'location': location and location[0].text or None,
                'subtitle': "\n".join([h3.text_content() for h3 in doc.cssselect("div.column-left h3")]),
            }
        }

        if article['text']:
            return article

    _props = {
        'defaults': {},
        'required': ['date', 'headline', 'section', 'pagenr', 'text'],
        'expected': ['author']
    }

if __name__ == '__main__':
    setup_logging()
    NRCScraper().run()

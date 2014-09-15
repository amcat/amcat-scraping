from __future__ import unicode_literals, print_function, absolute_import
###########################################################################
#          (C) Vrije Universiteit, Amsterdam (the Netherlands)            #
#                                                                         #
# This file is part of AmCAT - The Amsterdam Content Analysis Toolkit     #
#                                                                         #
# AmCAT is free software: you can redistribute it and/or modify it under  #
# the terms of the GNU Affero General Public License as published by the  #
# Free Software Foundation, either version 3 of the License, or (at your  #
# option) any later version.                                              #
#                                                                         #
# AmCAT is distributed in the hope that it will be useful, but WITHOUT    #
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or   #
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public     #
# License for more details.                                               #
#                                                                         #
# You should have received a copy of the GNU Affero General Public        #
# License along with AmCAT.  If not, see <http://www.gnu.org/licenses/>.  #
###########################################################################

from urllib import urlencode
from urlparse import urljoin
from datetime import datetime, time, timedelta
from hashlib import md5
import re

from amcatscraping.scraping.scraper import Scraper
from amcatscraping.tools import  setup_logging

class MarokkoScraper(Scraper):
    medium_name = "marokko.nl"
    skip_fora = [26,22,43,54,19,11,12,9,13,44,51,36]
    class URLS:
        forums = "http://forums.marokko.nl/"
        forum = "http://forums.marokko.nl/forumdisplay.php?f={forum_id}"
        threadlist = "http://forums.marokko.nl/forumdisplay.php?f={forum_id}&page={page}"
        thread = "http://forums.marokko.nl/showthread.php?t={thread_id}"
        threadpage = "http://forums.marokko.nl/showthread.php?t={thread_id}&page={page}"
        login = "http://forums.marokko.nl/login.php?do=login"

    def _login(self, username, password):
        post = {
            'do' : 'login',
            'securitytoken' : 'guest',
            'cookieuser' : 1,
            'vb_login_md5password' : md5(password).hexdigest(),
            'vb_login_username' : username,
            }
        response = self.session.post(self.URLS.login, data=post)
        if "foutieve gebruikersnaam of wachtwoord" in response.text:
            raise ValueError("login fail")

    def _scrape(self):
        return self.scrape_thread_page(4327526, 1)


    def get_all_threads(self):
        """Return a list of all valid thread ids, iterating over all forums"""
        for forum_id in self.get_forums():
            npages = self.get_npages_forum(forum_id)
            if npages is not None:
                for page in xrange(1, npages):
                    print("Forum {forum_id}, page {page}/{npages}".format(**locals()))
                    for t in self.get_threads(forum_id, page):
                        yield t


    def get_forums(self):
        """Return a list of valid forum ids"""
        html = self.session.get_html(self.URLS.forums)
        for a in html.cssselect(".forumtitle a"):
            m = re.match(r"forumdisplay\.php\?f=(\d+)", a.attrib['href'])
            if not m:
                raise ValueError("Cannot parse ref: {!r}".format(a.attrib['href']))
            yield int(m.group(1))


    def get_npages_forum(self,forum_id):
        """Return the number of pages in this forum"""
        url = self.URLS.forum.format(**locals())
        html = self.session.get_html(self.URLS.forum.format(**locals()))
        lijst = html.cssselect("span > a.popupctrl")
        if lijst:
            return int(lijst[0].text_content().split()[-1])


    def get_threads(self, forum_id, page):
        """Return a list of threads in this forum+page"""
        pdoc = self.session.get_html(self.URLS.threadlist.format(**locals()))
        for li in pdoc.cssselect("li.threadbit:not(.deleted)"):
            href = li.cssselect("a.title")[0].get('href')
            m = re.match("http://forums.marokko.nl/showthread.php?t=\d+", href)
            if not m:
                raise ValueError("Cannot parse {href}".format(**locals()))
            yield int(m.group(1))


    def get_npages_thread(self, thread_id):
        """Return the number of pages in this thread"""
        url = self.URLS.thread.format(**locals())
        doc = self.session.get_html(url)
        span = doc.cssselect("span > a.popupctrl")
        if span:
            return int(span[0].text_content().split()[-1])
        else:
            return 1


    def get_post(self, base_url, thread_id, thread_name, li):
        """Create an 'amcat' article dict from a li element"""
        url = urljoin(base_url, li.cssselect("a.postcounter")[0].get('href'))
        postno = int(li.cssselect("a.postcounter")[0].text_content().strip("#"))
        if postno > 1:
            headline = "{thread_name} [reply #{postno}]".format(**locals())
        else:
            headline = thread_name
        return {
            'headline': headline,
            'date' : _parse_date(li.cssselect("span.date")[0].text_content()).isoformat(),
            'author' : li.cssselect("a.username")[0].text_content().strip(),
            'text' : li.cssselect("blockquote.postcontent")[0].text_content().strip(),
            'page' : postno,
            'children' : [],
            'medium' : self.medium_name,
            'project' : self.options['project'],
            'section' : thread_id,
            'url' : url,
            }


    def scrape_thread_page(self, thread_id, page):
        """Scrape a given page, returning all articles on it"""
        url = self.URLS.threadpage.format(**locals())
        doc = self.session.get_html(url)
        thread_name = doc.cssselect("span.threadtitle")[0].text_content().strip()
        for li in [l for l in doc.cssselect("li")
                   if l.get('id') and l.get('id').startswith("post_")]:
            yield self.get_post(url, thread_id, thread_name, li)



def _parse_date(string):
    date,time = string.split()
    if date == 'Vandaag':
        today = datetime.today()
        day, month, year = today.day, today.month, today.year
    elif date == 'Gisteren':
        yesterday = datetime.today() - timedelta(days = 1)
        day, month, year = yesterday.day, yesterday.month, yesterday.year
    else:
        day, month, year = map(int,date.split("-"))
    hour,minute = map(int,time.split(":"))
    return datetime(year, month, day, hour, minute)




if __name__ == "__main__":
    setup_logging()
    MarokkoScraper().run()

#m = MarokkoScraper()
#m._login("nieuwsmonitor", "sinterklaas")
#posts = m.scrape_thread_page(4327526, 1)
#import json
#print(json.dumps(list(posts)[0], indent=2))

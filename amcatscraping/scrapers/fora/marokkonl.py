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
import os.path
import cPickle as pickle
from amcatscraping.scraping.scraper import Scraper, LoginMixin
from amcatscraping.tools import  setup_logging
import logging
log = logging.getLogger(__name__)

class MarokkoScraper(LoginMixin, Scraper):
    medium_name = "marokko.nl"
    skip_fora = [26,22,43,54,19,11,12,9,13,44,51,36]
    use_fora = [25, 14, 45, 39, 40]
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
            return False
        return True

    def _get_arg_list(self):
        return super(MarokkoScraper, self)._get_arg_list() + [
            ('progress_file', {'type' : str}),
        ]

    def _scrape(self):
        self._do_login()
        #return self.scrape_thread_page(4327526, 1)
        #list(self.scrape_thread_page(5152908, 1))
        progress = self.options['progress_file']
        if os.path.exists(progress):
            with open(progress) as f:
                todo = pickle.load(f)
            log.warn("Loaded todo from {progress}: {n}".format(n=len(todo), **locals()))
        else:
            log.info("Getting list of scraped threads from elastic")
            scraped_posts = self.get_scraped_posts_per_thread()
            log.info("Getting list of threads from forums")
            todo = {}
            for forum_id in self.use_fora:#self.get_forums():
                fn = "/tmp/progress_{forum_id}.pickle".format(**locals())
                if os.path.exists(fn):
                    with open(fn) as f:
                        threads = pickle.load(f)
                else:
                    log.info("Getting list of threads from forum {forum_id}, |todo|={n}"
                             .format(n=len(todo), **locals()))
                    threads = list(self.get_all_threads(forum_id))

                    with open(fn, "w") as f:
                        pickle.dump(threads, f)
                        log.info("Wrote {n} thread ids to {fn}".format(n=len(threads), **locals()))

                for thread_id in threads:
                    todo[thread_id] = scraped_posts.get(thread_id)
            log.warn("Writing todo to {progress}: |todo|={n}".format(n=len(todo), **locals()))
            with open(progress, 'w') as f:
                pickle.dump(todo, f)

        while todo:
            thread_id = max(todo)
            max_scraped = todo.pop(thread_id)
            log.warn("Scraping thread {thread_id} (max={max_scraped})".format(**locals()))
            try:
                posts = list(self.scrape_thread(thread_id, max_scraped))
                if posts:
                    posts = self.set_parent(posts, thread_id)
                    yield posts
            except:
                log.exception("ERROR scraping thread {thread_id}".format(**locals()))

            with open(progress, 'w') as f:
                pickle.dump(todo, f)

    def set_parent(self, posts, thread_id):
        # if post 1 (pagenr==1) is part of posts, add other posts as child
        for post in posts:
            if post['pagenr'] == 1:
                post['children'] = [p for p in posts if p['pagenr'] > 1]
                return post
        # look up first post in this thread on amcat and use that as parent
        r = list(self.api.search(self.articleset, query=None, section=thread_id, page=1, minimal=True))
        if not r:
            raise Exception("Post 1 not in AmCAT but also not scraped?")
        parent_id = r[0]['id']
        result = []
        for post in posts:
            post['parent'] = parent_id
            result.append( post)
        return result


    def scrape_thread(self, thread_id, max_scraped_post):
        for i in range(self.get_npages_thread(thread_id), 0, -1):
            found_new = False
            for p in self.scrape_thread_page(thread_id, i):
                if p['pagenr'] > max_scraped_post:
                    found_new = True
                    yield p
                    # [wva] can't we just 'return' if a non-new post is found??
            if not found_new:
                break



    def get_all_threads(self, forum_id):
        """Return a list of all valid thread ids from a specific forum"""
        i = 0
        npages = self.get_npages_forum(forum_id)
        if npages is not None:
            for page in xrange(1, npages+1):
                if not page % 100:
                    log.info("Forum {forum_id}, page {page}/{npages}, i={i}".format(**locals()))
                for t in self.get_threads(forum_id, page):
                    i += 1
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
        html = self.session.get_html(url)
        lijst = html.cssselect("span > a.popupctrl")
        if lijst:
            return int(lijst[0].text_content().split()[-1])


    def get_threads(self, forum_id, page):
        """Return a sequence of threads in this forum+page"""
        url = self.URLS.threadlist.format(**locals())
        pdoc = self.session.get_html(url)
        lis = pdoc.cssselect("li.threadbit:not(.deleted)")
        #log.info("forum {forum_id}.{page}: {n} ({url})".format(n=len(lis), **locals()))
        for li in lis:
            href = li.cssselect("a.title")[0].get('href')
            m = re.match(r"showthread.php\?t=(\d+)", href)
            if not m:
                raise ValueError("Cannot parse {href!r}".format(**locals()))
            yield int(m.group(1))


    def get_npages_thread(self, thread_id):
        """Return the number of pages in this thread"""
        url = self.URLS.thread.format(**locals())
        doc = self.session.get_html(url)
        span = doc.cssselect("span > a.popupctrl")
        if span and span[0].text_content().split():
            return int(span[0].text_content().split()[-1])
        else:
            return 1


    def get_scraped_posts_per_thread(self):
        """Get the max(post) per thread that has already been scraped"""
        return {int(row['section']): row['max'] 
                for row in self.api.aggregate(sets=self.options['articleset'], axis1="section", stats="page")}

    def get_post(self, base_url, thread_id, thread_name, li):
        """Create an 'amcat' article dict from a li element"""
        url = urljoin(base_url, li.cssselect("a.postcounter")[0].get('href'))
        postno = int(li.cssselect("a.postcounter")[0].text_content().strip("#"))
        if postno > 1:
            headline = "{thread_name} [reply #{postno}]".format(**locals())
        else:
            headline = thread_name
        post = {
            'headline': headline,
            'date' : _parse_date(li.cssselect("span.date")[0].text_content()).isoformat(),
            'author' : li.cssselect("a.username")[0].text_content().strip(),
            'text' : li.cssselect("blockquote.postcontent")[0].text_content().strip(),
            'pagenr' : postno,
            'children' : [],
            'medium' : self.medium_name,
            'project' : self.options['project'],
            'section' : thread_id,
            'url' : url,
            }
        for f in ('text', 'headline'):
            if not post[f]: post[f] = "(missing)"
        return post

    def scrape_thread_page(self, thread_id, page):
        """Scrape a given page, returning all articles on it"""
        url = self.URLS.threadpage.format(**locals())
        doc = self.session.get_html(url)
        thread_name = doc.cssselect("span.threadtitle")[0].text_content().strip()
        for li in [l for l in doc.cssselect("li:not(.postbitdeleted)")
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

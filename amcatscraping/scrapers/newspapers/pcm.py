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

import datetime
import base64
import pprint
import uuid
import logging
from typing import Any, Tuple

import pyamf

from pyamf import remoting
from pyamf.flex import messaging

from amcat.models import Article

from amcatscraping.scraper import LoginMixin, UnitScraper, DateRangeScraper
from amcatscraping.tools import parse_form

log = logging.getLogger(__name__)

# Login page
LOGINURL = "https://caps.{domain}/service/web/authentication?client_id=caps-{caps_code}&redirect_uri={login_redirect}"
AUTHURL = "https://caps.{domain}/service/validate?service="
SAVEURL = "http://krant.%(domain)s/ipaper-online/saveLoginHistory?zone=%(regio_code)s&pubId=%(main_id)s&method=CAPS&paperId=%(paper_id)s&login=%(username)s"
TICKET = "SSO_{paper_id}:http://krant.{domain}/@{code}"

# AMF API page
AMFURL = "http://krant.{domain}/ipaper-online/blaze/amf"

# Text displayed when login successfull
LOGIN_SUCCESS = "Log In Successful"

# Generate a valid uuid for an AMF object
uuid4 = lambda: str(uuid.uuid4()).upper()


# Convienience function
def get_pubdate(paper):
    pd = dict([(k, int(v)) for k, v in paper['pubDate'].items()])
    pd['month'] += 1
    return datetime.date(**pd)


class PCMScraper(LoginMixin, UnitScraper, DateRangeScraper):
    paper_id = None
    context_id = None
    domain = None
    caps_code = None
    login_redirect = None

    def __init__(self, *args, **kwargs):
        self.client_id = uuid4()
        self.headers = {
            'DSMessagingVersion': 1,
            'DSId': 'nil'
        }

        if self.publisher is None:
            raise ValueError("Subclasses should set publisher name")

        super(PCMScraper, self).__init__(*args, **kwargs)

    def login(self, username, password):
        """
        Parse login form and fill in wanted parts
        """
        # Get latest paper id
        latest = self._get_latest()
        latest = latest[(sorted(latest.keys())[-1])]
        paper_id = int(latest['paperId'])

        # Build url
        url = LOGINURL.format(paper_id=paper_id,
                              regio_code=self.context_id,
                              domain=self.domain,
                              caps_code=self.caps_code,
                              login_redirect=self.login_redirect)

        # Login
        login_page = self.session.get_html(url)

        form = parse_form(login_page)
        form['email'] = username
        form['password'] = password
        form['remember_me'] = True

        login_page = self.session.post(url, json=form)
        if login_page.status_code != 200:
            raise Exception("Login page not loaded ({login_page.status_code}): {url}".format(**locals()))
        res = login_page.json()
        access_token, code = res['access_token'], res['code']

        # Handshake server
        com = self.create_message(messaging.CommandMessage, operation=5)
        req = self.create_request(com)
        env = self.create_envelope(req)
        res = self.apiget(env).bodies[0][1]

        self.headers.update(res.body.headers)

        # Send AMF Auth message to server
        # Note: we now have two paper_ids, a static self.paper_id (ie 8002) and dynamic paper_id (id 64774)
        ticket = TICKET.format(paper_id=self.paper_id, domain=self.domain, code=code)
        com = self.create_message(messaging.CommandMessage, operation=8)
        com.destination = 'auth'
        com.body = base64.b64encode(ticket.encode())

        com.headers["DSEndpoint"] = "_IPaperOnlineServiceLocator_AMFChannel1"
        com.correlationId = ""

        env = self.create_envelope(self.create_request(com))
        res = self.apiget(env)

        return "ErrorMessage" not in str(res)

    def get_units(self):
        latest = self._get_latest()
        for date in self.dates:
            page = latest.get(date)
            if page is None:
                continue

            pid = int(page['paperId'])
            paper = self._get_paper(pid, date)
            for index in paper:
                for art in index['doc']['articles']:
                    if not (art['title'] and art['title'].strip()):
                        continue

                    url = "{}?id={}".format(index["doc"]["highresUrl"], art["id"])
                    yield (index, art, url, date)

    def get_url_and_date_from_unit(self, unit: Any) -> Tuple[str, datetime.date]:
        index, art, url, date = unit
        return url, date

    def scrape_unit(self, index__art):
        index, art, url, date = index__art
        date = index["date"]

        article = Article(url=url)
        article.set_property('author', art['author'][:100] if art['author'] else '')
        article.set_property('title', art['title'])
        article.set_property('text', "\n\n".join([el['text'] for el in art['bodyElements']]))
        article.set_property('section', index['section'])
        article.set_property('pagenr_int', index['pagenr'])
        article.set_property('date', datetime.datetime(date.year, date.month, date.day))

        if article.text and article.title:
            return article

    def _get_latest(self):
        """
        Get latest newspapers
        """
        rmsg = self.create_message(
            messaging.RemotingMessage,
            operation="getHome", body=[self.paper_id],
            destination="onlineFacade"
        )

        req = self.create_request(rmsg)
        env = self.create_envelope(req)
        resp = self.apiget(env).bodies[0][1].body  # .body['homePapers']

        if isinstance(resp, messaging.ErrorMessage):
            # Session was not cleared. Try again..
            return self._get_latest()

        # Create date:paper dictionary and check for date
        return dict([(get_pubdate(p), p) for p in resp.body['homePapers']])

    def apiget(self, envelope):
        """
        Communicate with API.

        @type envelope: pyamf.remoting.Envelope
        @param envelope: request

        @return: decoded AMF stream
        """
        data = bytes(remoting.encode(envelope).read())
        url = AMFURL.format(domain=self.domain)

        resp = remoting.decode(
            self.session.get(url, data=data, headers={'Content-Type': 'application/x-amf'}).content
        )

        return resp

    def create_envelope(self, *requests):
        """
        Create AMF Envelope object with embedded requests.
        """
        env = remoting.Envelope(amfVersion=pyamf.AMF3)
        env.bodies = []

        for i, req in enumerate(requests):
            env.bodies.append(("/%s" % (i + 1), req))

        return env

    def create_request(self, *messages):
        """
        Create MAF Request object and embed given
        messages.
        """
        return remoting.Request("null", body=messages)

    def create_message(self, msgtype, **args):
        """
        Creates message and sets messageId, clientId and
        given keyword arguments. For documentation see:

            http://api.pyamf.org/0.6.1/pyamf.flex.messaging.\
            AbstractMessage-class.html

        Example:

            msg = self.create_message(
                pyamf.flex.messaging.RemotingMessage,
                operation="getHome"
            )
        """
        msg = msgtype(messageId=uuid4(), clientId=self.client_id, **args)
        msg.headers.update(self.headers)
        return msg

    def _get_paper(self, paper_id, date):
        rmsg = self.create_message(
            messaging.RemotingMessage,
            operation="getPaper",
            body=[self.paper_id, paper_id, self.context_id],
            destination="onlineFacade"
        )

        env = self.create_envelope(self.create_request(rmsg))
        resp = self.apiget(env).bodies[0][1]

        for spread in resp.body.body['spreads']:
            for page in [spread.get(p) for p in ('leftPage', 'rightPage')]:
                if page is None: continue
                index = {}
                index['date'] = date
                index['section'] = page.get('section')
                index['pagenr'] = page.get('nr')
                index['doc'] = page

                yield index

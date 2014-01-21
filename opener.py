"""Class to deal with http browsing"""

import urllib2
from lxml import html
from httplib2 import iri2uri
from urlparse import urljoin
from urllib  import urlencode
import cookielib

import logging; log = logging.getLogger(__name__)

class Opener(object):
    def __init__(self):
        # Construct a urllib2 opener
        self.cookiejar = cookielib.CookieJar()
        self.opener = urllib2.build_opener(
            urllib2.HTTPCookieProcessor(self.cookiejar),
            urllib2.HTTPRedirectHandler(),
            urllib2.UnknownHandler(),
            )

    def open(self, url, data = None):
        url = iri2uri(url).strip()
        if data:
            data = urlencode(data)
        log.info("opening {url}".format(**locals()))
        return self.opener.open(url, data)

    def open_html(self, url, data = None):
        """Open url and parse into lxml.HTML object"""
        response = self.open(url, data)
        return html.parse(response).getroot()

    def navigate_html(self, anchor):
        """Follows a link"""
        destination = urljoin(anchor.base_url, anchor.get('href'))
        return self.open_html(destination)

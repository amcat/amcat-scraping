"""Class to deal with http browsing"""

import urllib2
from lxml import html
from httplib2 import iri2uri
from urlparse import urljoin
from urllib  import urlencode
import cookielib

import logging; log = logging.getLogger(__name__)

class Browser:
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
        logging.info("opening {url}".format(**locals()))
        return self.opener.open(url, data)

    def getdoc(self, url, data = None):
        response = self.open(url, data)
        return html.parse(response).getroot()

    def navigate(self, anchor):
        """Follows a link"""
        destination = urljoin(a.base_url, a.get('href'))
        return self.getdoc(destination)

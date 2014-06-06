"""Class to deal with http browsing"""

from lxml import html
from httplib2 import iri2uri
from urlparse import urljoin
import requests

import logging; log = logging.getLogger(__name__)

class Session(requests.Session):
    """Provides a HTTP session, HTML parsing and a few convenience methods"""
    def get_html(self, url_or_anchor, *args, **kwargs):
        """Open url or follow <a> tag and parse into lxml.HTML object"""
        response = self.get(url_or_anchor, *args, **kwargs)
        doc = html.fromstring(response.text.encode('utf-8'))
        doc.url = response.url
        return doc

    def get(self, url_or_anchor, *args, **kwargs):
        if not type(url_or_anchor) in (unicode, str):
            url_or_anchor = urljoin(url_or_anchor.base_url, url_or_anchor.get('href'))
        url_or_anchor = url_or_anchor.strip()
        return super(Session, self).get(url_or_anchor, *args, **kwargs)



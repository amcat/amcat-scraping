"""Class to deal with http browsing"""

from lxml import html
from urlparse import urljoin
import requests

import logging; log = logging.getLogger(__name__)

class Session(requests.Session):
    """Provides a HTTP session, HTML parsing and a few convenience methods"""
    def get_html(self, link, *args, **kwargs):
        """Open url or follow <a> tag and parse into lxml.HTML object"""
        response = self.get(link, *args, **kwargs)
        doc = html.fromstring(response.text.encode('utf-8'), base_url = response.url)
        return doc

    def get(self, link, *args, **kwargs):
        #link: an url or an <a> tag
        if not type(link) in (unicode, str):            
            link = urljoin(link.base_url, link.get('href'))
        return super(Session, self).get(link.strip(), *args, **kwargs)



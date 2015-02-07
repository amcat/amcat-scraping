"""Class to deal with http browsing"""

import lxml.html
import requests


class Session(requests.Session):
    """Provides a HTTP session, HTML parsing and a few convenience methods"""
    def __init__(self):
        super(Session, self).__init__()
        self.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 6.3; rv:36.0) Gecko/20100101 Firefox/36.0"
        })

    def get_html(self, link, **kwargs):
        return lxml.html.fromstring(self.get(link, **kwargs).content)

    def get(self, link, **kwargs):
        return super(Session, self).get(link.strip(), **kwargs)



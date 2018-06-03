###########################################################################
# (C) Vrije Universiteit, Amsterdam (the Netherlands)                     #
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
import os
import lxml
import datetime
import logging
import requests
import cssselect
import readability
import string

from multiprocessing.pool import ThreadPool

from amcat.models import Article
from amcatscraping.scraper import DeduplicatingUnitScraper
from amcatscraping.tools import html2text

from urllib.parse import urljoin


log = logging.getLogger(__name__)

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BLOCKLIST = os.path.join(THIS_DIR, "fanboy-annoyance.txt")
CONTROL_RE = re.compile("[\x00-\x08\x0b\x0e-\x1f\x7f]")


# https://github.com/buriy/python-readability/issues/43
class AdRemover:
    """
    This class applies elemhide rules from AdBlock Plus to an lxml
    document or element object. One or more AdBlock Plus filter
    subscription files must be provided.

    Example usage:

    >>> import lxml.html
    >>> remover = AdRemover('fanboy-annoyance.txt')
    >>> doc = lxml.html.document_fromstring("<html>...</html>")
    >>> remover.remove_ads(doc)
    """

    def __init__(self, *rules_files):
        if not rules_files:
            raise ValueError("one or more rules_files required")

        self.rules_files = rules_files

    def get_chunked_rules(self, chunk_size=50):
        translator = cssselect.HTMLTranslator()
        rules = set()

        for rules_file in self.rules_files:
            with open(rules_file, 'r') as f:
                for line in f:
                    line = line.strip()

                    # elemhide rules are prefixed by ## in the adblock filter syntax
                    if line[:2] == '##':
                        try:
                            xpath = translator.css_to_xpath(line[2:])
                            xpath = re.sub(CONTROL_RE, "", xpath)
                            rules.add(xpath)
                        except cssselect.SelectorError:
                            # just skip bad selectors
                            pass

                    if len(rules) >= chunk_size:
                        yield "|".join(rules)
                        rules.clear()

        # create one large query by joining them the xpath | (or) operator
        #self.xpath_query = '|'.join(rules)


    def remove_ads(self, tree):
        """Remove ads from an lxml document or element object.

        The object passed to this method will be modified in place."""
        matched = []

        rules = self.get_chunked_rules()
        with ThreadPool() as pool:
            for i, elems in enumerate(pool.imap(tree.xpath, rules)):
                for elem in elems:
                    matched.append(elem)

        for elem in matched:
            elem.getparent().remove(elem)


class GenericScraper(DeduplicatingUnitScraper):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.adbock_enabled = self.options.get("enable_adblock", "false") in ("true", "1", "yes")
        self.index_url = self.options["index_url"]
        self.article_url_re = re.compile(self.options["article_url"])
        self.adblocker = AdRemover(BLOCKLIST)
        self.publisher = self.options["publisher"]
        self.now = datetime.datetime.now()
        self.remove_elements = self.options.get("remove_elements")

    def get_html(self, url, *args, **kwargs):
        doc = self.session.get_html(url, *args, **kwargs)
        if self.remove_elements:
            for element in doc.cssselect(self.remove_elements):
                element.getparent().remove(element)
        if self.adbock_enabled:
            self.adblocker.remove_ads(doc)
        return doc

    def get_deduplicate_key_from_unit(self, unit) -> str:
        return unit

    def get_deduplicate_key_from_article(self, article: Article) -> str:
        return article.url

    def get_deduplicate_units(self):
        index = self.get_html(self.index_url)

        for a in index.cssselect("a"):
            absolute_url = urljoin(self.index_url, a.get("href"))
            if self.article_url_re.search(absolute_url):
                yield absolute_url

    def scrape_unit(self, url):
        html = lxml.etree.tostring(self.get_html(url))
        doc = readability.Document(html)
        candidates = doc.score_paragraphs()
        best_candidate = doc.select_best_candidate(candidates)
        article_doc = doc.get_article(candidates, best_candidate)
        article_html = lxml.etree.tostring(article_doc, pretty_print=True).decode()
        text = html2text(article_html)
        short_title = doc.short_title()

        article = Article(date=self.now, title=short_title, text=text, url=url)

        return article


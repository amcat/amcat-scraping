import collections
from html2text import html2text
import lxml.html
from urlparse import urljoin

from amcatscraping.tools import setup_logging, parse_form
from amcatscraping.scraping.scraper import (LoginMixin, PropertyCheckMixin,
                                            UnitScraper, DateRangeScraper)


LOGIN_URL = "https://fd.nl/login"
DIGIKRANT_BASE_URL = "http://fd.nl/digikrant"
DIGIKRANT_URL = "http://digikrant.fd.nl/%Y%m%d/public/"

SectionEntry = collections.namedtuple("SectionEntry", ["section", "subsection", "pagenr", "date", "url"])


def parse_section_url(date, section_url):
    base_url = date.strftime(DIGIKRANT_URL)
    return urljoin(base_url, section_url.replace("%PATH%", "/public")) + ".html"


class FDScraper(LoginMixin, PropertyCheckMixin, UnitScraper, DateRangeScraper):
    def _login(self, username, password):
        login_page = self.session.get(LOGIN_URL)
        login_doc = lxml.html.fromstring(login_page.content)
        login_form = login_doc.cssselect("form.login")[0]
        login_post_url = login_form.get("action")
        login_fail_url = login_form.cssselect("input[name=failureUrl]")[0].get("value")

        # Login
        post_data = parse_form(login_form)
        post_data.update({"username": username, "password": password})
        response = self.session.post(login_post_url, post_data)

        # Set right cookies
        self.session.get(DIGIKRANT_BASE_URL)

        # Check if logging in worked :)
        return response.url != login_fail_url

    def _get_section_table(self, page):
        return (line.strip() for line in page if line.strip().startswith("sectionTable.add"))

    def _get_sections(self, date):
        # Sections are defined in javascript, like so:
        # sectionTable.add('Katern 3', 'Outlook', '1', '/pages/07001/FD-07-001-20150207');
        frontpage = self.session.get(date.strftime(DIGIKRANT_URL)).content
        for section in self._get_section_table(frontpage.split("\n")):
            section_tuple = section.lstrip("sectionTable.add(").rstrip(");").replace("'", "")
            section, subsection, pagenr, url = section_tuple.split(", ")
            yield SectionEntry(section, subsection, pagenr, date, parse_section_url(date, url))

    def _get_articles(self, entry):
        page_doc = self.session.get_html(entry.url)

        page_map = page_doc.cssselect("map[name=pagemap]")[0]
        for area in page_map.cssselect("area"):
            _, url, _ = area.get('onclick').split("'")
            yield "%s_body.html" % urljoin(entry.url, url).rstrip(".html")


    def _get_units(self):
        for date in self.dates:
            for entry in self._get_sections(date):
                for article_url in set(self._get_articles(entry)):
                    _entry = collections.OrderedDict(entry._asdict(), url=article_url)
                    yield SectionEntry(*_entry.values()), self.session.get_html(article_url)
            break

    def _scrape_unit(self, entry_and_article):
        entry, article = entry_and_article

        text = article.cssselect("td > font.artbody")[1:]
        text = map(html2text, map(lxml.html.tostring, text))
        text = "\n\n".join(p.replace("\n", "") for p in text)

        article_properties = {
            "headline": article.cssselect("title")[0].text,
            "text": text
        }

        author = article.cssselect(".artauthor")
        if author:
            article_properties["author"] = author[0].text.split(":")[1].strip()

        article_properties.update(entry._asdict())

        if article_properties["text"].strip():
            return article_properties

    _props = {
        'defaults': {
            'medium': 'Financieel Dagblad',
            'insertscript': 'FDScraper'
        },
        'required': ['subsection', 'date', 'headline', 'section', 'pagenr', 'text'],
        'expected': []
    }


if __name__ == '__main__':
    setup_logging()
    FDScraper().run()

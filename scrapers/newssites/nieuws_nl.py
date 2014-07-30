from lxml import html
import logging; log = logging.getLogger(__name__)

from amcatscraping.scraping.scraper import UnitScraper, DateRangeScraper, PropertyCheckMixin
from amcatscraping.tools import setup_logging, read_date, todate, html2text

class NieuwsNLScraper(PropertyCheckMixin, UnitScraper, DateRangeScraper):
    def _get_units(self):
        index = self.session.get_html("http://www.nieuws.nl")
        for s_anchor in index.cssselect("a.menuMainItem"):
            sectionname = s_anchor.text
            print('')
            log.info(sectionname)
            for a in self.__get_section_units(s_anchor.get('href')):
                url = a.get('href')
                datetime = read_date(a.cssselect("span.time")[0].text_content())
                if self.mindatetime <= datetime <= self.maxdatetime:
                    yield {'url' : url,
                           'date' : datetime,
                           'section' : sectionname}
                elif self.mindatetime > datetime:
                    break

    def __get_section_units(self, url):
        urlformat = url+"?ajax=1&after={}&ajax=1"
        content = self.session.get_html(url)
        while True:
            for a in content.cssselect("div.border a.article"):
                yield a

            hash = content.cssselect("#nextPage")[0].get('data-after')
            url = urlformat.format(hash)
            data = self.session.get(url).json()
            content = html.fromstring(data['content']['div#nextPage'])

    def _scrape_unit(self, article):
        doc = self.session.get_html(article['url'])
        article['headline'] = doc.cssselect("div.intro h1")[0].text
        article['text'] = html2text(
            doc.cssselect("div.intro h2") + doc.cssselect("div.text"))
        if doc.cssselect("span.author"):
            article['author'] = doc.cssselect("span.author"
            )[0].text.split("Door:")[1]

    _props = {
        'defaults' : {'medium':'nieuws.nl'},
        'required' : ['text','headline','section','date','url'],
        'expected' : ['author']
    }


if __name__ == "__main__":
    setup_logging()
    NieuwsNLScraper().run()

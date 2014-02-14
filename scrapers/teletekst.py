from amcatscraping.scraping.scraper import UnitScraper, OpenerMixin, PropertyCheckMixin
from amcatscraping.scraping import tools

class TeletekstScraper(OpenerMixin, PropertyCheckMixin, UnitScraper):
    def _get_units(self):
        self.open("http://nos.nl")
        self.open("http://cookies.publiekeomroep.nl/accept/")
        for item in self.open_html("http://feeds.nos.nl/nosnieuws").cssselect("item")[:1]:
            yield item.cssselect("link")[0].tail

    def _scrape_unit(self, url):
        doc = self.open_html(url)
        article = {
            'url' : url,
            'text' : tools.html2text(doc.cssselect("#article-content p")),
            'headline' : doc.cssselect("#article h1")[0].text_content().strip(),
            'date' : tools.read_date(doc.cssselect("abbr.page-last-modified")[0].text),
            'externalid' : int(url.split("/")[-1].split("-")[0])}
        return article

    _props = {
        'defaults' : {'medium' : "NOS Teletekst"},
        'required' : ['url', 'headline', 'text', 'date', 'externalid'],
        'expected' : []}
    

if __name__ == "__main__":
    from amcatscraping.scraping.tools import setup_logging
    setup_logging()
    TeletekstScraper().run()

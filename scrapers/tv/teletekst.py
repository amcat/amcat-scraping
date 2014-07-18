from amcatscraping.scraping.scraper import UnitScraper, PropertyCheckMixin
from amcatscraping.scraping import tools

class TeletekstScraper(PropertyCheckMixin, UnitScraper):
    def _get_units(self):
        self.session.get("http://nos.nl")
        self.session.get("http://cookies.publiekeomroep.nl/accept/")
        for item in self.session.get_html("http://feeds.nos.nl/nosnieuws").cssselect("item")[:-1]:
            yield tools.urljoin("http://nos.nl", item.cssselect("link")[0].tail)

    def _scrape_unit(self, url):
        doc = self.session.get_html(url)
        article = {
            'url' : doc.base_url,
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

from amcatscraping.scraper import QualityScraper
from amcatscraping import tools

class TeletekstScraper(QualityScraper):
    medium_name = "NOS Teletekst"
    def _get_units(self):
        self.browser.open("http://nos.nl")
        self.browser.open("http://cookies.publiekeomroep.nl/accept/")
        for item in self.browser.getdoc("http://feeds.nos.nl/nosnieuws").cssselect("item"):
            yield item.cssselect("link")[0].tail

    def _scrape_unit(self, url):
        doc = self.browser.getdoc(url)
        article = {
            'url' : url,
            'text' : tools.html2text(doc.cssselect("#article-content p")),
            'headline' : doc.cssselect("#article h1")[0].text_content().strip(),
            'date' : tools.read_date(doc.cssselect("abbr.page-last-modified")[0].text)
            'externalid' : int(url.split("/")[-1].split("-")[0])}
        return article
            
    _properties = {
        'all' : ['url','headline','text','date','externalid'],
        'some' : []
        }

if __name__ == "__main__":
    from amcat.scripts.tools import cli
    cli.run_cli(TeletekstScraper)

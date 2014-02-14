from amcatscraping.scraping.scraper import UnitScraper, DateRangeScraper, LoginMixin, OpenerMixin, PropertyCheckMixin
from amcatscraping.scraping.tools import parse_form, html2text
from urllib import urlencode
from urlparse import urljoin

class TelegraafScraper(LoginMixin,OpenerMixin,PropertyCheckMixin,UnitScraper,DateRangeScraper):
    def _login(self, username, password):
        login_url = "https://telegraaf-i.telegraaf.nl/telegraaf/_main_/{y}/{m:02d}/{d:02d}/001/page.html"
        login_url_2 = "https://telegraaf-i.telegraaf.nl/tmg/login.php"
        login_url = login_url.format(
            y=self.options['first_date'].year,
            m=self.options['first_date'].month,
            d=self.options['first_date'].day)
        pagel = self.open_html(login_url)
        form = parse_form(pagel)
        form["sso:field:username"] = username
        form["sso:field:password"] = password
        pagel = self.open(login_url_2, form)
        if pagel.getcode() == 200:
            return True

    def _get_units(self):
        """
        @type date: datetime.date, datetime.datetime
        @param date: date to scrape for.
        """
        index_url = "https://telegraaf-i.telegraaf.nl/telegraaf/_main_/%(year)d/%(month)02d/%(day)02d/001"
        for date in self.dates:
            index = index_url % dict(year=date.year, month=date.month, day=date.day)
            doc = self.open_html(index)
            self.categories = self.get_categories(doc)
            for td in doc.cssselect('td.select_page option'):
                url = urljoin(index, td.get('value') + '/page.html')
                doc = self.open_html(url)
                # Articles with an id higher than 100 are advertisements,
                # which can be filtered by excluding classnames lager than
                # 9 (articleXXX).
                articles = doc.cssselect('#page div')
                articles = set(div.get('class') for div in articles
                               if len(div.get('class')) <= 9)
                for clsname in articles:
                    yield (date, urljoin(url,"article/%s.html" % clsname[7:]))

    def get_categories(self, doc):
        borders = {}
        for a in doc.cssselect("td.nav tr")[1].cssselect("a"):
            try:
                pagenr = int(a.get('href').split("/")[-1])
            except AttributeError:
                #some html fail
                continue
            cat = a.text_content()
            borders[pagenr] = cat
        categories = {}
        cat = borders[1]
        for td in doc.cssselect('td.select_page option'):
            pagenr = int(td.get('value'))
            if pagenr in borders.keys():
                cat = borders[pagenr]
            categories[pagenr] = cat
        return categories

    def _scrape_unit(self, date_url):
        date, url = date_url
        article = {'metastring' : {}}
        article['url'] = url
        pagedoc = self.open_html(article['url'])
        article['pagenr'] = int(url.split("/")[-3])
        article['section'] = self.categories[article['pagenr']]
        article['text'] = html2text(pagedoc.cssselect('#article .body p'))
        article['date'] = date
        if pagedoc.cssselect("#article p.dateline"):
            article['dateline'] = pagedoc.cssselect("#article p.dateline")[0].text_content()
        if pagedoc.cssselect("#article .kicker"):
            article['metastring']['kicker'] = pagedoc.cssselect("#article .kicker")[0].text_content()
        if pagedoc.cssselect("#article address"):
            article['author'] = pagedoc.cssselect("#article address")[0].text_content().strip().lstrip("dor").strip()
        if pagedoc.cssselect('#article h1'):
            article['headline'] = pagedoc.cssselect('#article h1')[0].text_content()
            if len(article['text']) < 300:
                return
            return article

    _props = {
        'defaults' : {
            'medium' : "De Telegraaf",
            'insertscript' : 'TelegraafScraper'},
        'required' : ['url','pagenr','section','text','date','headline'],
        'expected' : ['dateline','metastring','author']
        }

if __name__ == "__main__":
    from amcatscraping.scraping.tools import setup_logging
    setup_logging()
    TelegraafScraper().run()

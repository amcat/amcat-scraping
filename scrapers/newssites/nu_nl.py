from datetime import timedelta

from amcatscraping.scraping.scraper import UnitScraper, DateRangeScraper, PropertyCheckMixin
from amcatscraping.scraping.tools import read_date, html2text, setup_logging

import random, string
def id_generator(length, chars = string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(length))

class NuScraper(PropertyCheckMixin, UnitScraper, DateRangeScraper):
    def _get_units(self):
        # The search results show a 'last edited' date. Sometimes, 
        # this is a day off the publication date, however we can only
        # find the pubdate by following the link.
        # we yield all articles that might fall in our date range
        # then check in _scrape_unit
        self._set_js_cookies()
        checkdates = self.dates + [max(self.dates) + timedelta(days = x) for x in range(3)]
        pagenr = 0
        while True:
            pagenr += 1
            doc = self.session.get_html("http://www.nu.nl/zoeken/?q=&page={}".format(pagenr))
            assert doc.cssselect("#searchlist")
            for div in doc.cssselect("#searchlist div.subarticle"):
                date = read_date(div.cssselect("span.date")[0].text)
                if date.date() in checkdates:
                    yield div.cssselect("a")[0].get('href')
                elif date.date() < min(self.dates):
                    return
            assert pagenr < 1000000 # infinite loop

    def _set_js_cookies(self):
        idlength = 10
        self.session.cookies.update({
            'SanomaWebSession' : id_generator(idlength),
            'SanomaWeb' : id_generator(idlength)
        })

    def _scrape_unit(self, url):
        doc = self.session.get_html(url)
        date_txt = doc.cssselect("div.dateplace-data")[0].text
        date = read_date(date_txt)
        if not date.date() in self.dates:
            return
        hours, minutes = map(int,date_txt.split()[-1].split(":"))
        date += timedelta(hours = hours, minutes = minutes)

        content = doc.cssselect("#leadarticle")[0]
        article = {
            'text' : html2text(content.cssselect("div.content")),
            'headline' : content.cssselect("h1")[0].text,
            'section' : url.split("/")[4],
            'date' : date,
            'url' : url,
            }
        if content.cssselect("span.smallprint"):
            article['author'] = content.cssselect("span.smallprint"
            )[-1].text.split(":")[1].strip()
        return article

    _props = {
        'defaults' : {'medium':"nu.nl"},
        'required' : ['text','headline','section','date','url'],
        'expected' : ['author']
    }


if __name__ == "__main__":
    setup_logging()
    NuScraper().run()

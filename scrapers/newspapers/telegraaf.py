from amcatscraping.scraping.scraper import UnitScraper, DateRangeScraper, LoginMixin, PropertyCheckMixin
from amcatscraping.tools import parse_form, setup_logging()
import re

from datetime import date
def mkdate(string):
    return date(*map(int,string.split("-")))


class TelegraafScraper(LoginMixin,PropertyCheckMixin,UnitScraper,DateRangeScraper):
    def _login(self, username, password):
        login_url = "http://www.telegraaf.nl/wuz/loginbox/epaper?nocache"
        week_url = "http://www.telegraaf.nl/telegraaf-i/week"        
        self.session.get(week_url) # set session cookies

        form = parse_form(self.session.get_html(login_url).cssselect("#user-login")[0])
        form['name'], form['pass'] = username, password
        form['rhash'], form['redir'] = "f8ac71adde5cdb382ab5e485a8c3447210a6b69b", week_url

        self.session.headers.update({"Host":"www.telegraaf.nl","Referer":login_url})
        response = self.session.post(login_url, form)
        if "close-iframe" in response.url:
            return True

    def _get_units(self):
        data = self.session.get("http://www.telegraaf.nl/telegraaf-i/newspapers").json()
        papers = [paper for paper in data if mkdate(paper['date']) in self.dates]
        for paper in papers:
            for page in paper['pages']:
                for article_id in page['articles']:
                    section = [s['title'] for s in paper['sections'] if page['page_number'] in s['pages']][0]
                    yield (article_id, page['page_number'],section,mkdate(paper['date']))

    def _scrape_unit(self, (article_id, pagenr, section, date)):
        if section == "Advertentie":
            return
        url = "http://www.telegraaf.nl/telegraaf-i/article/" + article_id
        article = {'url' : url,'metastring' : {},'pagenr' : pagenr,
                   'section' : section, 'date' : date}
        data = self.session.get(url).json()
        article['headline'] = data['headline']
        if not article['headline']:
            return

        body = {k : "" for dic in data['body'] for k in dic}
        for dic in data['body']:
            for k, v in dic.items():
                if not body[k]: body[k] = v
                else: body[k] += "\n\n" + v
            
        article['text'] = body.get('lead') or "" + (body.get('paragraph') or body.get('byline') or "")
        if not article['text']:
            return
        article['metastring'].update({'subheadline' : body.get('subheadline'),
                                      'media_caption' : body.get('media-caption')})
        for line in article['text'].split("\n\n"):
            if line.startswith("door "):
                article['author'] = line.lstrip("door ")
            
            if re.search('[A-Z ]+, [a-z]+', line):
                article['metastring']['dateline'] = line

        return article

    _props = {
        'defaults' : {
            'medium' : "De Telegraaf",
            },
        'required' : ['url','pagenr','section','text','date','headline'],
        'expected' : ['dateline','author']
        }

if __name__ == "__main__":
    setup_logging()
    TelegraafScraper().run()

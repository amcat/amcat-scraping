

from urlparse import urljoin
from cStringIO import StringIO
import ftplib, datetime, threading
from contextlib import contextmanager

from xml.sax.saxutils import unescape
import logging, os
log = logging.getLogger(__name__)

from amcat.tools.stl import STLtoText
from amcat.models import Article
from amcat.models import Scraper

from amcatscraping.scraping.scraper import UnitScraper, OpenerMixin, PropertyCheckMixin

import sys


def getDate(fn):
    datestring = fn.split('/')[1].split('.txt')[0].split('-')
    timestring = datestring[3].split(',')
    date = datetime.datetime(int(datestring[0]),int(datestring[1]),int(datestring[2]),int(timestring[0]),int(timestring[1]))
    return date

def asURL(string):
    url = "file://{url}".format(url=string)
    return url

def getUrlsFromSet(setid, check_back=30):
    """Returns list with all URLS of articles in the articleset for the last [check_back] days"""
    fromdate = (datetime.date.today() - datetime.timedelta(days = check_back))
    articles = (Article.objects.filter(date__gt = fromdate)
                .filter(articlesets_set = setid).only("url"))
    urls = set(a.url for a in articles)
    return urls

def cleanUpDraaiboek(text):
    body = ''
    for t in text.readlines():
        t = t.decode('latin-1', 'ignore')
        t = t.replace('\n',' ').replace('\r','')
        if t == ' ': continue
        if '000 ' in t: t = '\n\n'
        if '888' in t: t = '\n\n'
        body += t
    return body
            
class DraaiboekenScraper(PropertyCheckMixin, UnitScraper):

    def __init__(self, *args, **kargs):
        super(DraaiboekenScraper, self).__init__(*args, **kwargs)
        login_info = Scraper.objects.get(class_name='DraaiboekenScraper')
        self.articleset = self.options['articleset']
        self._ftp = ftplib.FTP('ftp.tt888.nl')
        self._ftp.login(login_info.username, login_info.password)
        self._ftp_lock = threading.Lock()

    _props = {
        'defaults' : {},
        'required' : ['url', 'headline', 'text', 'date', 'medium'],
        'expected' : []}


    @contextmanager
    def ftp(self):
        self._ftp_lock.acquire()
        try:
            yield self._ftp
        finally:
            self._ftp_lock.release()
        
    def _get_units(self):
        existing_files = getUrlsFromSet(setid=self.articleset, check_back=300)
        print(existing_files)
        with self.ftp() as ftp:
            for folder in ftp.nlst():
                if '.txt' in folder: continue
                files = {}
                got_xml = False
                for f in ftp.nlst(folder):
                    if '.txt' in f:
                        if f in existing_files:
                            print('Already in database: %s' % f)
                            continue
                        #f_url = asURL(f)
                        #if f_url in existing_files:
                        #    print('Already in database: %s' % f_url)
                        #    continue
                        files[f.split('/')[1].split('.txt')[0]] = f
                    if '.xml' in f: got_xml = f
                if got_xml:
                    if len(files) == 0:
                        print('\nAll files in %s already in database\n' % got_xml)
                        continue
                    dest = StringIO()
                    ftp.retrbinary(b'RETR %s' % got_xml, dest.write)
                    
                    xml = dest.getvalue()
                    for p in xml.split('<qry_Nieuwsmonitor>')[1:]:
                        tb = p.split('titelbestand>')[1].split('<')[0]
                        pn = p.split('Programmanaam>')[1].split('<')[0].strip()
                        if tb in files:
                            dest = StringIO()
                            ftp.retrbinary(b'RETR %s' % files[tb], dest.write)
                            dest.seek(0)
                            body = cleanUpDraaiboek(dest)
                            yield (pn,files[tb],body)
                        else:
                            print('Missing or already in database: %s' % tb)
                    

    def _scrape_unit(self, ftuple):
        title = ftuple[0]
        url = ftuple[1]
        body = ftuple[2]
        
        date = getDate(url)    
        medium = title.lower()
    
        headline = "%s (%s)" % (medium, url.split('/')[-1].replace('.stl','').strip())
        #url = asURL(url)
        art = dict(headline=headline, text=body,
                      medium=medium, date=date.strftime('%Y-%m-%d %H:%M:%S'), url=url)
        return art
            

if __name__ == '__main__':
    from amcatscraping.tools import setup_logging
    setup_logging()
    DraaiboekenScraper().run()
    

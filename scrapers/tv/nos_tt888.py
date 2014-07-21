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

#ARTICLESET, PROJECT, USERNAME, PASSWORD = sys.argv[1:]

def getDate(title):
    """Parses date (datetime object) from title of tt-888 .stl files. If hour > 24 (the date of nighttime broadcasts to a certain hour are attributed to former day), the true date of the broadcast is used. (hour minus 24, and day plus 1)"""
    datestring = title.split('-')[0:4]
    year, month, day, hour, minute = int(datestring[0]), int(datestring[1]), int(datestring[2]), int(datestring[3].split(',')[0]), int(datestring[3].split(',')[1])
    if hour > 23:
        hour = hour - 24
        date = datetime.datetime(year,month,day,hour,minute)
        return date + datetime.timedelta(1)
    else:
        return datetime.datetime(year,month,day,hour,minute)

def getUrlsFromSet(setid, check_back=300):
    """Returns list with all URLS of articles in the articleset for the last [check_back] days"""
    fromdate = (datetime.date.today() - datetime.timedelta(days = check_back))
    articles = (Article.objects.filter(date__gt = fromdate)
                .filter(articlesets_set = setid).only("url"))
    urls = set(a.url.split('/')[-1].lower() for a in articles if a.url)
    return urls
            
class tt888Scraper(PropertyCheckMixin, UnitScraper):

    def __init__(self, *args, **kargs):
        super(tt888Scraper, self).__init__()
        login_info = Scraper.objects.get(class_name='tt888Scraper')
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
        checkback = 30
        existing_files = getUrlsFromSet(setid=self.articleset, check_back=checkback+5)
        
        for exfile in existing_files:
            print(exfile)
        with self.ftp() as ftp:
            files = ftp.nlst()

        for fn in files:
            fn = fn.decode("latin-1")
            
            title = fn.split('/')[-1].lower()
            date = getDate(title)
            fromdate = datetime.date.today() - datetime.timedelta(checkback)
            if date.date() < fromdate:
                print('Too long ago!!')
                continue
            if title in existing_files:
                print("Already in articleset: %s" % title)
                continue
            if title.count('-') > 9:
                print('Skipping rerun')
                continue # Filter out reruns (marked by double dates)

            print(fn)
            
            yield fn


    def _scrape_unit(self, fn):
        dest = StringIO()
        with self.ftp() as ftp:
            ftp.retrbinary(b'RETR %s' % (fn.encode('latin-1')) , dest.write)
        text = dest.getvalue()

        if not text == '':
            body = STLtoText(text)
            body = body.decode('latin-1','ignore').strip().lstrip('888').strip()
        else:
            body = ''

        title = fn.split('/')[-1]
        medium = title.split('-')[-1].split('.stl')[0].strip().lower()
        date = getDate(title) 
        
        if medium == 'nos journaal' and int(format(date, '%H')) == 20 and int(format(date, '%M')) == 0: medium = 'NOS 20:00'

        if body == '': body = 'missing'
        headline = "%s (%s)" % (medium, fn.replace('.stl','').strip())
        art = dict(headline=headline, text=body,
                      medium = medium, date=date.strftime('%Y-%m-%d %H:%M:%S'), url = fn)
        return art


if __name__ == '__main__':
    from amcatscraping.tools import setup_logging
    setup_logging()
    tt888Scraper().run()
    

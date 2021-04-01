import urllib.parse

import tempfile
import shutil
import logging
import itertools
import collections
import iso8601
import datetime
import glob
import time
import csv
import re
import os
import argparse
from datetime import date
from selenium import webdriver
from typing import Tuple
from urllib.parse import urlparse
from pathlib import Path

from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
#from amcat.models import Article
from amcat.models import Article
from amcatscraping.scraper import DeduplicatingUnitScraper, LoginMixin
from amcatscraping.tools import parse_form, setup_logging
from dutch_news_scrapers import all_scrapers

log = logging.getLogger(__name__)


LOGIN_URL = "https://in.coosto.com/enter/signin"

#MEDIUMS = ["Nieuwsmedia"]



class SkipArticle(Exception):
    pass

class NotVisible(Exception):
    pass

class CoostoScraper(LoginMixin, DeduplicatingUnitScraper):
    publisher = None # Will be set by scraper

    def __init__(self, username, password, **kwargs):
        self.continuous = False
        super().__init__(username, password, **kwargs)
        self.medium = self.options['medium']
        self.query = self.options['query']
        #self.fromdate = self.options['fromdate']
        #self.todate = self.options['todate']
        self.proxy = self.options.get('proxy')

    def waitclick(self, selector, timeout=10, interval=0.1, by=By.CSS_SELECTOR):
        start = time.time()
        while True:
            try:
                if by == By.CSS_SELECTOR:
                    return self.browser.find_element(by, selector).click()
            except ElementClickInterceptedException:
                if time.time() < start + timeout:
                    time.sleep(interval)
                else:
                    raise

    def wait(self, selector, timeout=5, visible=True, by=By.CSS_SELECTOR):
        start = datetime.datetime.now()

        while True:
            seconds_forgone = (datetime.datetime.now() - start).total_seconds()       

            try:
                element = self.browser.find_element(by, selector)
            except NoSuchElementException:
                if seconds_forgone > timeout:
                    raise
            else:
                if not visible:
                    return element
                elif element.is_displayed():
                    return element
                elif seconds_forgone > timeout:
                    raise NotVisible("Element present, but not visible: {}".format(selector))

            time.sleep(0.5)

    def get_text(self, link: str) -> str:
        """
        Retrieve the text of an article using any of the scrapers from online_scrapers
        """
       # if self.proxy:
        #    kargs = dict(proxies={'https': f'socks5://localhost:{self.proxy}',
         #                         'http': f'socks5://localhost:{self.proxy}'})
        #else:
        kargs = {}
        for scraper in all_scrapers(**kargs):
            print(f"scraper is {scraper}")
            if scraper.can_scrape(link):
                logging.info(f"... Scraping {link} with {scraper}")
                time.sleep(1)  # to avoid being banned (again) :)
                return scraper.scrape_text(link)
        logging.error(f"No scraper available for {link}")
        raise SkipArticle(f"No scraper for {link}")

    def login(self, username, password):
        return True

    def _get_coosto_units(self, timeout=180):
        log.info("Exporting articles..")
        self.wait(".query_content > section:nth-child(4) menu.settings").click()
        self.wait('button[name="export"]').click()
        time.sleep(1)
        self.waitclick('#export_dialog_form_shards label[for="export_dialog_shards_csv"]')
        time.sleep(1)
        Select(self.wait("#export_dialog_count_shards")).select_by_value('10000')
        #TODO: check/clear tmp dir
        self.wait("#button_export").click()

        # Wait for file to be downloaded:
        log.info("Downloading file..")
        start = datetime.datetime.now()
        while True:
            time.sleep(0.3)
            if (datetime.datetime.now() - start).total_seconds() > timeout:
                raise IOError("Did not find file in {} within {} seconds".format(self.tmp_dir, timeout))
            files = list(self.tmp_dir.glob("*.csv"))
            if len(files) == 0:
                continue
            csvfile = files[0]
            print(f"NAME is {csvfile}")
            break
        try:
            # Wait for file to download
            fsize_prev = -1
            while True:
                fsize = csvfile.stat().st_size
                if fsize_prev == fsize:
                    for thing in csv.DictReader(csvfile.open(), delimiter=";"):
                       yield thing
                    return
                else:
                    fsize_prev = fsize
                time.sleep(0.3)
        finally:
            pass#csvfile.unlink()

    def get_deduplicate_units(self):
        log.info("Starting Firefox..")

        self.tmp_dir = Path(tempfile.mkdtemp(prefix="coosto-", suffix="-coosto"))
        print(self.tmp_dir)
        fp = webdriver.FirefoxProfile()
        fp.set_preference("browser.download.folderList",2)
        fp.set_preference("browser.download.dir", str(self.tmp_dir))
        fp.set_preference("browser.helperApps.neverAsk.saveToDisk", "text/csv")
        fp.set_preference("intl.accept_languages", "nl")
        #if self.proxy:
        #    log.info(f"Setting SOCKS proxy localhost: {self.proxy}")
        #    fp.set_preference("network.proxy.type", 1)
        #    fp.set_preference("network.proxy.socks", "localhost")
        #    fp.set_preference("network.proxy.socks_port", self.proxy)
        self.browser = webdriver.Firefox(firefox_profile=fp)

        try:
            self.browser.set_window_size(1920, 3000)
            log.info("Logging in on Coosto..")
            self.browser.get(LOGIN_URL)
            log.info("Sending username..")
            self.wait("#username").send_keys(self.username)
            log.info("Sending password..")
            self.wait("#password").send_keys(self.password)
            log.info("OK..")
            self.wait('.form__footer button[type="submit"]').click()

            #self.wait('//button[contains(@type,"submit")]', by=By.XPATH).send_keys("")
            #self.wait('//button[contains(@type,"submit")]' , by=By.XPATH).click()

            # Logout other users if necessary:
            try:
                self.wait(".usermessage", timeout=5)
            except NoSuchElementException:
                pass
            except NotVisible:
                pass
            else:
                self.wait(".flat_buttons > a").click()

            # Wait a bit for scripts to load
            time.sleep(5)

            # Close (potential) changelog
            webdriver.ActionChains(self.browser).send_keys(Keys.ESCAPE).perform()


            #Select Listen
            #self.wait('a[href="/querycenter/?pid=23291"]').click()
            self.wait('//a[contains(@href, "querycenter")]', by=By.XPATH).click()

            # Close all tabs
            self.wait(".tab_removeall").click()

            # Set filter media
            self.wait('#qform button.settings').click()
            #for medium in MEDIUMS:
            self.wait('//form[@id="qform"]//label[text() = "{}"]'.format(self.medium), by=By.XPATH).click()

            # Select 'only posts'
            self.wait(".query_advanced > div:nth-child(2) > p:nth-child(2) > label:nth-child(2)").click()

            # Set post to 'last 30 days'
            self.wait('#qform button.datepicker').click()
            #self.wait('#qform .date_presets > li[data-preset="24h"]').click()
            self.wait('fieldset.sb_container input.sb').clear()
            #self.wait('fieldset.sb_container input.sb').send_keys(self.fromdate)
            self.wait('fieldset.se_container input.se').clear()
            #self.wait('fieldset.se_container input.se').send_keys(self.todate)

            prev_time = datetime.datetime.now() - datetime.timedelta(minutes=30)

            #query input
            self.wait('textarea.q.query_input').send_keys(self.query)

            #search button
            self.wait('#qform button.query_form_submit').click()



            yield from self._get_coosto_units()

            while self.continuous:
                # Wait for 12 hours. No new articles = crash.
                self.wait(".notification_popup.opened", timeout=12*60*60)
                self.wait('#qform button.datepicker').click()

                # Reset time (to last 30 minutes)
                sb = self.wait('#qform .query_datepicker input.sb')
                sb.clear()
                sb.send_keys(prev_time.strftime("%d/%m/%Y %H:%M"))
                prev_time = datetime.datetime.now() - datetime.timedelta(minutes=30)

                se = self.wait('#qform .query_datepicker input.se')
                se.clear()
                se.send_keys("Nu")

                self.wait(".query_form_submit").click()

                # Make sure we commit ALL articles
                try:
                    (*init, last) = self._get_coosto_units()
                except ValueError:
                    # API returned no new articles..?
                    pass
                else:
                    yield from init
                    self.set_flush_flag()
                    yield last
        finally:
            pass#shutil.rmtree(self.tmp_dir)
            #self.browser.quit()

    def get_deduplicate_key_from_unit(self, unit):
        return unit["url"]

    def get_deduplicate_key_from_article(self, article):
        return article.url

    def scrape_unit(self, unit):
        date = iso8601.iso8601.parse_date(unit["datum"], default_timezone=None)
        hostname = urlparse(unit["url"]).hostname
        publisher = ".".join(hostname.split(".")[-2:])
        title = unit["titel"].strip() or"[No title]"
        if "advertorial" in unit['url']:
            return
        text = self.get_text(unit['url'])
        if text is None:
            raise Exception(f"Text is None for {unit['url']} (title: {title})")
        article = Article(title=title, text=text, url=unit["url"], date=date)
        article.set_property("author", unit["auteur"])
        article.set_property("publisher", publisher)
        return article
    

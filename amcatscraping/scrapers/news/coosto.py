###########################################################################
#          (C) Vrije Universiteit, Amsterdam (the Netherlands)            #
#                                                                         #
# This file is part of AmCAT - The Amsterdam Content Analysis Toolkit     #
#                                                                         #
# AmCAT is free software: you can redistribute it and/or modify it under  #
# the terms of the GNU Lesser General Public License as published by the  #
# Free Software Foundation, either version 3 of the License, or (at your  #
# option) any later version.                                              #
#                                                                         #
# AmCAT is distributed in the hope that it will be useful, but WITHOUT    #
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or   #
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public     #
# License for more details.                                               #
#                                                                         #
# You should have received a copy of the GNU Lesser General Public        #
# License along with AmCAT.  If not, see <http://www.gnu.org/licenses/>.  #
###########################################################################

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

from datetime import date
from selenium import webdriver
from typing import Tuple
from urllib.parse import urlparse

from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from amcat.models import Article
from amcatscraping.scraper import DeduplicatingUnitScraper, LoginMixin
from amcatscraping.tools import parse_form, setup_logging

log = logging.getLogger(__name__)


LOGIN_URL = "https://in.coosto.com/enter/signin"

MEDIUMS = [
    "Nieuwsmedia"
]

class NotVisible(Exception):
    pass

class CoostoScraper(LoginMixin, DeduplicatingUnitScraper):
    publisher = None # Will be set by scraper

    def __init__(self, username, password, **kwargs):
        self.continuous = False
        super().__init__(username, password, **kwargs)

    def wait(self, selector, timeout=60, visible=True, by=By.CSS_SELECTOR):
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

    def login(self, username, password):
        return True

    def _get_coosto_units(self, timeout=180):
        log.info("Exporting articles..")
        self.wait(".query_content > section:nth-child(4) menu.settings").click()
        self.wait('button[name="export"]').click()
        self.wait('#export_dialog_form_shards label[for="export_dialog_shards_csv"]').click()
        Select(self.wait("#export_dialog_count_shards")).select_by_value('10000')
        self.wait("#button_export").click()

        fname = os.path.join(self.tmp_dir, "*.csv")

        # Wait for file to be downloaded:
        log.info("Downloading file..")
        start = datetime.datetime.now()
        while True:
            time.sleep(0.3)

            if (datetime.datetime.now() - start).total_seconds() > timeout:
                raise IOError("Did not find {} within {} seconds".format(fname, timeout))

            try:
                fname_ = next(iter(glob.glob(fname)))
            except StopIteration:
                continue
            else:
                # Wait for file to download
                fsize = lambda : os.stat(fname_).st_size

                fsize_prev = -1
                while True:
                    if fsize_prev == fsize():
                        for thing in csv.DictReader(open(fname_), delimiter=";"):
                            yield thing
                        os.remove(fname_)
                        return
                    else:
                        fsize_prev = fsize()

                    time.sleep(0.3)

    def get_deduplicate_units(self):
        log.info("Starting Firefox..")

        self.tmp_dir = tempfile.mkdtemp(prefix="coosto-", suffix="-coosto")

        fp = webdriver.FirefoxProfile()
        fp.set_preference("browser.download.folderList",2)
        fp.set_preference("browser.download.dir", self.tmp_dir)
        fp.set_preference("browser.helperApps.neverAsk.saveToDisk", "text/csv")
        fp.set_preference("intl.accept_languages", "nl")

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
            self.wait('button[type="submit"]').click()

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

            # Close all tabs
            self.wait(".tab_removeall").click()

            # Set filter media
            self.wait('#qform button.settings').click()
            for medium in MEDIUMS:
                self.wait('//form[@id="qform"]//label[text() = "{}"]'.format(medium), by=By.XPATH).click()

            # Select 'only posts'
            self.wait(".query_advanced > div:nth-child(2) > p:nth-child(2) > label:nth-child(2)").click()

            # Set post to 'last 30 days'
            self.wait('#qform button.datepicker').click()
            self.wait('#qform .date_presets > li[data-preset="24h"]').click()

            prev_time = datetime.datetime.now() - datetime.timedelta(minutes=30)
            yield from self._get_coosto_units()

            while self.continuous:
                # Wait for 12 hours. No new articles = crash.
                self.wait(".notification_popup.opened", timeout=12*60*60)
                self.wait('#qform button.datepicker').click()

                # Reset time (to lsat 30 minutes)
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
            shutil.rmtree(self.tmp_dir)
            self.browser.quit()

    def get_deduplicate_key_from_unit(self, unit):
        return unit["url"]

    def get_deduplicate_key_from_article(self, article):
        return article.url

    def scrape_unit(self, unit):
        date = iso8601.iso8601.parse_date(unit["datum"], default_timezone=None)
        hostname = urlparse(unit["url"]).hostname
        publisher = ".".join(hostname.split(".")[-2:])
        title = unit["titel"].strip() or "[No title]"
        article = Article(title=title, text=unit["bericht tekst"], url=unit["url"], date=date)
        article.set_property("author", unit["auteur"])
        article.set_property("publisher", publisher)
        return article
    
if __name__ == "__main__":
    setup_logging()
    CoostoScraper().run()

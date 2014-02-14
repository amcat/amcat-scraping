from __future__ import absolute_import

from amcatscraping.celery.app import app

@app.task
def run_scraper(scraper):
    scraper.run()

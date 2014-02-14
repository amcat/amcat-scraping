from __future__ import absolute_import

from celery import Celery

app = Celery('amcatscraping')
app.config_from_object('amcatscraping.settings.celery')
app.autodiscover_tasks(['celery'])

if __name__ == "__main__":
    app.start()

"""Settings for celery app"""
from kombu import Exchange, Queue

CELERY_RESULT_BACKEND='amqp'

qname = 'amcatscraping'

CELERY_QUEUES = (Queue(qname, Exchange('default'), routing_key=qname),)
CELERY_DEFAULT_QUEUE = qname
CELERY_DEFAULT_ROUTING_KEY = qname
CELERY_IMPORTS = ('amcatscraping.celery',)

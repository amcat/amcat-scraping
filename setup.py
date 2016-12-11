#!/usr/bin/env python

from distutils.core import setup

setup(
    version='0.14',
    name="amcatscraping",
    description="Scrapers for AmCAT",
    author="Wouter van Atteveldt, Martijn Bastiaan, Toon Alfrink",
    author_email="wouter@vanatteveldt.com",
    packages=["amcatscraping",
              "amcatscraping.scrapers",
              "amcatscraping.scrapers.newspapers",
              "amcatscraping.scrapers.blogs",
              "amcatscraping.scrapers.news",
              "amcatscraping.scrapers.forums",
              ],
    package_data={
      'amcatscraping': ['*.conf', 'templates/*.html'],
   },
    classifiers=[
        "License :: OSI Approved :: AGPL3 License",
    ],
    install_requires=[
        "amcatclient",
        "requests",
        "html2text",
        "cssselect",
        "jinja2",
        "django",
        "docopt",
        "lxml",
        "tabulate",
        "feedparser", 'redis', 'dateparser', 'iso8601'
    ],
)

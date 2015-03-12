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
        "License :: OSI Approved :: MIT License",
    ],
    install_requires=[
        "html2text",
        "cssselect",
        "pyamf",
        "jinja2",
        "django",
        "docopt",
        "lxml",
        "tabulate",
    ],
)

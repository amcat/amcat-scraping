###########################################################################
# (C) Vrije Universiteit, Amsterdam (the Netherlands)            #
# #
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
"""Run scraper

Usage:
  scrape.py run [options] [<scraper>...]
  scrape.py list
  scrape.py -h | --help

Options:
  -h --help        Show this screen.
  --from=<date>    Scrape articles from date (default: today)
  --to=<date>      Scrape articles up to and including date (default: today)
  --dry-run        Do not commit to database
  --report         Send report to e-mailaddress after scraping

"""
import collections
from StringIO import StringIO
from email.utils import formatdate
import logging
import os.path
import sys
import jinja2
import datetime

from django.core.mail import EmailMultiAlternatives, get_connection

import amcatscraping.tools
from amcatscraping.tools import read_date, todatetime, get_boolean
import amcatscraping.scraper


JINJA_ENV = jinja2.Environment(loader=jinja2.PackageLoader('amcatscraping', 'templates'))
EMAIL_TEMPLATE = JINJA_ENV.get_template('log_email.html')

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

MODULE_PATH = os.path.abspath(os.path.join(*amcatscraping.__path__))
ROOT_PATH = os.path.abspath(os.path.join(MODULE_PATH, ".."))
DEFAULT_CONFIG_FILE = os.path.join(MODULE_PATH, "default.conf")
USER_CONFIG_FILE = os.path.abspath(os.path.expanduser("~/.scrapers.conf"))

SECTIONS = {"*", "store", "mail"}

ScraperResult = collections.namedtuple("ScraperResult", ["name", "narticles", "log"])


def get_scraper_class(scraper, relative_path):
    scraper_module, scraper_class = relative_path.rsplit(".", 1)

    if not get_boolean(scraper["is_absolute_classpath"]):
        scraper_module = "amcatscraping.scrapers.%s" % scraper_module

    scraper_module = __import__(scraper_module, fromlist=["non-empty"])
    return getattr(scraper_module, scraper_class)


def run_single(config, args, scraper_config, scraper_class):
    # Scraper config
    articleset_id = int(scraper_config["articleset"])
    project_id = int(scraper_config["project"])
    username = scraper_config["username"]
    password = scraper_config["password"]

    # Store config
    protocol = "https" if config.getboolean("store", "ssl") else "http"
    host_url = "%s://%s:%s" % (protocol, config.get("store", "host"), config.get("store", "port"))
    host_username = config.get("store", "username")
    host_password = config.get("store", "password")

    min_datetime = max_datetime = todatetime(datetime.date.today())

    if args["--from"]:
        min_datetime = todatetime(read_date(args["--from"]))

    if args["--to"]:
        max_datetime = todatetime(read_date(args["--to"]))

    opts = {
        "project": project_id,
        "articleset": articleset_id,
        "api_host": host_url,
        "api_user": host_username,
        "api_password": host_password,
        "username": username,
        "password": password,
        "log_errors": True,
        "min_datetime": min_datetime,
        "max_datetime": max_datetime,
    }

    if args["--dry-run"]:
        opts["command"] = "test"

    return scraper_class(**opts).run()


def _run(config, args, scrapers):
    all_scrapers = dict(get_scrapers(config))
    scrapers = {label: all_scrapers[label] for label in scrapers} or all_scrapers

    if not scrapers:
        print("No scrapers found.")
        sys.exit(1)

    non_existing_scrapers = set(scrapers) - set(all_scrapers)
    if non_existing_scrapers:
        print("Scraper(s) not found: %s. Use:\n" % ", ".join(non_existing_scrapers))
        print("\tscrape.py list\n")
        print("to list existing scrapers")
        sys.exit(1)

    root_logger = logging.getLogger(amcatscraping.scraper.__name__)
    for label, scraper in scrapers.items():
        articles = []  # HACK :-(
        log_buffer = StringIO()
        log_handler = logging.StreamHandler(log_buffer)
        root_logger.addHandler(log_handler)

        try:
            scraper_class = get_scraper_class(scraper, scraper["class"])
            articles.append(run_single(config, args, scraper, scraper_class))
        finally:
            root_logger.removeHandler(log_handler)
            narticles = len(articles.pop()) if articles else 0
            yield ScraperResult(label, narticles, log_buffer.getvalue())


def run(config, args, scrapers):
    logs = collections.OrderedDict()
    for label, narticles, log in _run(config, args, scrapers):
        logs[label] = (narticles, log)

    if args["--report"]:
        _send_email(config, logs)


def get_connection_config(config):
    if config.getboolean("mail", "use_django_settings"):
        return {}
    else:
        return {
            "host": config.get("mail", "host"),
            "port": config.get("mail", "port"),
            "use_tls": config.getboolean("mail", "tls"),
            "use_ssl": config.getboolean("mail", "ssl"),
            "username": config.get("mail", "username"),
            "password": config.get("mail", "password"),
        }


def _send_email(config, logs):
    scrapers = sorted([(label, narticles) for (label, (narticles, _)) in logs.items()])
    html_content = EMAIL_TEMPLATE.render(scrapers=scrapers, total=sum(dict(scrapers).values()))
    connection = get_connection(**get_connection_config(config))

    mail = EmailMultiAlternatives(
        connection=connection,
        subject="Scraper log for %s" % formatdate(),
        body="Enable HTML viewing in your e-mail client. Sorry :-(.",
        from_email=config.get("mail", "from"),
        to=config.get("mail", "to").split(",")
    )

    mail.attach_alternative(html_content, 'text/html')

    for (label, (_, log)) in logs.items():
        mail.attach(filename="%s_log.txt" % label, mimetype="text/plain", content=log)

    mail.send()


def get_config():
    config = configparser.SafeConfigParser()
    config.read([DEFAULT_CONFIG_FILE, USER_CONFIG_FILE])
    return config


def get_scrapers(config):
    """
    Returns parsed scraper dicts, based on given config file. This merges every
    scraper with [*]-section in config file.

    @type config: ConfigParser.ConfigParser
    """
    scrapers = set(config.sections()) - SECTIONS
    default_config = dict(config.items("*"))
    for scraper_label in scrapers:
        yield scraper_label, dict(default_config, **dict(config.items(scraper_label)))


def list_scrapers(config):
    print("Config file: ~/.scrapers.conf")
    for scraper_label, scraper in get_scrapers(config):
        print("")
        print("[%s]" % scraper_label)
        print("username: %s" % scraper.get("username"))
        print("class: %s" % scraper.get("class"))
        print("project: %s" % scraper.get("project"))
        print("articleset: %s" % scraper.get("articleset"))
    else:
        print("\nNo scrapers configured")


def main(config, args):
    if args["list"]:
        return list_scrapers(config)

    if args["run"]:
        return run(config, args, args["<scraper>"])


if __name__ == '__main__':
    from docopt import docopt

    amcatscraping.tools.setup_django()
    amcatscraping.tools.setup_logging()
    main(get_config(), docopt(__doc__, sys.argv[1:]))


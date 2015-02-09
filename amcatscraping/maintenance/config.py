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
import collections
from StringIO import StringIO
from email.utils import formatdate
import logging
import os.path
import sys
import jinja2

from django.core.mail import EmailMultiAlternatives, get_connection

import amcatscraping.tools
from amcatscraping.scraping import scraper
from amcatscraping.tools import read_date, todatetime


JINJA_ENV = jinja2.Environment(loader=jinja2.PackageLoader('amcatscraping', 'templates'))
EMAIL_TEMPLATE = JINJA_ENV.get_template('log_email.html')

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

MODULE_PATH = os.path.abspath(os.path.join(*amcatscraping.__path__))
ROOT_PATH = os.path.abspath(os.path.join(MODULE_PATH, ".."))
DEFAULT_CONFIG_FILE = os.path.join(MODULE_PATH, "maintenance/default.conf")
USER_CONFIG_FILE = os.path.abspath(os.path.expanduser("~/.scrapers.conf"))

SECTIONS = {"*", "store", "mail", "report"}

ScraperResult = collections.namedtuple("ScraperResult", ["name", "narticles", "log"])


def cron(config):
    pass


def get_scraper_class(relative_path):
    scraper_module, scraper_class = relative_path.rsplit(".", 1)
    scraper_module = "amcatscraping.scrapers.%s" % scraper_module
    scraper_module = __import__(scraper_module, fromlist=["non-empty"])
    return getattr(scraper_module, scraper_class)


def run_single(config, scraper_name, scraper_class):
    scraper_config = dict(dict(config.items("*")), **dict(config.items(scraper_name)))

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

    return scraper_class(**{
        "project": project_id,
        "articleset": articleset_id,
        "api_host": host_url,
        "api_user": host_username,
        "api_password": host_password,
        "username": username,
        "password": password,
        "log_errors": True,
        "command": "test",
        "min_datetime": todatetime(read_date("2015-02-09")),
        "max_datetime": todatetime(read_date("2015-02-09")),
    }).run()


def _run(config, scrapers):
    all_scrapers = set(config.sections()) - SECTIONS
    scrapers = sorted(scrapers or all_scrapers)

    root_logger = logging.getLogger(scraper.__name__)

    for scraper_name, scraper_class in zip(scrapers, map(get_scraper_class, scrapers)):
        articles = [] # HACK :-(
        log_buffer = StringIO()
        log_handler = logging.StreamHandler(log_buffer)
        root_logger.addHandler(log_handler)

        try:
            articles.append(run_single(config, scraper_name, scraper_class))
        finally:
            root_logger.removeHandler(log_handler)
            narticles = len(articles.pop()) if articles else 0
            yield ScraperResult(scraper_name, narticles, log_buffer.getvalue())


def run(config, scrapers):
    logs = collections.OrderedDict()
    for scraper_name, narticles, log in _run(config, scrapers):
        label = scraper_name
        if config.has_option(scraper_name, "label"):
            label = config.get(scraper_name, "label")
        logs[label] = (narticles, log)

    if config.getboolean("report", "enable"):
        _send_email(config, logs)


def _send_email(config, logs):
    scrapers = [(label, narticles) for (label, (narticles, _)) in logs.items()]
    html_content = EMAIL_TEMPLATE.render(scrapers=scrapers, total=sum(dict(scrapers).values()))

    connection = get_connection(
        backend="django.core.mail.backends.smtp.EmailBackend",
        host=config.get("mail", "host"),
        port=config.get("mail", "port"),
        username=config.get("mail", "username"),
        password=config.get("mail", "password"),
        fail_silently=False,
        use_tls=True
    )

    mail = EmailMultiAlternatives(
        subject="Scraper log for %s" % formatdate(),
        connection=connection,
        body="Enable HTML viewing in your e-mail client. Sorry :-(.",
        from_email=config.get("mail", "from"),
        to=config.get("mail", "to").split(",")
    )

    mail.attach_alternative(html_content, 'text/html')

    for (label, (_, log)) in logs.items():
        mail.attach(filename="%s_log.txt" % label, mimetype="text/plain", content=log)

    mail.send()


def usage():
    print("config.py [cron|run [,scraper]]")


def main(config, args):
    if len(args) <= 1:
        return usage()

    if args[1] == "cron":
        return cron(config)

    if args[1] == "run":
        return run(config, args[2:])

    print("%s not a valid argument.")
    usage()

if __name__ == '__main__':
    import django

    try:
        django.setup()
    except django.core.exceptions.ImproperlyConfigured:
        django.conf.settings.configure()
        django.setup()


    config = configparser.SafeConfigParser()
    config.read([DEFAULT_CONFIG_FILE, USER_CONFIG_FILE])
    amcatscraping.tools.setup_logging()
    main(config, sys.argv)


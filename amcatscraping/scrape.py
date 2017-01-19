###########################################################################
# (C) Vrije Universiteit, Amsterdam (the Netherlands)                     #
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
"""Run scraper

Usage:
  scrape.py run [options] [<scraper>...]
  scrape.py list
  scrape.py report [--email] [--date=<date>]
  scrape.py log <uuid>
  scrape.py -h | --help

Options:
  -h --help                Show this screen.
  --from=<date>            Scrape articles from date (default: today)
  --to=<date>              Scrape articles up to and including date (default: today)
  --dry-run                Do not commit to database
  --no-deduplicate-on-url  Do not dedpulicate based on URL
  --batch-size=<n>         If running in batched mode, this determines the batch size. For continuous
                           scrapers a low value is suitable for "real-time" purposes (default: 100).
  --update                 Update comment threads of existing articles

"""
import amcatscraping.setup_django
import amcatscraping.scraper
import configparser
import collections
import glob
import io
import json
import logging
import os.path
import sys
import jinja2
import datetime
import tabulate
import uuid
import errno

from iso8601.iso8601 import parse_date
from email.utils import formatdate
from django.core.mail import EmailMultiAlternatives, get_connection
from amcatscraping.tools import get_boolean, to_date


JINJA_ENV = jinja2.Environment(loader=jinja2.PackageLoader('amcatscraping', 'templates'))
EMAIL_TEMPLATE = JINJA_ENV.get_template('log_email.html')


log = logging.getLogger(__name__)

MODULE_PATH = os.path.abspath(os.path.join(*amcatscraping.__path__))
ROOT_PATH = os.path.abspath(os.path.join(MODULE_PATH, ".."))
DEFAULT_CONFIG_FILE = os.path.join(MODULE_PATH, "default.conf")
USER_CONFIG_FILE = os.path.abspath(os.path.expanduser("~/.scrapers.conf"))
LOG_DIR = os.path.expanduser("~/.cache/scraperlogs/")
TODAY = datetime.date.today()

SECTIONS = {"*", "store", "mail", "logging"}

ScraperResult = collections.namedtuple("ScraperResult", ["name", "narticles", "failed", "log"])


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
    username = scraper_config.get("username")
    password = scraper_config.get("password")
    scrape_comments = scraper_config.get("scrape_comments").lower() in ("y", "yes", "1", "true")

    # Store config
    protocol = "https" if config.getboolean("store", "ssl") else "http"
    host_url = "%s://%s:%s" % (protocol, config.get("store", "host"), config.get("store", "port"))
    host_username = config.get("store", "username")
    host_password = config.get("store", "password")

    min_date = max_date = datetime.date.today()

    if args["--from"]:
        try:
            reldate = int(args["--from"])
            min_date = min_date + datetime.timedelta(days=reldate)
        except ValueError:
            min_date = to_date(parse_date(args["--from"]))

    if args["--to"]:
        try:
            reldate = int(args["--to"])
            max_date = max_date + datetime.timedelta(days=reldate)
        except ValueError:
            max_date = to_date(parse_date(args["--to"]))

    opts = {
        "project_id": project_id,
        "articleset_id": articleset_id,
        "api_host": host_url,
        "api_user": host_username,
        "api_password": host_password,
        "username": username,
        "password": password,
        "scrape_comments": scrape_comments,
        "log_errors": True,
        "min_date": min_date,
        "max_date": max_date,
        "dry_run": args["--dry-run"],
        "deduplicate_on_url": not args["--no-deduplicate-on-url"],
        "batch_size": int(args.get("--batch-size") or 100)
    }

    scraper = scraper_class(**opts)
    method = "run_update" if args["--update"] else "run"

    try:
        return list(getattr(scraper, method)()), False
    except NotImplementedError:
        if args["--update"]:
            log.info("Updating not implemented for {scraper_class.__name__}".format(**locals()))
        else:
            log.exception("Running scraper {scraper_class.__name__} resulted in an exception:".format(**locals()))
    except Exception as e:
        log.exception("Running scraper {scraper_class.__name__} resulted in an exception:".format(**locals()))

    return [], True


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
        log_buffer = io.StringIO()
        log_handler = logging.StreamHandler(log_buffer)
        root_logger.addHandler(log_handler)

        scraper_class = get_scraper_class(scraper, scraper["class"])
        articles, failed = run_single(config, args, scraper, scraper_class)

        root_logger.removeHandler(log_handler)
        yield ScraperResult(label, len(articles), failed, log_buffer.getvalue())


def run(config, args, scrapers):
    """Run scrapers and write logs afterwards"""
    logs = collections.OrderedDict()
    for label, narticles, failed, log in _run(config, args, scrapers):
        logs[label] = (datetime.datetime.now(), narticles, failed, log)

    identifier = str(uuid.uuid4())
    log_dir = os.path.join(LOG_DIR, TODAY.strftime("%Y-%m-%d"))
    log_file = os.path.join(log_dir, identifier + ".json")

    try:
        os.makedirs(log_dir)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise

    for label, (timestamp, narticles, failed, log) in logs.items():
        json.dump({
            "narticles": narticles, "log": log, "label": label,
            "timestamp": int(timestamp.strftime("%s")),
            "update": args["--update"], "uuid": identifier,
            "failed": failed
        }, open(log_file, "w"))


def _bool_to_str(val):
    if val is None:
        return ""
    return "Yes" if val else "No"


def get_logs(date):
    log_dir = os.path.join(LOG_DIR, date.strftime("%Y-%m-%d"))
    files = glob.glob(os.path.join(log_dir, "*.json"))
    logs = map(json.load, map(open, files))
    logs = sorted(logs, key=lambda l: (l['label'], l['timestamp']))

    for log in logs:
        log["timestamp"] = datetime.datetime.fromtimestamp(log["timestamp"]).isoformat()
        log["update"] = _bool_to_str(log.get("update"))
        log["failed"] = _bool_to_str(log.get("failed"))

    return logs


def report(config, args):
    date = args.get('--date')
    date = TODAY if date is None else parse_date(date).date()

    headers = ["label", "timestamp", "narticles", "update", "failed", "uuid"]
    table_data = [[log[h] for h in headers] for log in get_logs(date)]

    if table_data:
        print(tabulate.tabulate(table_data, headers=headers))
        print("\nUse 'scrape log <uuid>' to view the logs of a particular run.")
    else:
        print("No logs found for {date}".format(date=date))
        return

    if args["--email"]:
        print("Sending report above via email.. ", end="")
        _send_email(config, headers, table_data)
        print("OK.")

def _log(config, args):
    file = glob.glob(os.path.join(LOG_DIR, "*/{}.json".format(args["<uuid>"])))

    assert(len(file) <= 1)

    try:
        print(json.load(open(file[0]))["log"].strip())
    except IndexError:
        print("No log found for {}".format(args["<uuid>"]))


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


def _send_email(config, headers, table_data):
    table_html = tabulate.tabulate(table_data, headers=headers)
    html_content = EMAIL_TEMPLATE.render(table=table_html, today=TODAY)
    connection = get_connection(**get_connection_config(config))

    mail = EmailMultiAlternatives(
        connection=connection,
        subject="Scraper log for %s" % formatdate(),
        body="Enable HTML viewing in your e-mail client. Sorry :-(.",
        from_email=config.get("mail", "from"),
        to=config.get("mail", "to").split(",")
    )

    mail.attach_alternative(html_content, 'text/html')
    mail.send()


def get_config():
    config = configparser.ConfigParser()
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

    if args["report"]:
        return report(config, args)

    if args["log"]:
        return _log(config, args)

if __name__ == '__main__':
    from docopt import docopt

    amcatscraping.tools.setup_logging()
    main(get_config(), docopt(__doc__, sys.argv[1:]))


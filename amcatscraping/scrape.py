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
  scrape.py [options] <scraper>
  scrape.py -l | --list-scrapers
  scrape.py -h | --help

Options:
  -h --help                Show this screen.
  --from=<date>            Scrape articles from date (default: today)
  --to=<date>              Scrape articles up to and including date (default: today)
  --dry-run                Do not commit to database
  --no-headless            Instruct Chromium to create window
  --batch-size=<n>         If running in batched mode, this determines the batch size. For continuous
                           scrapers a low value is suitable for "real-time" purposes (default: 100).
"""
import amcatscraping.setup_django
import configparser
import logging
import os.path
import datetime
import tabulate
import sys

from iso8601.iso8601 import parse_date
from amcatscraping.tools import get_boolean, to_date
from amcatscraping.scraper import SeleniumMixin


log = logging.getLogger(__name__)

MODULE_PATH = os.path.abspath(os.path.join(*amcatscraping.__path__))
ROOT_PATH = os.path.abspath(os.path.join(MODULE_PATH, ".."))
DEFAULT_CONFIG_FILE = os.path.join(MODULE_PATH, "default.conf")
USER_CONFIG_FILE = os.path.abspath(os.path.expanduser("~/.scrapers.conf"))

SECTIONS = {"*", "store"}


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
        "min_date": min_date,
        "max_date": max_date,
        "dry_run": args["--dry-run"],
        "batch_size": int(args.get("--batch-size") or 100)
    }

    raw_opts = dict(scraper_config)
    for opt in opts.keys():
        if opt in raw_opts:
            del raw_opts[opt]

    for opt in ("username", "password", "articleset", "project", "class", "is_absolute_classpath"):
        if opt in raw_opts:
            del raw_opts[opt]

    opts["options"] = raw_opts

    scraper = scraper_class(**opts)

    try:
        scraper.setup_session()
        scraper.run()
    finally:
        if isinstance(scraper, SeleniumMixin):
            os.makedirs("artifacts", exist_ok=True)
            html = scraper.browser.execute_script("return document.body.outerHTML;")
            open("artifacts/last_sight.html", "w").write(html)
            scraper.browser.save_screenshot("artifacts/last_sight.png")


def run(config, args, scraper: str):
    all_scrapers = dict(get_scrapers(config))

    scraper = all_scrapers.get(scraper)
    if scraper is None:
        print("Scraper not found: {}. Use:\n".format(scraper))
        print("\tscrape.py -l\n")
        print("to list existing scrapers")
        sys.exit(1)

    scraper_class = get_scraper_class(scraper, scraper["class"])
    run_single(config, args, scraper, scraper_class)


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

    scrapers = [(label, scraper.get("class")) for label, scraper in get_scrapers(config)]
    scrapers = sorted(scrapers, key=lambda s: s[0].lower())

    if scrapers:
        print(tabulate.tabulate(scrapers, headers=["Name", "class"]))
    else:
        print("\nNo scrapers configured")


def main(config, args):
    if args["-l"] or args["--list-scrapers"]:
        return list_scrapers(config)
    run(config, args, args["<scraper>"])


if __name__ == '__main__':
    from docopt import docopt

    amcatscraping.tools.setup_logging()
    main(get_config(), docopt(__doc__, sys.argv[1:]))

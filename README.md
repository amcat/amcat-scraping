Installation
======

Install amcat-scraping and amcatclient directly from github using pip:

```{sh}
pip install git+git://github.com/amcat/amcatclient git+git://github.com/amcat/amcat-scraping
```

(Note, you should probably either work in a python virtual environment, or use sudo to install system-wide)

The scrapers can be run using the `amcatscraping.scrape` module: (see below for configuration and options)

```{sh}
python -m amcatscraping.scrape --help
```

AmCAT 3.5
===
AmCAT 3.5 included the transition from Python 2 to Python 3. Additionally, some fundamental changes in the way it approaches articles have been made. This is an overview of the scrapers currently fixed:

* newspapers.ad
* newspapers.fd
* newspapers.nrc
* newspapers.nrchandelsblad
* newspapers.nrcnext
* newspapers.pcm
* newspapers.telegraaf
* newspapers.trouw
* newspapers.volkskrant
* blogs.geenstijl
* news.nu

Unchecked / not working are:

* forums.hababam
* forums.marokko
* forums.phpbb
* news.fok
* newspapers.haaretz

Configuration
====

Configuration is stored in <code>~/.scrapers.conf</code>.

```{conf}
[store]
# Project and articleset defined per scraper
host: amcat.nl
port: 443
username: amcat
password: amcat
ssl: true

[mail]
host: mail.hmbastiaan.nl
port: 587
from: spam@hmbastiaan.nl
to: spam@hmbastiaan.nl
username: martijn
password: xxxxxxx
tls: true

[*]
# Section with defaults for all scrapers
articleset: 37
project: 1

[AD]
username: xxxxxxxxxxxxxxx
password: xxxxxxxxxxxxxxx
class: newspapers.ad.AlgemeenDagbladScraper
```

Defaults can be found [here](https://github.com/amcat/amcat-scraping/blob/master/amcatscraping/maintenance/default.conf here)

Specific options:

[store]
------

Defines where articles are saved, after scraping.

<code>host</code> hostname or IP-address of AmCAT instance [default: amcat.nl]

<code>port</code> port to connect to [default: 80]

<code>username / password</code> credentials to use when logging in

<code>ssl</code> use SSL upon connecting (port should probably 443) [default: no]

[mail]
----

<code>use_django_settings</code> use default Django settings for mail. See the [Django documention on e-mail settings](https://docs.djangoproject.com/en/1.7/ref/settings/#default-from-email) [default: false]

<code>host</code> SMTP server (outgoing) hostname / IP-address

<code>port</code> port to connect to [default: 587]

<code>ssl</code> use ssl [default: no]

<code>tls</code> use tls [default: true]

<code>username / password</code> credentials to use when logging in

[*]
----
All settings in this section will be used as defaults for all scrapers. See the following section.

[scraper_label]
----

<code>username / password</code> credentials to use when logging in

<code>class</code> class relative to <code>amcatscraping.scrapers</code>

<code>is_absolute_classpath</code> if this option is enabled, <code>class</code> will be considered an absolute classpath [default: no]

<code>articleset</code> id of articleset in which to store scraped articles

<code>project</code> id of project in which to store scraped articles

Running
----

You can directly call <code>amcatscraping.scrape</code> to invoke specific, or all scrapers. 


```{sh}
$ python -m amcatscraping.scrape --help
Run scraper

Usage:
  scrape.py run [options] [<scraper>...]
  scrape.py list
  scrape.py -h | --help

Options:
  -h --help        Show this screen.
  --from=<date>    Scrape articles from date (default: today)
  --to=<date>      Scrape articles up to and including date (default: today)
  --dry-run        Do not commit to database
  --report         Send report to e-mailaddress after scraping</nowiki>
```


You can use <code>list</code> to list all scrapers installed in <code>~/.scrapers.conf</code>. One can run all scrapers listed their by specifying none:

<code>PYTHONPATH=. python amcatscraping/maintenance/run.py</code>

or specific ones by listing them:

<code>PYTHONPATH=. python amcatscraping/maintenance/run.py AD FD</code>

You can mix various options; for example:

<code>PYTHONPATH=. python amcatscraping/maintenance/run.py AD FD --report --dry-run</code>

The latter will email a report similar to the mail shown below:

[![Scraper report](http://wiki.amcat.nl/images/thumb/4/4d/Scraper_report.png/173px-Scraper_report.png)](http://wiki.amcat.nl/images/4/4d/Scraper_report.png)

Running periodically
----
You can use [Cron](https://en.wikipedia.org/wiki/Cron) to install periodic jobs on Linux-based systems. To view / edit your current jobs, run <code>crontab -e</code>. To run all scrapers each morning at 11 A.M., add:

<code>0 11 * * 1  python -m amcatscraping.scrape all --report</code>

Installation
======

Clone both amcat-scraping and amcat-client. The latter is used to contact a running AmCAT instance, and push articles.

```{sh}
git clone https://github.com/amcat/amcat-scraping.git amcatscraping
git clone https://github.com/amcat/amcat-client.git amcatclient
ln -s amcatclient amcatscraping
```

You might need to install dependencies (use `sudo` to become root if needed):

```
pip -r install amcatscraping/requirements.txt
```

That's it!

Configuration
====

Configuration is stored in <code>~/.scrapers.conf</code>.

```{conf}
[store]
# Project and articleset defined per scraper
host: localhost
port: 9876
username: amcat
password: amcat
ssl: false

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

You can use <code>scrape.py</code> to invoke specific, or all scrapers. 


```{sh}
$ PYTHONPATH=. python amcatscraping/maintenance/scrape.py --help
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

[![Scraper report](http://wiki.amcat.nl/images/thumb/4/4d/Scraper_report.png/173px-Scraper_report.png)](http://wiki.amcat.nl/images/4/4d/Scraper_report.png)

You can use <code>list</code> to list all scrapers installed in <code>~/.scrapers.conf</code>. One can run all scrapers listed their by specifying none:

<code>PYTHONPATH=. python amcatscraping/maintenance/run.py</code>

or specific ones by listing them:

<code>PYTHONPATH=. python amcatscraping/maintenance/run.py AD FD</code>

You can mix various options; for example:

<code>PYTHONPATH=. python amcatscraping/maintenance/run.py AD FD --report --dry-run</code>

Running periodically
----
You can use [https://en.wikipedia.org/wiki/Cron Cron] to install periodic jobs on Linux-based systems. To view / edit your current jobs, run <code>crontab -e</code>. To run all scrapers each morning at 11 A.M., add:

<code>0 11 * * 1  cd ~/amcatscraping; PYTHONPATH=. python amcatscraping/maintenance/run.py --report</code>

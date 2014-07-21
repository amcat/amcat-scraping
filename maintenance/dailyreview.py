"""This script ought to be run daily.
It will mail the provided adresses with an overview
of scrapers and their results"""

from datetime import date, timedelta
from collections import defaultdict, OrderedDict
from pprint import pprint
from mailer import Mailer, Message

from amcatclient.amcatclient import AmcatAPI

from amcatscraping.tools import get_arguments
from amcatscraping.maintenance.db import DB

MAIL = """
<h2>Scraping report</h2>
<p>The following scrapers are active:</p>
{table}
"""

# Hacks for readable output
class PrettyDefaultDict(defaultdict):
    __repr__ = dict.__repr__

class PrettyOrderedDict(OrderedDict):
    __repr__ = dict.__repr__

class DailyReview(object):
    def __init__(self):
        self.arguments = get_arguments(OrderedDict([
            ('api_host', {}),
            ('api_user', {}),
            ('api_password', {}),
            ('--smtp_server',{}),
            ('--email_login',{}),
            ('--email_password',{}),
            ('mail_to',{'nargs' : '*'})
        ]))
        if 'mail_to' in self.arguments:
            assert 'smtp_server' in self.arguments
            assert 'email_login' in self.arguments
            assert 'email_password' in self.arguments

        self.api = AmcatAPI(self.arguments['api_host'],
                            self.arguments['api_user'],
                            self.arguments['api_password'])
        self.db = DB()
        
    def run(self):
        data = self._getdata()
        pprint(data)
        html = MAIL.format(table = self._maketable(data))
        self._send_mail(html)

    def _getdata(self):
        result = PrettyDefaultDict(lambda:PrettyOrderedDict())
        for classpath, info in self.db.items():
            today = date.today()
            i = -1
            while i < 7:
                i += 1
                day = today - timedelta(days = i)
                project, articleset = info['arguments']['project'], info['arguments']['articleset']
                articles = self.api.list_articles(project, articleset,
                                                  insertscript = classpath,
                                                  date = day
                                              )
                n_articles = len(list(articles))
                result[classpath][day] = n_articles
        return result

    def _maketable(self, resultdict):
        unique_keys = sorted(set([key for item in resultdict.values() for key in item]), 
                             reverse = True)
        rows = [["&nbsp;"] + unique_keys]
        for classpath, data in resultdict.items():
            row = [classpath]
            for key in unique_keys:
                row.append(data.get(key))
            rows.append(row)
            
        table = '<table border="1">'
        for row in rows:
            table += "<tr>"
            for data in row:
                table += '<td align="right">'
                if data:
                    table += str(data)
                else:
                    table += '0'
                table += "</td>"
            table += "</tr>"
        table += "</table>"
        return table

    def _send_mail(self, html):
        user = self.arguments['email_login']
        message = Message(
            From = user,
            To = self.arguments['mail_to'],
            Subject = "Scraping report",
            Html = html)

        sender = Mailer(
            self.arguments['smtp_server'], 
            usr = user, 
            pwd = self.arguments['email_password'],
            use_tls = True)

        sender.send(message)
        

if __name__ == "__main__":
    DailyReview().run()
            

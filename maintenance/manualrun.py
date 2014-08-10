from amcatscraping.tools import (todatetime, read_date, setup_logging,
                                 get_arguments, run_scraper_and_log)
from amcatscraping.maintenance.db import DB

class ManualRun(object):
    """
    This script will allow you to run all
    daterange scrapers with custom date arguments
    (In the future, further flexibility should be added,
    but this will cover for 90% of the use cases)
    """
    db = DB()
    def __init__(self):
        self.options = get_arguments({
            ('api_host','api_user','api_password') : {},
            ('min_datetime','max_datetime') : {
                'type' : lambda x: todatetime(read_date(x))}
        })

    def run(self):
        for classpath, info in self.db.items():
            if info['timetype'] == 'daterange':
                arguments = info['arguments']
                arguments.update(self.options)
                run_scraper_and_log(classpath, arguments, self.db)

if __name__ == "__main__":
    setup_logging()
    ManualRun().run()

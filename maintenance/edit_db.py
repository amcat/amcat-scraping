"""One-run script to update db to new version"""
from amcatscraping.maintenance.db import DB

def run():
    db = DB()
    for classpath, info in db.items():
        if info.get('period') == 'hourly':
            info['timetype'] = 'periodic'
            info['cron'] = "30 * * * *"
        elif info.get('period') == 'daily' :
            info['timetype'] = 'daterange'
        if info.get('period'):
            del info['period']
        db[classpath] = info


if __name__ == "__main__":
    run()

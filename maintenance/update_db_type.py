"""temp script to make the DB compatible with new code"""

import dbm, pickle

db = dbm.open('scrapers','c')
for k in db.keys():
    val = pickle.loads(db[k])
    if val['run_daily']:
        val['period'] = 'daily'
    else:
        val['period'] = 'never'
    del val['run_daily']
    db[k] = pickle.dumps(val)
    

"""Keeps a tiny database for registering scrapers, their arguments and other useful info about them"""

import dbm, os, pprint, argparse, dill as pickle
from importlib import import_module

PYTHONPATH = os.environ.get('PYTHONPATH')

class DB(object):
    def __init__(self):
        self.db = dbm.open(PYTHONPATH + "/amcatscraping/maintenance/scrapers",'c')

    def items(self):
        for k in self.db.keys():
            yield (k,pickle.loads(self.db[k]))

    def list(self):
        pprint.pprint(self.items())

    def add(self, classpath, run_daily, active, label = None, **arguments):
        assert 'articleset' in arguments and arguments['articleset']
        assert 'project' in arguments and arguments['project']
        assert period in ('hourly','daily','weekly','never')
        modulepath,classname = classpath.rsplit(".",1)
        module = import_module(modulepath)
        getattr(module, classname) #check if class exists in module

        info = {'classpath':classpath,
                'run_daily':run_daily,
                'active':active,
                'label':label,
                'arguments':arguments,
                'runs':[]}
        if not label:
            info['label'] = classpath

        self.db[classpath] = pickle.dumps(info)
            
    def update(self, classpath, **kwargs):
        item = dict(pickle.loads(self.db[classpath]).items() + kwargs.items())
        self.db[classpath] = pickle.dumps(item)
        self.db.close()
        self.db = dbm.open(PYTHONPATH + '/amcatscraping/maintenance/scrapers','w')

    def delete(self, classpath):
        """Consider setting 'active = False' instead of deleting"""
        del self.db[classpath]

    def __getitem__(self, classpath):
        return pickle.loads(self.db[classpath])

    def __setitem__(self, classpath, info):
        self.db[classpath] = pickle.dumps(info)

def argparser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='command')

    parser_add = subparsers.add_parser('add')
    parser_update = subparsers.add_parser('update')
    parser_delete = subparsers.add_parser('delete')
    parser_list = subparsers.add_parser('list')
    for p in [parser_add,parser_update,parser_delete]:
        p.add_argument('classpath')

    parser_add.add_argument('run_daily',type=bool)
    parser_add.add_argument('active',type=bool)

    parser_update.add_argument('--run_daily',type=bool)
    parser_update.add_argument('--active',type=bool)

    for p in [parser_add,parser_update]:
        p.add_argument('--label')
        p.add_argument('--articleset',type=int)
        p.add_argument('--project',type=int)
        p.add_argument('--username')
        p.add_argument('--password')

    return parser

if __name__ == "__main__":
    db = DB()
    parser = argparser()
    args = parser.parse_args()
    call = getattr(db, args.command)
    del args.command
    call(**vars(args))

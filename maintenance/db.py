"""Keeps a tiny database for registering scrapers, their arguments and other useful info about them"""

import gdbm, os, pprint, argparse, pickle
from importlib import import_module
from contextlib import contextmanager

PYTHONPATH = os.environ.get('PYTHONPATH')
assert PYTHONPATH

class DB(object):

    @contextmanager
    def opendb(self):
        self.db = gdbm.open(PYTHONPATH + "/amcatscraping/maintenance/scrapers",'cs')
        try:
            yield
        finally:
            self.db.close()

    def items(self):
        with self.opendb():
            return [(k,pickle.loads(self.db[k])) for k in self.db.keys()]
                
    def runcmd(self, command, *args, **kwargs):
        with self.opendb():
            getattr(self, command)(*args, **kwargs)

    def list(self, verbose=False):
        if verbose:
            pprint.pprint(self.items())
        else:
            pprint.pprint(self.items(), depth = 3)

    def add(self, classpath, period, active, label = None, **arguments):
        modulepath,classname = classpath.rsplit(".",1)
        module = import_module(modulepath)
        getattr(module, classname) #check if class exists in module

        info = {'classpath':classpath,
                'period':period,
                'active':active,
                'label':label,
                'arguments':arguments,
                'runs':[]}
        if not label:
            info['label'] = classpath

        with self.opendb():
            self.db[classpath] = pickle.dumps(info)
            
    def update(self, classpath, **kwargs):
        with self.opendb():
            self.db[classpath] = pickle.dumps(dict(pickle.loads(self.db[classpath]).items() + kwargs.items()))

    def delete(self, classpath):
        """Consider setting 'active = False' instead of deleting"""
        with self.opendb():
            del self.db[classpath]

    def __getitem__(self, classpath):
        with self.opendb():
            return pickle.loads(self.db[classpath])

    def __setitem__(self, classpath, info):
        with self.opendb():
            self.db[classpath] = pickle.dumps(info)

def getargparser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='command')

    scraper_props = {
        ('username','password','label') : {},
        ('articleset','project') : {'type' : int},
        ('active',) : {'type' : bool},
        ('period',) : {'choices':['hourly','daily','weekly','never']},
        }
        
    parser_add = subparsers.add_parser('add')
    parser_add.add_argument('classpath')
    for names, arguments in scraper_props.items():
        for name in names:
            if name in ('username','password','label'):
                parser_add.add_argument("--" + name, **arguments)
            else:
                parser_add.add_argument(name, **arguments)

    parser_update = subparsers.add_parser('update')
    parser_update.add_argument('classpath')
    for names, arguments in scraper_props.items():
        for name in names:
            parser_update.add_argument("--" + name, **arguments)

    parser_delete = subparsers.add_parser('delete')
    parser_delete.add_argument('classpath')

    parser_list = subparsers.add_parser('list')
    parser_list.add_argument('--verbose')

    return parser

if __name__ == "__main__":
    db = DB()
    parser = getargparser()
    args = parser.parse_args()
    db.runcmd(**vars(args))

"""Keeps a tiny database for registering scrapers, their arguments and other useful info about them"""

import gdbm, os, pprint, pickle
from importlib import import_module
from contextlib import contextmanager

from amcatscraping.tools import get_arguments

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
                
    def runcli(self):
        arguments = get_arguments(
            add = {
                ('classpath','--username','--password','--label') : {},
                ('articleset','project') : {'type' : int},
                'active' : {'type' : bool, 'const' : True},
                'period' : {'choices' : ['hourly','daily','weekly','never']},
            },
            update = {
                ('classpath','--username','--password','--label') : {},
                ('--articleset','--project') : {'type' : int},
                '--active' : {'type' : bool, 'const' : True},
                '--period' : {'choices' : ['hourly','daily','weekly','never']},
            },
            delete = {
                'classpath' : {}
            },
            list = {
                '--verbose' : {'type' : bool, 'const' : True}
            }
        )
        func = getattr(self, arguments['__command__'])
        del arguments['__command__']
        with self.opendb():
            func(**arguments)

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
            updated = dict(pickle.loads(self.db[classpath]).items() + kwargs.items())
            self.db[classpath] = pickle.dumps(updated)

    def delete(self, classpath):
        """Consider setting 'active = False' instead of deleting"""
        with self.opendb():
            del self.db[classpath]

    def __iter__(self):
        with self.opendb():
            for key in self.db.keys():
                yield key

    def __getitem__(self, classpath):
        with self.opendb():
            return pickle.loads(self.db[classpath])

    def __setitem__(self, classpath, info):
        with self.opendb():
            self.db[classpath] = pickle.dumps(info)


if __name__ == "__main__":
    DB().runcli()

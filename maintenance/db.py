"""Keeps a tiny database for registering scrapers, their arguments and other useful info about them"""

import gdbm, os, pprint, pickle
from importlib import import_module
from contextlib import contextmanager
from croniter import croniter

from amcatscraping.tools import get_arguments

PYTHONPATH = os.environ.get('PYTHONPATH')
assert PYTHONPATH

def is_cron(string):
    try:
        croniter(string)
    except ValueError:
        raise ValueError("please provide a valid cron entry")
    else:
        return string

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
                'active' : {'type' : bool},
                'timetype' : {'choices' : ['periodic','daterange']},
                '--cron' : {'type' : is_cron},
            },
            update = {
                ('classpath','--username','--password','--label') : {},
                ('--articleset','--project') : {'type' : int},
                '--active' : {'action' : 'store_const', 'const' : True},
                '--timetype' : {'choices' : ['periodic','daterange']},
                '--cron' : {'type' : is_cron}
            },
            delete = {
                'classpath' : {}
            },
            list = {
                '--depth' : {'type':int}
            }
        )
        func = getattr(self, arguments['__command__'])
        del arguments['__command__']
        with self.opendb():
            func(**arguments)

    def list(self, depth = 2):
        pprint.pprint(self.items(), depth = 3)

    def add(self, classpath, timetype, cron, active, label = None, **arguments):
        modulepath,classname = classpath.rsplit(".",1)
        module = import_module(modulepath)
        getattr(module, classname) #check if class exists in module

        info = {'classpath':classpath,
                'timetype' : timetype,
                'cron' : cron,
                'active' : active,
                'label' : label,
                'arguments' : arguments,
                'runs':[]}
        if not label:
            info['label'] = classpath
        if timetype == 'periodic' and not cron:
            raise ValueError("Please provide --cron when timetype is periodic")
        if cron:
            info['cron'] = cron

        with self.opendb():
            self.db[classpath] = pickle.dumps(info)
            
    def update(self, classpath, **kwargs):
        with self.opendb():
            updated = dict(pickle.loads(self.db[classpath]).items() + kwargs.items())
            if updated['timetype'] == 'periodic' and not updated.get('cron'):
                raise ValueError("Please provide --cron when timetype is periodic")
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

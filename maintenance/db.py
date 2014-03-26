"""Keeps a tiny database for registering scrapers and their arguments"""

import dbm, argparse, json

class DB(object):
    def __init__(self):
        self.db = dbm.open('scrapers','c')

    def items(self):
        return [(k,json.loads(self.db[k])) for k in self.db.keys()]

    def list(self):
        print(self.items())

    def add(self, classpath, run_daily, active, **kwargs):
        assert 'articleset' in kwargs and kwargs['articleset']
        assert 'project' in kwargs and kwargs['project']
        if not kwargs.get('label'):
            kwargs['label'] = classpath
        kwargs.update({'run_daily' : run_daily, 'active' : active})
        self.db[classpath] = json.dumps(kwargs)
            
    def update(self, classpath, **kwargs):
        item = dict(json.loads(self.db[classpath]).items() + kwargs.items())
        self.db[classpath] = json.dumps(item)

    def delete(self, classpath):
        """Consider setting 'active = False' instead of deleting"""
        del self.db[classpath]


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

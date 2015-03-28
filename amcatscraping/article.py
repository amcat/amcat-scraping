from uuid import uuid4


class Article(object):
    def __init__(self, properties, children=(), uuid=None, parent=None, id=None):
        self._children = children
        self.properties = properties
        self.uuid = uuid or uuid4()
        self.parent = parent
        self.id = id

    def __hash__(self):
        return hash(self.uuid)

    def __repr__(self):
        return "<Article: {})>".format(self.properties)

    def __eq__(self, other):
        if not isinstance(other, Article):
            raise ValueError("Cant compare {} with {}".format(type(other), type(self)))
        return self.uuid == other.uuid

    @property
    def children(self):
        for child in self._children:
            child.parent = self
            yield child

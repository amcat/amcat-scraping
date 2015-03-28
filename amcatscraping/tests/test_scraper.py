from __future__ import absolute_import, print_function, unicode_literals
from amcatscraping.article import Article

from amcatscraping.scraper import add_articles, get_tree

import unittest

class ScraperTest(unittest.TestCase):
    pass


class AddArticlesTest(unittest.TestCase):
    def scrape(self):
        yield Article(**{
            "properties":{
                "_id": 0,
            },
            "children": [
                Article({"_id": 1}),
                Article({"_id": 2})
            ]
        })

        yield Article(**{
            "properties":{
                "_id": 3,
                "parent": 2
            },
            "children": [
                Article({"_id": 4})
            ]
        })

    def test_add_articles(self):
        scraped = self.scrape()
        articles = []

        batches = add_articles(articles, next(scraped), batch_size=2)

        batch = next(batches)
        self.assertEqual([{u'_id': 0}, {u'_id': 1}], [a.properties for a in batch])
        self.assertEqual(batch[1].parent, batch[0])

        self.assertRaises(StopIteration, next, batches)
        self.assertEqual({u'_id': 2}, articles[0].properties)
        self.assertEqual(batch[0], articles[0].parent)

    def test_add_articles_parent(self):
        scraped = self.scrape()
        articles = []

        list(add_articles(articles, next(scraped), batch_size=2))
        batch = next(add_articles(articles, next(scraped), batch_size=2))

        self.assertEqual(3, batch[1].properties["_id"])
        self.assertEqual(2, batch[1].properties["parent"])

    def test_get_tree(self):
        scraped = self.scrape()
        articles = []

        list(add_articles(articles, next(scraped)))
        list(add_articles(articles, next(scraped)))

        self.assertEqual(5, len(articles))

        tree = [articles[0], articles[3]]
        self.assertEqual(tree, get_tree(articles))

    def test_get_tree_parent_id(self):
        scraped = self.scrape()
        articles = []
        list(add_articles(articles, next(scraped)))
        list(add_articles(articles, next(scraped)))

        articles[0].id = 42

        tree = get_tree(articles)
        self.assertEqual(42, tree[0].children[0].properties['parent'])
        self.assertEqual(42, tree[0].children[1].properties['parent'])


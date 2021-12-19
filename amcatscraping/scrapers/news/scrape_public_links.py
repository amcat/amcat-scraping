import logging
import sqlite3
from pathlib import Path

from requests import HTTPError
from amcatclient import AmcatAPI

from online_scrapers import all_scrapers


def get_text(link: str) -> str:
    """
    Retrieve the text of an article using any of the scrapers from online_scrapers
    """
    for scraper in all_scrapers():
        if scraper.can_scrape(link):
            return scraper.scrape_text(link)
    logging.error(f"No scraper available for {link}")
    raise SkipArticle(f"No scraper for {link}")


def get_articles(conn, where="status is 'public'", n=100):
    """
    Retrieve articles to scrape from local db
    """
    cur = conn.cursor()
    cur.execute(f"SELECT public_link as url, title, medium as publisher, date FROM articles where {where} limit {n}")
    colnames = [x[0] for x in cur.description]
    rows = cur.fetchall()
    return [dict(zip(colnames, r)) for r in rows]


class SkipArticle(Exception):
    pass

def scrape_article(article: dict) -> str:
    """
    Retrieve the text for an online article using online_scrapers
    Article should be a dict containing at least a url and title
    """
    link = article['url']
    if ('video' in link) or ('redirect' in link) or ('Liveblog' in article['title']):
        raise SkipArticle("Video/redirect/liveblog")
    try:
        text = get_text(link)
    except HTTPError as err:
        if (err.response.status_code == 404) or (err.response.status_code == 403) or (err.response.status_code == 410):
            logging.error(f"Article not found (404, 403): {link}")
            raise SkipArticle("404")
        else:
            raise
    if not text:
        raise SkipArticle("Empty")
    return text


def set_status(conn, articles, status='done'):
    """
    Upoate the status of the articles in the local db
    """
    urls = ",".join(f"'{a['url']}'" for a in articles)
    with conn:
        cur = conn.cursor()
        cur.execute(f"Update articles set status = '{status}' where public_link in ({urls})")


def scrape_articles(db, amcat_conn, project, articleset):
    while True:
        logging.info("Retrieving articles to scrape from database")
        articles = get_articles(db)
        if not articles:
            break
        to_save = []
        to_skip = []

        for i, article in enumerate(articles):
            logging.info(f"[{i + 1}/{len(articles)}] Scraping article {article['url']}")
            try:
                print(article['url'])
                article['text'] = scrape_article(article)
                to_save.append(article)
            except SkipArticle:
                to_skip.append(article)

        logging.info(f"Saving {len(to_save)} articles, skipped {len(to_skip)}")

        amcat_conn.create_articles(project, articleset, to_save)
        set_status(conn, to_save, status='done')
        set_status(conn, to_skip, status='skip')

    logging.info("DONE")


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s %(name)-12s %(levelname)-5s] %(message)s')
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("db", help="Database name", type=Path)
    parser.add_argument("amcat", help="AmCAT host to connect to")
    parser.add_argument("project", help="AmCAT project")
    parser.add_argument("articleset", help="AmCAT articleset")
    args = parser.parse_args()

    if not args.db.exists():
        raise Exception(f"Database {args.db} does not exist")
    conn = sqlite3.connect(str(args.db))
    c = AmcatAPI(args.amcat)
    logging.info(f"Scraping articles from {args.db} to {args.amcat} set {args.project}:{args.articleset}")
    scrape_articles(conn, c, args.project, args.articleset)


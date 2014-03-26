"""Running scrapers daily"""

class Daily(object):
    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("date")
        self.date = parser.parse_args().date

    def run(self):
        # Gather scrapers that ought to run daily
        # For each scraper:
            # Get arguments
            # Try:
                # Run scraper with arguments, get results
            # Except Exception:
                # report exception
                # continue
            # Report back with results

    def _get_scrapers(self):
        pass

    def _report(self, scraper, articles):
        pass

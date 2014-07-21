import nrc

class NRCHandelsbladScraper(nrc.NRCScraper):
    def __init__(self, *args, **kwargs):
        super(NRCHandelsbladScraper, self).__init__(*args, **kwargs)
        self._props['defaults']['medium'] = "NRC Handelsblad"
        self._props['defaults']['insertscript'] = "NRCHandelsbladScraper"

    nrc_version = "NH"

if __name__ == '__main__':
    from amcatscraping.tools import setup_logging
    setup_logging()
    NRCHandelsbladScraper().run()

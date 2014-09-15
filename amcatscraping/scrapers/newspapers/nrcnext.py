import nrc

class NRCNextScraper(nrc.NRCScraper):
    def __init__(self, *args, **kwargs):
        super(NRCNextScraper, self).__init__(*args, **kwargs)
        self._props['defaults']['medium'] = "NRC.NEXT"
        self._props['defaults']['insertscript'] = "NRCNextScraper"

    nrc_version = "NN"

if __name__ == '__main__':
    from amcatscraping.tools import setup_logging
    setup_logging()
    NRCNextScraper().run()

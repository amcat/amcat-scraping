import pcm

class AlgemeenDagbladScraper(pcm.PCMScraper):
    def __init__(self,*args,**kwargs):
        super(AlgemeenDagbladScraper, self).__init__(*args, **kwargs)
        self._props['defaults']['medium'] = 'Algemeen Dagblad'
        self._props['defaults']['insertscript'] = 'AlgemeenDagbladScraper'

    domain = "ad.nl"
    paper_id = 8001
    context_id = "AD"


if __name__ == '__main__':
    from amcatscraping.tools import setup_logging
    setup_logging()
    AlgemeenDagbladScraper().run()

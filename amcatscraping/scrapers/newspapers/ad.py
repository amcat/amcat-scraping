###########################################################################
#          (C) Vrije Universiteit, Amsterdam (the Netherlands)            #
#                                                                         #
# This file is part of AmCAT - The Amsterdam Content Analysis Toolkit     #
#                                                                         #
# AmCAT is free software: you can redistribute it and/or modify it under  #
# the terms of the GNU Lesser General Public License as published by the  #
# Free Software Foundation, either version 3 of the License, or (at your  #
# option) any later version.                                              #
#                                                                         #
# AmCAT is distributed in the hope that it will be useful, but WITHOUT    #
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or   #
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public     #
# License for more details.                                               #
#                                                                         #
# You should have received a copy of the GNU Lesser General Public        #
# License along with AmCAT.  If not, see <http://www.gnu.org/licenses/>.  #
###########################################################################
from amcatscraping.scrapers.newspapers import pcm


class AlgemeenDagbladScraper(pcm.PCMScraper):
    domain = "ad.nl"
    paper_id = 8001
    context_id = "AD"
    caps_code = "ad-441"
    login_redirect = "http%3A%2F%2Fkrant.ad.nl%2F"
    publisher = "Algemeen Dagblad"
    


if __name__ == '__main__':
    from amcatscraping.tools import setup_logging
    setup_logging()
    AlgemeenDagbladScraper().run()

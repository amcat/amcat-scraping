# -*- coding: utf-8 -*-
from __future__ import unicode_literals, print_function
###########################################################################
#          (C) Vrije Universiteit, Amsterdam (the Netherlands)            #
#                                                                         #
# This file is part of AmCAT - The Amsterdam Content Analysis Toolkit     #
#                                                                         #
# AmCAT is free software: you can redistribute it and/or modify it under  #
# the terms of the GNU Affero General Public License as published by the  #
# Free Software Foundation, either version 3 of the License, or (at your  #
# option) any later version.                                              #
#                                                                         #
# AmCAT is distributed in the hope that it will be useful, but WITHOUT    #
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or   #
# FITNESS FOR A PARTICULAR PURPOSE. See the GNU Affero General Public     #
# License for more details.                                               #
#                                                                         #
# You should have received a copy of the GNU Affero General Public        #
# License along with AmCAT.  If not, see <http://www.gnu.org/licenses/>.  #
###########################################################################

from amcatscraping.scrapers.newspapers import pcm


class TrouwScraper(pcm.PCMScraper):
    domain = "trouw.nl"
    paper_id = 8004
    context_id = "NL"
    caps_code = "tr-423"
    login_redirect = "http%3A%2F%2Fwww.trouw.nl%2Ftr%2Fsecured%2Fcheck.do"
    
if __name__ == '__main__':
    from amcatscraping.tools import setup_logging
    setup_logging()
    TrouwScraper().run()

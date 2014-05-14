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

import nrc

class NRCNextScraper(nrc.NRCScraper):
    def __init__(self, *args, **kwargs):
        super(NRCNextScraper, self).__init__(*args, **kwargs)
        self._props['defaults']['medium'] = "NRC.NEXT"
        self._props['defaults']['insertscript'] = "NRCNextScraper"

    nrc_version = "NN"

if __name__ == '__main__':
    from amcatscraping.scraping.tools import setup_logging
    setup_logging()
    NRCNextScraper().run()

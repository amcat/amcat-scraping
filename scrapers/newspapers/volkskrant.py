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

import pcm

class VolkskrantScraper(pcm.PCMScraper):
    def __init__(self, *args, **kwargs):
        super(VolkskrantScraper, self).__init__(*args, **kwargs)
        self._props['defaults']['medium'] = "De Volkskrant"
        self._props['defaults']['insertscript'] = "VolkskrantScraper"

    domain = "volkskrant.nl"
    paper_id = 8002
    context_id = "NL"

if __name__ == '__main__':
    from amcatscraping.tools import setup_logging
    setup_logging()
    VolkskrantScraper().run()

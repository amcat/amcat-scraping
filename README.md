AmCAT-Scraping
==============

A seperate repository for scraping to AmCAT.

To install:
```
export INSTALLDIR=$HOME #edit this line if you want to install in a different directory

git clone https://github.com/amcat/amcat-scraping.git $INSTALLDIR/amcatscraping
git clone https://github.com/vanatteveldt/amcatclient.git $INSTALLDIR/amcatclient

# Install dependencies
sudo pip install -r $INSTALLDIR/amcatclient/requirements.txt

# To run scripts in amcatscraping, PYTHONPATH needs to be set to the directory it's in:
echo 'export PYTHONPATH=$PYTHONPATH:$INSTALLDIR' >> ~/.bashrc
```

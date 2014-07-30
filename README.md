To install:
```
cd /home/somedir
git clone https://github.com/amcat/amcat-scraping.git amcatscraping
git clone https://github.com/vanatteveldt/amcatclient.git

# we now have the following directory structure:
#somedir/
#    amcatscraping/
#    amcatclient/
#    ...

# Install dependencies
sudo pip install celery html2text mailer croniter cssselect

# To run scripts in amcatscraping, PYTHONPATH needs to be set to the directory it's in:
export PYTHONPATH='/home/somedir'
```

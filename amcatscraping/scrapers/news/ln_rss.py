from lxml import html, etree
import requests, re, datetime, csv, argparse, warnings, json, sys, time
from amcatclient.amcatclient import AmcatAPI

def login(username, password):
    url = 'https://www.vinous.com/users/sign_in'

    session = requests.Session()
    session.headers.update({'User-agent': 'Mozilla/5.0 (X11; Linux i686; rv:6.0.2) Gecko/20100101 Firefox/6.0.2'})

    ## get all input forms (because of necessary hidden input)
    page = session.get(url)
    page = html.fromstring(page.content)
    inputs = page.findall('.//input')

    ## create username and password payload, and add all other input forms with default values
    payload = {"user[email]": username,
           "user[password]": password}

    ## add all other input forms if they have default values (this often captures required checkboxes and authenticity tokens)
    for input in inputs:
        if input.name in payload.keys(): continue
        a = input.attrib
        if not 'value' in a.keys(): continue
        payload[a['name']] = a['value']

    r = session.post(url, data=payload)
    return(session)

def scrape(session, conn, project_id, set_id, done_urls=[]):
    for page_url in getPages(session, 6550):
        print(page_url)
        for i in range(0,10):
            try:
                w = []
                for a in getArticles(session, page_url, done_urls):
                    w.append(a)
                    articles = conn.create_articles(project=project_id, articleset=set_id, json_data=w)
                    break
            except:
            	print('Ooopps!!!!! Lets try again')
            	time.sleep(5)
                                        
                
                        

def getPages(session, startpage):
    p = session.get('http://www.vinous.com/wines')
    p = html.fromstring(p.content)
    pagination = p.find('.//div[@class="pagination"]')
    lastpage = pagination.findall('.//a')[-1]
    lastpage_url = lastpage.attrib['href']
    lastpage_count = re.search('(?<=page=)\d+', lastpage_url).group(0)

    pageurl = "http://www.vinous.com/wines?page={pagenr}&wf_dirty=false&wf_export_fields=&wf_export_format=&wf_id=&wf_match=all&wf_model=Wine&wf_name=&wf_order=vintage&wf_order_type=desc&wf_page=1&wf_per_page=25&wf_submitted=true&wf_type=WillFilter%3A%3AFilter&wine_filter[author]=&wine_filter[color]=&wine_filter[country]=&wine_filter[region_1]=&wine_filter[region_2]="
    for i in range(startpage, int(lastpage_count)+1):
        url = pageurl.format(pagenr=i)
        yield(url)

def getArticles(session, page_url, done_urls):
    articles = []

        
        ## Vinous has the nasty habit of showing empty pages now and then. Therefore, make several attempts with short intervalls before giving up
    for trycount in range(0,10):
            p = session.get(page_url)
            p = html.fromstring(p.content)
            articles = p.findall('.//tr[@class="wine"]')
            if len(articles) > 0:
                    break
            else:
                    if trycount == 9:
                            print('failed to get articles at page ', page_url.split('page')[1].split('&')[0])
                            sys.exit()
                    time.sleep(5)
                        

    for article in articles:
        ## get most information directly from the table
        artdict = {td.attrib['data-title']: td.text_content() for td in article.findall('td')}

        ## get additional information from a separate page
        arturl = 'http://www.vinous.com' + article.find('td/div[@class="wine-cta"]/a').attrib['href']
        if arturl in done_urls:
            print('\t' + 'Already in AmCAT: ' + arturl)
            continue
        print('\t' + arturl)
        artpage = session.get(arturl)
        artpage = html.fromstring(artpage.content)

        colour_country = artpage.find('.//h4[@class="country"]').text_content().strip()
        artdict['country'] = colour_country.split('from ')[1].strip()
        artdict['colour'] = colour_country.split('wine')[0].strip()
        artdict['appellation'] = artpage.find('.//ul[@class="unstyled"]/li/h4').text_content().strip().replace('\n', ' ')


        box = artpage.find('.//div[@class="box producer-details lift-up-text shelftalker-hidden"]')
        artdict['grape'] = 'missing'
        for dl in box.findall('.//dl'):
            if 'grape' in dl.text_content().lower():
                artdict['grape'] = dl.find('dd').text_content().strip()
                break

                ## to store the score in the length field it needs to be an integer. Therefore, all non integer scores (e.g., 90-91, 90+) are rounded down, and missing scores are defined as None.
        try:
            intscore = int(artdict['Score'].split('-')[0].strip('()+-/'))
        except:
            intscore = None

        art =  {"headline":"%s : %s" % (artdict['appellation'], artdict['Producer'].strip()),
                "medium": colour_country,
            "text": artdict['Tasting Note'] + '\n\nReview date: ' + artdict['Review Date'] + '\nDrinking window: ' + artdict['Drinking Window'],
            "date": "%s-01-01T00:00" % artdict['Vintage'].strip(),
            "author": artdict['Author'].strip(),
            "length": intscore,
            "section": artdict['country'],
            "byline": artdict['grape'],
            "url": arturl,
            "metastring": json.dumps(artdict)}
        yield(art)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Scrape reviews van Vinous.com')
    parser.add_argument('vinous_username')
    parser.add_argument('vinous_password')
    parser.add_argument('amcat_username')
    parser.add_argument('amcat_password')
        
    args = parser.parse_args()
    session = login(args.vinous_username, args.vinous_password)
    project_id = 1039
    set_id = 30104

    conn = AmcatAPI("https://amcat.nl", args.amcat_username, args.amcat_password)
    done_urls = [a['url'] for a in conn.search(set_id, '*', columns=['url'], page_size=10000)]

    scrape(session, conn, project_id, set_id, done_urls)



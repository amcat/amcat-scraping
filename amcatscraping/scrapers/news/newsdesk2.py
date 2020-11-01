import locale
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Tuple

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver.common.keys import Keys

# tested with firefox 72.0.2, geckodriver 0.24.0 ( 2019-01-28), and selenium 3.141.0


def dutch_strptime(date, pattern):
    loc = locale.getlocale()
    locale.setlocale(locale.LC_ALL, 'nl_NL.UTF-8')
    try:
        return datetime.strptime(date, pattern)
    finally:
        locale.setlocale(locale.LC_ALL, loc)


class InvisibleElementException(Exception):
    pass


def waits(driver, selector, by="css", timeout=60, interval=0.1, require_visible=False):
    start = time.time()
    while True:
        try:
            if by == "css":
                e = driver.find_elements_by_css_selector(selector)
            elif by == "xpath":
                e = driver.find_elements_by_xpath(selector)
            if require_visible and not e.is_displayed():
                raise InvisibleElementException()
            return e
        except (NoSuchElementException, InvisibleElementException):
            if time.time() < start + timeout:
                time.sleep(interval)
            else:
                raise


def wait(driver, selector, by="css", timeout=60, interval=0.1, require_visible=False):
    start = time.time()
    while True:
        try:
            if by == "css":
                e = driver.find_element_by_css_selector(selector)
            elif by == "xpath":
                e = driver.find_element_by_xpath(selector)
            if require_visible and not e.is_displayed():
                raise InvisibleElementException()
            return e
        except (NoSuchElementException, InvisibleElementException):
            if time.time() < start + timeout:
                time.sleep(interval)
            else:
                raise


def waitclick(driver, selector, by="css", timeout=60, interval=0.1):
    start = time.time()
    while True:
        try:
            if by == "css":
                return driver.find_element_by_css_selector(selector).click()
            elif by == "xpath":
                return driver.find_element_by_xpath(selector).click()
        except ElementClickInterceptedException:
            if time.time() < start + timeout:
                time.sleep(interval)
            else:
                raise


def insertText(element,text):
    element.click()
    element.clear()
    element.send_keys(text)


def extract_body(preview):
    """Extract body text from a preview pane"""
    # body are all p's between body and classification header
    try:
        body = wait(preview, "#JUMPTO_Body")
    except NoSuchElementException:
        body = wait(preview, "h2.SS_Banner")
        if body.text != "Graphic":
            raise Exception(f"unexpected graphic {body.text}")
    classificaton = wait(preview, "#JUMPTO_Classification")
    above_classification = classificaton.find_elements_by_xpath("preceding-sibling::p")
    below_body = body.find_elements_by_xpath("following-sibling::p")
    paras = [p for p in below_body if p in above_classification]
    return "\n\n".join(para.text for para in paras)


def extract_meta(preview):
    """Extract all metadata fields from the preview pane, returns a sequence of key, value pairs"""
    # metadata are div/span.SS_bf before body header and span.SS_bf after the classification header
    try:
        body = wait(preview, "#JUMPTO_Body")
    except NoSuchElementException:
        body = wait(preview, "h2.SS_Banner")
        if body.text != "Graphic":
            raise Exception(f"unexpected graphic {body.text}")
    classificaton = wait(preview, "#JUMPTO_Classification")
    above_body = body.find_elements_by_xpath("preceding-sibling::div/span[@class='SS_bf']")
    below_classification = classificaton.find_elements_by_xpath("following-sibling::span[@class='SS_bf']")
    for meta in above_body + below_classification:
        # Metadata is encoded as <span class="SS_bf">KEY</span>VALUE
        # So need to get the VALUE text node following the meta key
        key = meta.text.strip(':').replace(' ', '').replace('-', '')
        # selenium xpath only returns elements, and we want to get the next sibling text node, so use javascript
        JS_CMD = 'return(document.evaluate("following-sibling::text()", arguments[0]).iterateNext().textContent)'
        value = driver.execute_script(JS_CMD, meta).strip()
        yield key, value.strip(':')


def extract_date(art):
    """Get the date from an article listing element"""
    dates = art.find_elements_by_css_selector("div.dataInfo.translate dd a")
    datestr = dates[3].text
    return dutch_strptime(datestr, "%d %b %Y").isoformat()

def scrape_article(art, medium):
    """Scrape a single nexis article. Art should be a references to the result list LI element"""
    result = {}
    result['publisher'] = medium
    result['title'] = art.find_element_by_css_selector("h2.doc-title.translate").text
    result['date'] = extract_date(art)

    # open preview window by clicking on [Preview] button on right hand side of listing
    art.find_element_by_css_selector(".showResultListPanelNexisUni.btnPreview").click()
    # Wait until the preview window ('aside') is opened so we can select the text
    preview = wait(driver, "aside.ladialog,aside.gvs-dialog")
    # Extract body and metadata
    result['text'] = extract_body(preview)
    if result['text'] == "":
        result['text'] ="-"
    for key, value in extract_meta(preview):
        result[key] = value

    # Close preview pane by clicking on [Sluiten] button on bottom right
    preview.find_element_by_css_selector(".btnPreviewDocumentNexisUni").click()
    return result


def login_nexis(driver, username, password):
    driver.get("https://vu-nl.idm.oclc.org/login?url=http://www.nexisuni.com")
    login_username_field = "#frm2_submit"
    login_institute_field = "a.result.active.access"
    login_field = "#userNameInput"
    pw_field = "#passwordInput"
    driver.find_elements_by_css_selector(login_username_field)[0].click()
    driver.find_elements_by_css_selector(login_institute_field)[1].click()
    driver.find_elements_by_css_selector(login_field)[0].send_keys(username)
    driver.find_elements_by_css_selector(pw_field)[0].send_keys(password)
    driver.find_elements_by_css_selector("#submitButton")[0].click()


def wait_loadbox(driver):
    """
    Wait until the 'loadbox' is displayed and hidden again
     (full screen modal spinning wheel shown when retrieving articles)
     """
    loadbox = wait(driver, "#loadbox")
    while not loadbox.is_displayed():
        time.sleep(0.1)
    while loadbox.is_displayed():
        time.sleep(0.1)
    time.sleep(0.5) # just to be sure


def set_result_sort(driver, direction="datedescending"):
    """Sort the article result list"""
    # 1- Click on button "Sorten op: [button: Relevantie]"
    wait(driver, "#sortbymenulabel").click()
    # 2- Select "Datum: nieuwste eerst" from resulting dropdown list
    wait(driver, f"//li[@data-menu='sortby']//button[@data-value='{direction}']", by="xpath").click()
    # 3- Wait until dropdown is hidden so preview button is exposed again
    wait_loadbox(driver)

def scrape_nexis(driver, medium, from_date, to_date, query):
    # switch to power search
    wait(driver, "ul.advancesearch.getadoc button").click()
    # enter query
    insertText(driver.find_element_by_css_selector("input.searchterm-input-box"), query)
    # select medium
    driver.find_element_by_css_selector(".source-selector input").send_keys(medium)
    wait(driver, ".source-selector span.highlight").click()
    waitclick(driver, "button.search")
    try:
        minpicker = wait(driver, ".date-form .min-picker input")
    except NoSuchElementException:
    #if not minpicker.is_displayed():
        # click on tijdlijn sidebar
        wait(driver, '//button[@id="podfiltersbuttondatestr-news"]', by="xpath").click()
        #wait(driver, '//button[@data-filtertype="datestr-news"]', by="xpath").click()
        minpicker = wait(driver, ".date-form .min-picker input", timeout=5, require_visible=True)

    minpicker.send_keys((Keys.BACKSPACE*10) + from_date.strftime("%d/%m/%Y"))
    maxpicker = driver.find_element_by_css_selector(".date-form .max-picker input")
    maxpicker.send_keys((Keys.BACKSPACE*10) + to_date.strftime("%d/%m/%Y"))

    # click on 'save' button but wait until the loadbox is disappeared again
    driver.find_element_by_css_selector(".date-form button.save").click()
    wait_loadbox(driver)

    set_result_sort(driver, direction='datedescending')


    while True:
        article_list = waits(driver, 'ol.nexisuni-result-list li')
        yield [scrape_article(art, medium) for art in article_list]
        next = driver.find_elements_by_css_selector("nav.pagination li")[-1]
        if next.get_attribute("class") == "disabled":
            break
        next.click()
        wait_loadbox(driver)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("amcat_host", help="Hostname of AmCAT server to upload articles to")
    parser.add_argument("amcat_project", help="Project ID in AmCAT server", type=int)
    parser.add_argument("amcat_set", help="Article Set ID in AmCAT server", type=int)
    parser.add_argument("login", help="Login LN")
    parser.add_argument("password", help="Password LN")
    parser.add_argument("medium", help="Medium to get articles from")
    parser.add_argument("from_date", help="Date from which to get articles")
    parser.add_argument("to_date", help="Date to which to get articles")
    parser.add_argument("query", help="searchstring")
    parser.add_argument("--geckodriver", help="Path of geckodriver executable (default=~/geckodriver)")

    args = parser.parse_args()

    from amcatclient import AmcatAPI
    conn = AmcatAPI(args.amcat_host)

    driver_path = args.geckodriver or str(Path.home() / "geckodriver")
    driver = webdriver.Firefox(executable_path=driver_path)

    from_date = datetime.strptime(args.from_date, "%Y-%m-%d")
    to_date = datetime.strptime(args.to_date, "%Y-%m-%d")

    login_nexis(driver, args.login, args.password)

    for page in scrape_nexis(driver, args.medium, from_date, to_date, args.query):
        conn.create_articles(args.amcat_project, args.amcat_set, page)




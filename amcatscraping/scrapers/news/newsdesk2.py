import time
import random

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from datetime import datetime

driver = webdriver.Firefox(executable_path=r"/home/nel/Downloads/geckodriver")


driver.get("http://vu-nl.idm.oclc.org/login?url=http://vu-nl.idm.oclc.org/login?url=http://www.nexisuni.com")
login_username_field = "#frm2_submit"
login_institute_field = "a.result.active.access"
login_field = "#userNameInput"
pw_field = "#passwordInput"
login = "wat200"
password = "rd255XT"
zoekterm ="blok"

def wait(css_selector, timeout=60, interval=0.1):
    start = time.time()
    while True:
        try:
            return driver.find_element_by_css_selector(css_selector)
        except NoSuchElementException:
            if time.time() < start + timeout:
                time.sleep(interval)
            else:
                raise

def actCool(min_time,max_time, be_visibly_cool=False):
    seconds = round(random.uniform(min_time,max_time),2)
    if be_visibly_cool == True: logging.info(f"Acting cool for {seconds} seconds")
    time.sleep(seconds)

def insertText(element,text):
    element.click()
    element.clear()
    element.send_keys(text)
    actCool(1,2)

driver.find_elements_by_css_selector(login_username_field)[0].click()
driver.find_elements_by_css_selector(login_institute_field)[1].click()
driver.find_elements_by_css_selector(login_field)[0].send_keys(login)
driver.find_elements_by_css_selector(pw_field)[0].send_keys(password)
driver.find_elements_by_css_selector("#submitButton")[0].click()

wait("ul.advancesearch.getadoc button").click()
insertText(driver.find_element_by_css_selector("input.searchterm-input-box"), zoekterm)

# Click on button to open options for dates
driver.find_element_by_xpath('//*[@class="icon la-TriangleDownAfter" and contains(text(), "Alle beschikbare datums")]').click()
# Select date between x and y
driver.find_element_by_xpath('//span[@data-value="datebetween"]').click()
#driver.find_element_by_xpath('//button[@class="icon.la-Calendar"]').click()
driver.find_elements_by_css_selector("#datepicker")[0].click()


#insertText(driver.find_element_by_xpath("//div[@class='date-from']"), '01 Apr 2019')
#insertText(driver.find_element_by_xpath("//div[@class='date-to']"), '01 Jan 2020')



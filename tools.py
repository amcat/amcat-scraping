from html2text import html2text as html_to_text
from amcat.tools.toolkit import readDate
from lxml import html, etree


def html2text(data):
    if type(data) == list:
        return "".join([html2text(bit) for bit in data])
    elif type(data) in (str, unicode):
        return html_to_text(data)
    elif type(data) in (html.HtmlElement, etree._Element):
        return html_to_text(html.tostring(data)).strip()

def read_date(string, **kwargs):
    return readDate(string, **kwargs)

def parse_form(form):
    return {inp.get('name') : inp.get('value', '').encode('utf-8') for inp in form.cssselect('input')}




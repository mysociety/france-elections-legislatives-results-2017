# -*- coding: utf-8 -*-

# This is a template for a Python scraper on morph.io (https://morph.io)
# including some code snippets below that you should find helpful

import json
import re
from urlparse import urljoin

import scraperwiki
import sqlite3
import lxml.html


def tidy_element_text(element):
    s = element.text_content()
    return re.sub(r'\s+', ' ', s.strip())


def fix_name(messy_name):
    name = re.sub('^Mme \.', 'Mme', messy_name)
    return re.sub('MARIE SARA', 'Marie SARA', name)


def parse_table(table, department_id, cir_number, tour):
    rows = table.cssselect('tr')
    fields = [tidy_element_text(th) for th in rows[0].cssselect('th')]
    results = []
    for row in rows[1:]:
        d = dict(zip(fields, [tidy_element_text(td) for td in row.cssselect('td')]))
        d['area_id'] = 'ref:{0}-{1:02d}'.format(department_id, int(cir_number))
        d['dep_id'] = department_id
        d['cir_number'] = cir_number
        d['Tour'] = tour
        d['Liste des candidats'] = fix_name(d['Liste des candidats'])
        d['gender'] = ''
        if d['Liste des candidats'].find('M. ') == 0:
            d['gender'] = 'M'
        elif d['Liste des candidats'].find('Mme ') == 0:
            d['gender'] = 'F'
        results.append(d)
    return results


def scrape_cir(cir_url, department_id, cir_number):
    results = []
    cir_html = scraperwiki.scrape(cir_url)
    root = lxml.html.fromstring(cir_html)
    first_round_table = None
    second_round_table = None
    for h3 in root.cssselect('h3'):
        tidied = tidy_element_text(h3)
        if tidied == u'Résultats de la circonscription au 2d tour':
            second_round_table = h3.getnext()
        elif tidied == u'Rappel des résultats de la circonscription au 1er tour':
            first_round_table = h3.getnext()
        # Some circonscriptions were decided on the first round,
        # though,
        # e.g. http://elections.interieur.gouv.fr/legislatives-2017/056/05604.html
        elif tidied == u'résultats de la circonscription au 1er tour':
            first_round_table = h3.getnext()

    if first_round_table is None and second_round_table is None:
        raise Exception, "No results found in: {0}".format(cir_url)

    for tour, table in (('1', first_round_table), ('2', second_round_table)):
        if table is None:
            continue
        data = parse_table(table, department_id, cir_number, tour)
        results += data

    # Make sure that exactly one person has elected set to 'Oui':
    winners_found = 0
    for r in results:
        elected = r['Elu(e)'].strip()
        if elected == 'Oui':
            winners_found += 1

    if winners_found != 1:
        print "{0} winners found in:".format(winners_found)
        print json.dumps(data, indent=2, sort_keys=True)
        raise Exception("Unexpected number of winners found in {0}".format(cir_url))

    return results


def scrape_department(department_url, department_id):
    results = []
    department_html = scraperwiki.scrape(department_url)
    root = lxml.html.fromstring(department_html)
    title_with_arrondissements = root.xpath(
        u"//*[contains(text(), 'Résultats par circonscriptions et arrondissements')]")
    title = root.xpath(
        u"//*[contains(text(), 'Circonscriptions législatives du département')]")
    if len(title_with_arrondissements) > 0:
        # Then this is a case like Paris where the links are in the
        # first column of the following table.
        assert len(title_with_arrondissements) == 1
        table = title_with_arrondissements[0].getnext()
        a_elements = [
            row.cssselect('td')[0].cssselect('a')[0]
            for row in table.cssselect('tr')[1:]
            if len(row) > 1
        ]
    else:
        assert len(title) == 1
        a_elements = title[0].getparent().cssselect('a')
    for a in a_elements:
        link_text = tidy_element_text(a)
        cir_number = re.search(r'^(\d+)', link_text).group(1)
        cir_rel_url = a.get('href')
        cir_url = urljoin(department_url, cir_rel_url)
        results += scrape_cir(cir_url, department_id, cir_number)
    return results


def scrape_country(country_url):
    country_html = scraperwiki.scrape(country_url)
    root = lxml.html.fromstring(country_html)
    department_options = root.cssselect('select#listeDpt option')

    results = []
    for i, option in enumerate(department_options):
        dep_rel_url = option.get('value')
        if dep_rel_url == '#':
            continue
        department_id = re.search('^(\d+[A-Z]*)', dep_rel_url).group(1)
        print dep_rel_url, department_id
        department_url = urljoin(country_url, dep_rel_url)
        results += scrape_department(department_url, department_id)
    # Wallis et Futuna has a separate link for some reason:
    dep_rel_url = './986/986.html'
    department_id = '986'
    print dep_rel_url, department_id
    results += scrape_department(
        urljoin(country_url, dep_rel_url), department_id)
    return results

data = scrape_country('http://elections.interieur.gouv.fr/legislatives-2017/')

try:
    scraperwiki.sqlite.execute('DELETE FROM data')
except sqlite3.OperationalError:
    pass
scraperwiki.sqlite.save(
    unique_keys=['area_id', 'Liste des candidats', 'Nuances', 'Tour'],
    data=data)

import os
import base64
import xmltodict
import requests
import json
from datetime import datetime
from flask import Flask, request

app = Flask(__name__)

SIGNALEN_ENDPOINT = os.getenv('SIGNALEN_ENDPOINT')
REVGEO_ENDPOINT = 'https://geodata.nationaalgeoregister.nl/locatieserver/revgeo/?type=adres&rows=1&fl=id,weergavenaam,straatnaam,huis_nlt,postcode,woonplaatsnaam,centroide_ll&distance=100'

@app.route('/', methods=['POST'])
def index():
    namespaces = {
        'http://schemas.xmlsoap.org/soap/envelope/': 'soap',
        'http://www.egem.nl/StUF/StUF0301:x': 'stuf',
        'http://www.egem.nl/StUF/sector/bg/0310:y': 'bg'
    }

    if os.getenv('DEBUG_LOGGING'):
        with open(f'input-{datetime.now().isoformat()}.xml', 'wb') as f:
            f.write(request.get_data())

    data = xmltodict.parse(request.get_data(), process_namespaces=True, namespaces=namespaces)
    body = data['soap:Envelope']['soap:Body']['http://www.egem.nl/StUF/sector/ef/0310:wloLk01']['http://www.egem.nl/StUF/sector/ef/0310:object']

    melding = body['http://www.egem.nl/StUF/sector/ef/0310:melding']
    bijlage = body['http://www.egem.nl/StUF/sector/ef/0310:bijlage']
    aangevraagdDoorGerelateerde = body['http://www.egem.nl/StUF/sector/ef/0310:isAangevraagdDoor']['http://www.egem.nl/StUF/sector/ef/0310:gerelateerde']

    omschrijving = melding['http://www.egem.nl/StUF/sector/ef/0310:omschrijvingMelding']

    emailadres = aangevraagdDoorGerelateerde['http://www.egem.nl/StUF/sector/bg/0310:sub.emailadres']
    telefoonnummer = aangevraagdDoorGerelateerde['http://www.egem.nl/StUF/sector/bg/0310:sub.telefoonnummer']

    extraElementen = body['http://www.egem.nl/StUF/StUF0301:extraElementen']['http://www.egem.nl/StUF/StUF0301:extraElement']

    longitude = None
    latitude = None

    for element in extraElementen:
        if element['@naam'] == 'longitude':
            longitude = element['#text']

        if element['@naam'] == 'latitude':
            latitude = element['#text']

    headers = {
        'Content-type': 'application/json'
    }

    data = {
        'text': omschrijving
    }

    response = requests.post(SIGNALEN_ENDPOINT + '/category/prediction', data=json.dumps(data), headers=headers)
    classification_data = response.json()

    response = requests.post(REVGEO_ENDPOINT + f'&lon={longitude}&lat={latitude}')
    revgeo_data = response.json()

    address = None
    if len(revgeo_data['response']['docs']) > 0:
        first_doc = revgeo_data['response']['docs'][0]
        address = {
            'openbare_ruimte': first_doc.get('weergavenaam', ''),
            'huisnummer': first_doc.get('huis_nlt', ''),
            'postcode': first_doc.get('postcode', ''),
            'woonplaats': first_doc.get('woonplaatsnaam', '')
        }

    data = {
        'text': omschrijving,
        'category': {
            'sub_category': classification_data['subrubriek'][0][0]
        },
        'location': {
            'address': address,
            'geometrie': {
                'type': 'Point',
                'coordinates': [ float(longitude), float(latitude) ]
            }
        },
        'reporter': {
            'email': emailadres,
            'phone': telefoonnummer,
            'sharing_allowed': False
        },
        'source': 'online',
        'incident_date_start': datetime.now().isoformat(),
    }

    response = requests.post(SIGNALEN_ENDPOINT + '/v1/public/signals/', data=json.dumps(data), headers=headers)
    signal_data = response.json()
    signal_id = signal_data['signal_id']

    bijlage_bestandsnaam = bijlage['@http://www.egem.nl/StUF/StUF0301:bestandsnaam']
    bijlage_data = bijlage['#text']

    data = {
        'signal_id': signal_id
    }

    files = {
        'file': (bijlage_bestandsnaam, base64.b64decode(bijlage_data), 'application/octet-stream')
    }

    response = requests.post(SIGNALEN_ENDPOINT + f'/v1/public/signals/{signal_id}/attachments', data=data, files=files)
    attachment_data = response.json()

    return ''

@app.route('/healthz')
def health():
    return ''

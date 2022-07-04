import os
import base64
import xmltodict
import binascii
import requests
import json
from requests.exceptions import JSONDecodeError
from datetime import datetime
from flask import Flask, Response, request
from xml.parsers.expat import ExpatError
from lib import DeliveryConfirmationMessage

app = Flask(__name__)

SIGNALEN_ENDPOINT = os.getenv('SIGNALEN_ENDPOINT')
JWT_TOKEN = os.getenv('JWT_TOKEN')

SOURCE_NAME = os.getenv('SOURCE_NAME', 'BuitenBeter')

MINIMUM_CERTAINTY = 0.41

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        return ''

    namespaces = {
        'http://schemas.xmlsoap.org/soap/envelope/': 'soap',
        'http://www.egem.nl/StUF/StUF0301:x': 'stuf',
        'http://www.egem.nl/StUF/sector/bg/0310:y': 'bg'
    }

    if os.getenv('DEBUG_LOGGING'):
        with open(f'input-{datetime.now().isoformat()}.xml', 'wb') as f:
            f.write(request.get_data())

    try:
        data = xmltodict.parse(request.get_data(), process_namespaces=True, namespaces=namespaces)
    except ExpatError:
        return 'Not a well-formatted XML document', 400

    body = data['soap:Envelope']['soap:Body']

    stuurgegevens = body['http://www.egem.nl/StUF/sector/ef/0310:wloLk01']['http://www.egem.nl/StUF/sector/ef/0310:stuurgegevens']
    referentienummer = stuurgegevens['http://www.egem.nl/StUF/StUF0301:referentienummer']

    object = body['http://www.egem.nl/StUF/sector/ef/0310:wloLk01']['http://www.egem.nl/StUF/sector/ef/0310:object']

    melding = object['http://www.egem.nl/StUF/sector/ef/0310:melding']

    betreftAdres = object['http://www.egem.nl/StUF/sector/ef/0310:plaats'].get('http://www.egem.nl/StUF/sector/ef/0310:betreftAdres')
    gerelateerde = None
    adresAanduidingGrp = None

    if betreftAdres:
        gerelateerde = betreftAdres.get('http://www.egem.nl/StUF/sector/ef/0310:gerelateerde')
    if gerelateerde:
        adresAanduidingGrp = gerelateerde.get('http://www.egem.nl/StUF/sector/bg/0310:adresAanduidingGrp')

    adres = None
    if betreftAdres and gerelateerde and adresAanduidingGrp and isinstance(adresAanduidingGrp['http://www.egem.nl/StUF/sector/bg/0310:gor.openbareRuimteNaam'], str) and isinstance(adresAanduidingGrp['http://www.egem.nl/StUF/sector/bg/0310:wpl.woonplaatsNaam'], str):
        adres = {
            'openbare_ruimte': adresAanduidingGrp['http://www.egem.nl/StUF/sector/bg/0310:gor.openbareRuimteNaam'],
            'huisnummer': adresAanduidingGrp.get('http://www.egem.nl/StUF/sector/bg/0310:aoa.huisnummer', ''),
            'postcode': '',
            'woonplaats': adresAanduidingGrp['http://www.egem.nl/StUF/sector/bg/0310:wpl.woonplaatsNaam']
        }

    bijlage = object.get('http://www.egem.nl/StUF/sector/ef/0310:bijlage')
    aangevraagdDoorGerelateerde = object['http://www.egem.nl/StUF/sector/ef/0310:isAangevraagdDoor']['http://www.egem.nl/StUF/sector/ef/0310:gerelateerde']

    omschrijvingMelding = melding['http://www.egem.nl/StUF/sector/ef/0310:omschrijvingMelding']
    waarGaatDeMeldingOver = melding['http://www.egem.nl/StUF/sector/ef/0310:waarGaatDeMeldingOver']

    emailadres = aangevraagdDoorGerelateerde['http://www.egem.nl/StUF/sector/bg/0310:sub.emailadres']
    telefoonnummer = aangevraagdDoorGerelateerde['http://www.egem.nl/StUF/sector/bg/0310:sub.telefoonnummer']

    extraElementen = object['http://www.egem.nl/StUF/StUF0301:extraElementen']['http://www.egem.nl/StUF/StUF0301:extraElement']

    longitude = None
    latitude = None

    for element in extraElementen:
        if element['@naam'] == 'longitude':
            longitude = element['#text']

        if element['@naam'] == 'latitude':
            latitude = element['#text']

    headers = {
        'Content-type': 'application/json',
        'Authorization': f'Bearer {JWT_TOKEN}'
    }

    text = 'niet ingevuld'
    if omschrijvingMelding and isinstance(omschrijvingMelding, str):
        text = omschrijvingMelding
    elif waarGaatDeMeldingOver and isinstance(waarGaatDeMeldingOver, str):
        text = waarGaatDeMeldingOver

    data = {
        'text': text
    }

    response = requests.post(SIGNALEN_ENDPOINT + '/category/prediction', data=json.dumps(data), headers=headers)

    sub_category = SIGNALEN_ENDPOINT + '/v1/public/terms/categories/overig/sub_categories/overig'

    try:
        classification_data = response.json()

        if classification_data['subrubriek'][1][0] >= MINIMUM_CERTAINTY:
            sub_category = classification_data['subrubriek'][0][0]

    except (JSONDecodeError, IndexError):
        print('Could not decode or index prediction response: ', response.text)

    data = {
        'text': text,
        'category': {
            'sub_category': sub_category
        },
        'location': {
            'address': adres,
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
        'source': SOURCE_NAME,
        'incident_date_start': datetime.now().astimezone().isoformat(),
    }

    response = requests.post(SIGNALEN_ENDPOINT + '/v1/private/signals/', data=json.dumps(data), headers=headers)

    if not response.ok:
        print('Could not create signal in Signalen: ', response.text)
        return 'Signal could not be created in Signalen', 400

    signal_data = response.json()
    signal_id = signal_data.get('signal_id')
    if not signal_id:
        return 'Could not fetch Signal id from Signal post', 400

    if bijlage:
        bijlage_data = bijlage.get('#text')
        if not bijlage_data:
            return 'Could not find bijlage data', 400

        bijlage_bestandsnaam = bijlage.get('@http://www.egem.nl/StUF/StUF0301:bestandsnaam')
        if not bijlage_bestandsnaam:
            return 'Could not find bijlage bestandsnaam', 400

        data = {
            'signal_id': signal_id
        }

        try:
            files = {
                'file': (bijlage_bestandsnaam, base64.b64decode(bijlage_data), 'application/octet-stream')
            }
        except binascii.Error:
            return 'Signal is created, but provided bijlage is not correctly base64 encoded and not created', 400

        headers = {
            'Authorization': f'Bearer {JWT_TOKEN}'
        }

        response = requests.post(SIGNALEN_ENDPOINT + f'/v1/public/signals/{signal_id}/attachments/', data=data, files=files, headers=headers)
        if not response.ok:
            print('Could not create attachment in Signalen: ', response.text)
            return 'Could not create attachment in Signalen', 400

        attachment_data = response.json()


    content = DeliveryConfirmationMessage(referentienummer, signal_id)
    return Response(content.tostring(), mimetype='text/xml')

@app.route('/healthz')
def health():
    return ''

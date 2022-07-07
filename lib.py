import re
import uuid
from datetime import datetime
from lxml import etree
from lxml.builder import ElementMaker

nsmap_soap = {
    'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
    'xs': 'http://www.w3.org/2001/XMLSchema',
}

nsmap_stuf_xsi = {
    'StUF': 'http://www.egem.nl/StUF/StUF0301',
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
}

nsmap_stuf = {
    None: 'http://www.egem.nl/StUF/StUF0301'
}

soap = ElementMaker(namespace='http://schemas.xmlsoap.org/soap/envelope/', nsmap=nsmap_soap)
stuf_xsi = ElementMaker(namespace='http://www.egem.nl/StUF/StUF0301', nsmap=nsmap_stuf_xsi)
stuf = ElementMaker(namespace='http://www.egem.nl/StUF/StUF0301', nsmap=nsmap_stuf)

class DeliveryConfirmationMessage:
    def __init__(self, cross_ref_number, signal_id):
        self.cross_ref_number = cross_ref_number
        self.signal_id = signal_id

    def tostring(self):
        berichtcode = stuf.berichtcode('Bv03')

        organisatie = stuf.organisatie('Signalen')
        applicatie = stuf.applicatie('Signalen')
        zender = stuf.zender(organisatie, applicatie)

        organisatie = stuf.organisatie('Gemeente')
        applicatie = stuf.applicatie('ESB')
        ontvanger = stuf.ontvanger(organisatie, applicatie)

        referentienummer = stuf.referentienummer(str(uuid.uuid4()))
        tijdstipBericht = stuf.tijdstipBericht(datetime.today().strftime('%Y%m%d%H%M%S'))
        crossRefnummer = stuf.crossRefnummer(self.cross_ref_number)

        stuurgegevens = stuf.stuurgegevens(berichtcode, zender, ontvanger, referentienummer, tijdstipBericht, crossRefnummer)

        bericht = stuf_xsi.Bv03Bericht(stuurgegevens)
        body = soap.Body(bericht)
        envelope = soap.Envelope(body)

        return etree.tostring(envelope, pretty_print=True, xml_declaration=True, encoding='UTF-8')


def is_valid_email(email):
    email_regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

    if re.fullmatch(email_regex, email):
        return True

    return False

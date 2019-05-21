from django.test import TestCase

from .factories import DRCCMISConnectionFactory


class ModelTests(TestCase):
    def test_get_cmis_properties(self):
        koppeling = DRCCMISConnectionFactory()
        document = koppeling.enkelvoudiginformatieobject
        self.assertEqual(koppeling.get_cmis_properties(), {
            'drc:documenttaal': document.taal,
            'drc:documentLink': '',
            'cmis:name': document.titel,
            'drc:identificatie': document.identificatie,
            'drc:documentcreatiedatum': document.creatiedatum,
            'drc:documentontvangstdatum': None,
            'drc:documentbeschrijving': document.beschrijving,
            'drc:documentverzenddatum': None,
            'drc:vertrouwelijkaanduiding': document.vertrouwelijkheidaanduiding,
            'drc:documentauteur': document.auteur,
            'drc:documentstatus': '',
            'drc:dct.omschrijving': 'https://example.com/ztc/api/v1/catalogus/1/informatieobjecttype/1'
        })

    def test_get_cmis_properties_with_mapping(self):
        koppeling = DRCCMISConnectionFactory()
        koppeling.CMIS_MAPPING = {'anders': 'taal'}
        self.assertEqual(koppeling.get_cmis_properties(), {'anders': koppeling.enkelvoudiginformatieobject.taal})

    def test_get_cmis_properties_with_none_values(self):
        koppeling = DRCCMISConnectionFactory()
        koppeling.CMIS_MAPPING = {'anders': 'ontvangstdatum'}
        self.assertEqual(koppeling.get_cmis_properties(), {'anders': None})

    def test_get_cmis_properties_with_none_values_allow_none_false(self):
        koppeling = DRCCMISConnectionFactory()
        koppeling.CMIS_MAPPING = {'anders': 'ontvangstdatum'}
        self.assertEqual(koppeling.get_cmis_properties(allow_none=False), {'anders': ''})

    def test_update_cmis_properties(self):
        koppeling = DRCCMISConnectionFactory()
        koppeling.update_cmis_properties({})

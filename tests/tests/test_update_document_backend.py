from datetime import datetime
from io import BytesIO

from django.test import TestCase

from tests.app.backend import BackendException
from tests.tests.factories import EnkelvoudigInformatieObjectFactory
from tests.tests.mixins import DMSMixin

from drc_cmis import settings
from drc_cmis.backend import CMISDRCStorageBackend
from drc_cmis.client.exceptions import DocumentConflictException
from drc_cmis.models import CMISConfig, CMISFolderLocation


class CMISUpdateDocumentTests(DMSMixin, TestCase):
    def setUp(self):
        super().setUp()

        self.backend = CMISDRCStorageBackend()
        location = CMISFolderLocation.objects.create(location=settings.BASE_FOLDER_LOCATION)
        config = CMISConfig.get_solo()
        config.locations.add(location)

    def test_update_document_no_document(self):
        eio = EnkelvoudigInformatieObjectFactory()
        eio_dict = eio.__dict__

        eio_dict['titel'] = 'test-titel-die-unique-is'

        with self.assertRaises(BackendException):
            self.backend.update_document(eio_dict['identificatie'], 'test_lock', eio_dict.copy(), BytesIO(b'some content2'))

    def test_update_document(self):
        eio = EnkelvoudigInformatieObjectFactory()
        eio_dict = eio.__dict__

        document = self.backend.create_document(eio_dict.copy(), BytesIO(b'some content'))
        self.assertIsNotNone(document)
        self.assertEqual(document.identificatie, str(eio.identificatie))

        lock = self.backend.lock_document(document.url.split('/')[-1])
        self.assertIsNotNone(lock)

        eio_dict['titel'] = 'test-titel-die-unique-is'

        updated_document = self.backend.update_document(document.url.split('/')[-1], lock, eio_dict.copy(), BytesIO(b'some content2'))

        self.assertNotEqual(document.titel, updated_document.titel)

    def test_update_document_no_stream(self):
        eio = EnkelvoudigInformatieObjectFactory()
        eio_dict = eio.__dict__
        document = self.backend.create_document(eio_dict.copy(), BytesIO(b'some content'))
        self.assertIsNotNone(document)
        self.assertEqual(document.identificatie, str(eio.identificatie))

        lock = self.backend.lock_document(document.url.split('/')[-1])
        self.assertIsNotNone(lock)

        eio_dict['titel'] = 'test-titel-die-unique-is'
        updated_document = self.backend.update_document(document.url.split('/')[-1], lock, eio_dict.copy(), None)

        self.assertNotEqual(document.titel, updated_document.titel)

    def test_update_document_not_locked(self):
        eio = EnkelvoudigInformatieObjectFactory()
        eio_dict = eio.__dict__
        document = self.backend.create_document(eio_dict.copy(), BytesIO(b'some content'))
        self.assertIsNotNone(document)
        self.assertEqual(document.identificatie, str(eio.identificatie))

        eio_dict['titel'] = 'test-titel-die-unique-is'
        with self.assertRaises(BackendException):
            self.backend.update_document(document.url.split('/')[-1], 'fake_lock', eio_dict.copy(), None)

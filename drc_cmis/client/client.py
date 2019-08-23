import codecs
import logging
import random
import string
from datetime import datetime
from io import BytesIO

from cmislib import CmisClient
from cmislib.browser.binding import BrowserBinding
from cmislib.exceptions import UpdateConflictException

from drc_cmis import settings
from drc_cmis.cmis.drc_document import Document, Folder
from drc_cmis.cmis.utils import CMISRequest

from .exceptions import (
    DocumentConflictException, DocumentDoesNotExistError, DocumentExistsError,
    DocumentLockedException, GetFirstException
)
from .mapper import mapper
from .query import CMISQuery

logger = logging.getLogger(__name__)


class CMISDRCClient(CMISRequest):
    """
    DRC client implementation using the CMIS protocol.

    This class makes it easier to query for everything you need.
    """

    documents_in_folders_query = CMISQuery("SELECT * FROM drc:document WHERE %s")
    find_folder_by_case_url_query = CMISQuery("SELECT * FROM drc:zaakfolder WHERE drc:zaak__url='%s'")

    document_via_identification_query = CMISQuery(
        "SELECT * FROM drc:document WHERE drc:document__identificatie = '%s' %s"
    )
    document_via_cmis_id_query = CMISQuery(
        "SELECT * FROM drc:document WHERE cmis:objectId = 'workspace://SpacesStore/%s;1.0' %s"
    )

    _repo = None
    _root_folder = None
    _base_folder = None

    @property
    def _get_base_folder(self):
        if not self._base_folder:
            self.setup()
            base = self._get(self.root_url)
            for folder_response in base['objects']:
                folder = Folder(folder_response['object'])
                if folder.name == 'DRC':
                    self._base_folder = folder
        return self._base_folder

    # ZRC Notification client calls.
    def get_or_create_zaaktype_folder(self, zaaktype):
        """
        Create a folder with the prefix 'zaaktype-' to make a zaaktype folder

        """

        properties = {
            "cmis:objectTypeId": "F:drc:zaaktypefolder",
            mapper("url", "zaaktype"): zaaktype.get("url"),
            mapper("identificatie", "zaaktype"): zaaktype.get("identificatie"),
        }

        folder_name = f"zaaktype-{zaaktype.get('omschrijving')}-{zaaktype.get('identificatie')}"
        cmis_folder = self._get_or_create_folder(folder_name, self._get_base_folder, properties)
        return cmis_folder

    def get_or_create_zaak_folder(self, zaak, zaaktype_folder):
        """
        Create a folder with the prefix 'zaak-' to make a zaak folder

        """

        properties = {
            "cmis:objectTypeId": "F:drc:zaakfolder",
            mapper("url", "zaak"): zaak.get("url"),
            mapper("identificatie", "zaak"): zaak.get("identificatie"),
            mapper("zaaktype", "zaak"): zaak.get("zaaktype"),
            mapper("bronorganisatie", "zaak"): zaak.get("bronorganisatie"),
        }
        cmis_folder = self._get_or_create_folder(f"zaak-{zaak.get('identificatie')}", zaaktype_folder, properties)
        return cmis_folder

    # DRC client calls.
    def create_document(self, identification, data, content=None):
        """
        Create a cmis document.

        Args:
            identification (str): A unique identifier for the document.
            data (dict): A dict with all the data that needs to be saved on the document.
            content (BytesStream): The content of the document.

        Returns:
            AtomPubDocument: A cmis document.

        Raises:
            DocumentExistsError: when a document already uses the same identifier.

        """

        self._check_document_exists(identification)

        now = datetime.now()

        if content is None:
            content = BytesIO()

        year_folder = self._get_or_create_folder(str(now.year), self._get_base_folder)
        month_folder = self._get_or_create_folder(str(now.month), year_folder)
        day_folder = self._get_or_create_folder(str(now.day), month_folder)
        properties = self._build_properties(identification, data)

        # Make sure that the content is set.
        content.seek(0)
        return day_folder.create_document(
            name=properties.pop("cmis:name"),
            properties=properties,
            content_file=content,
        )

    def get_cmis_documents(self, filters=None, page=1, results_per_page=100):
        """
        Gives a list of cmis documents.

        Args:
            filters (dict): A dict of filters that need to be applied to the search.

        Returns:
            AtomPubDocument: A list of CMIS documents.

        """
        filter_string = self._build_filter(filters, strip_end=True)
        query = "SELECT * FROM drc:document WHERE drc:document__verwijderd='false'"
        if filter_string:
            query += f' AND {filter_string}'

        data = {
            "cmisaction": "query",
            "statement": query,
        }

        skip_count = 0
        if page:
            results_per_page = results_per_page
            max_items = results_per_page
            skip_count = page * results_per_page - results_per_page

            data["maxItems"] = max_items
            data["skipCount"] = skip_count

        json_response = self._request(data)
        results = self._get_all(json_response, Document)
        return {
            'has_next': json_response['hasMoreItems'],
            'total_count': json_response['numItems'],
            'has_prev': skip_count > 0,
            'results': results,
        }

    def get_cmis_document(self, identification, document_query=None, filters=None):
        """
        Given a cmis document instance.

        :param identification.
        :return: :class:`AtomPubDocument` object
        """
        import traceback
        import sys
        traceback.print_exc()
        print(sys.exc_info()[0])
        if not document_query:
            document_query = self.document_via_identification_query

        filter_string = self._build_filter(filters, filter_string="AND ", strip_end=True)
        query = document_query(identification, filter_string)

        data = {
            "cmisaction": "query",
            "statement": query,
        }

        json_response = self._request(data)
        try:
            return self._get_first(json_response, Document)
        except GetFirstException:
            import traceback
            import sys
            traceback.print_exc()
            print(sys.exc_info()[0])
            error_string = "Document met identificatie {} bestaat niet in het CMIS connection".format(identification)
            raise DocumentDoesNotExistError(error_string)

    def update_cmis_document(self, identification, data, content=None):
        cmis_doc = self.get_cmis_document(identification)

        try:
            pwc = cmis_doc.checkout()
        except UpdateConflictException as exc:
            raise DocumentLockedException("Document was already checked out") from exc

        # build up the properties
        current_properties = cmis_doc.properties
        new_properties = self._build_properties(identification, data)

        diff_properties = {
            key: value
            for key, value in new_properties.items()
            if current_properties.get(key) != value
        }

        try:
            pwc.update_properties(diff_properties)
        except UpdateConflictException as exc:
            # Node locked!
            raise DocumentConflictException from exc

        major = False
        if content is not None:
            major = True
            pwc.setContentStream(content)

        updated_cmis_doc = pwc.checkin("Geupdate via het DRC", major)
        return updated_cmis_doc

    def delete_cmis_document(self, identification):
        """
        Update the property that the document is deleted.

        Arguments:
            identification (str): The identification of the document.

        Returns:
            AtomPubDocument: A CMIS document.

        Raises:
            DocumentConflictException: If the document could not be updated.
        """
        cmis_doc = self.get_cmis_document(identification)
        new_properties = {mapper("verwijderd"): True}

        try:
            cmis_doc.update_properties(new_properties)
        except UpdateConflictException as exc:
            # Node locked!
            raise DocumentConflictException from exc
        return cmis_doc

    # Split ########################################################################################

    def update_case_connection(self, identification, data):
        cmis_doc = self.get_cmis_document(identification)

        current_properties = cmis_doc.properties
        new_properties = self._build_case_properties(data, allow_empty=False)
        diff_properties = {
            key: value
            for key, value in new_properties.items()
            if current_properties.get(key) != new_properties.get(key)
        }

        if diff_properties:
            try:
                cmis_doc.update_properties(diff_properties)
            except UpdateConflictException as exc:
                # Node locked!
                raise DocumentConflictException from exc
        return cmis_doc

    def delete_case_connection(self, identification):
        cmis_doc = self.get_cmis_document(identification)

        connection_count = len(list(cmis_doc.getObjectParents()))
        in_zaakfolder = False

        for parent in list(cmis_doc.getObjectParents()):
            if parent.properties.get("cmis:objectTypeId") == "F:drc:zaakfolder":
                in_zaakfolder = True

        if in_zaakfolder and connection_count == 1:
            now = datetime.now()
            year_folder = self._get_or_create_folder(str(now.year), self._get_base_folder)
            month_folder = self._get_or_create_folder(str(now.month), year_folder)
            day_folder = self._get_or_create_folder(str(now.day), month_folder)

            self.move_to_case(cmis_doc, day_folder)

        # Clear properties
        current_properties = cmis_doc.properties
        new_properties = self._build_case_properties({})
        diff_properties = {
            key: value
            for key, value in new_properties.items()
            if current_properties.get(key) != new_properties.get(key)
        }

        if diff_properties:
            try:
                cmis_doc.updateProperties(diff_properties)
            except UpdateConflictException as exc:
                # Node locked!
                raise DocumentConflictException from exc
        return cmis_doc

    def move_to_case(self, cmis_doc, folder):
        parent = [parent for parent in cmis_doc.getObjectParents()][0]
        cmis_doc.move(parent, folder)

    def copy_document(self, cmis_doc, folder, data):
        """
        The copy from source is not supported via the atom pub bindings.
        So we create a new document with the same values.
        """
        properties = {}

        properties.update(**{
            'cmis:objectTypeId': cmis_doc.objectTypeId,
            'drc:document__auteur': cmis_doc.auteur,
            'drc:document__beschrijving': cmis_doc.beschrijving,
            'drc:document__bestandsnaam': cmis_doc.bestandsnaam,
            'drc:document__bronorganisatie': cmis_doc.bronorganisatie,
            'drc:document__creatiedatum': cmis_doc.creatiedatum,
            'drc:document__formaat': cmis_doc.formaat,
            'drc:document__identificatie': cmis_doc.identificatie,
            'drc:document__indicatiegebruiksrecht': cmis_doc.indicatiegebruiksrecht,
            'drc:document__informatieobjecttype': cmis_doc.informatieobjecttype,
            'drc:document__integriteitalgoritme': cmis_doc.integriteitalgoritme,
            'drc:document__integriteitdatum': cmis_doc.integriteitdatum,
            'drc:document__integriteitwaarde': cmis_doc.integriteitwaarde,
            'drc:document__link': cmis_doc.link,
            'drc:document__ondertekeningdatum': cmis_doc.ondertekeningdatum,
            'drc:document__ondertekeningsoort': cmis_doc.ondertekeningsoort,
            'drc:document__ontvangstdatum': cmis_doc.ontvangstdatum,
            'drc:document__status': cmis_doc.status,
            'drc:document__taal': cmis_doc.taal,
            'drc:document__titel': f"{cmis_doc.titel} - copy",
            'drc:document__vertrouwelijkaanduiding': cmis_doc.vertrouwelijkaanduiding,
            'drc:document__verwijderd': cmis_doc.verwijderd,
            'drc:document__verzenddatum': cmis_doc.verzenddatum,
            'drc:kopie_van': cmis_doc.id,  # Keep tack of where this is copied from.
        })

        new_properties = self._build_case_properties(data)
        properties.update(**new_properties)

        if not folder:
            now = datetime.now()
            year_folder = self._get_or_create_folder(str(now.year), self._get_base_folder)
            month_folder = self._get_or_create_folder(str(now.month), year_folder)
            folder = self._get_or_create_folder(str(now.day), month_folder)

        # Update the cmis:name to make it more unique
        file_name = f"{cmis_doc.titel}-{self.get_random_string()}"
        properties['cmis:name'] = file_name

        stream = cmis_doc.getContentStream()
        new_doc = folder.create_document(
            name=file_name,
            properties=properties,
            content_file=stream,
        )

        return new_doc

    def get_random_string(self, number=6):
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=number))

    def get_folder_from_case_url(self, zaak_url):
        query = self.find_folder_by_case_url_query(zaak_url)
        self.setup()

        data = {
            "cmisaction": "query",
            "statement": query,
        }

        json_response = self._get(self.root_url, data)

        if len(json_response['objects']) == 0:
            return None
        return Folder(json_response['objects'][0]['object'])

    # Private functions.
    def _get_or_create_folder(self, name, parent, properties=None):
        """
        Get or create the folder with :param:`name` in :param:`parent`.

        :param name: string, the name of the folder to create.
        :param parent: parent folder to create the folder in as subfolder.
        :param properties: dictionary with cmis and/or custom properties to
          pass to the folder object
        :return: the folder that was retrieved or created.
        """
        existing = self._get_folder(name, parent)
        if existing:
            return existing
        return parent.createFolder(name, properties=properties or {})

    def _get_folder(self, name, parent):
        existing = next((child for child in parent.getChildren() if str(child.name) == str(name)), None)
        if existing is not None:
            return existing
        return None

    def _build_filter(self, filters, filter_string="", strip_end=False):
        if filters:
            for key, value in filters.items():
                if mapper(key):
                    key = mapper(key)

                if value and value in ["NULL", "NOT NULL"]:
                    filter_string += f"{key} IS {value} AND "
                elif value:
                    filter_string += f"{key} = '{value}' AND "

        if strip_end and filter_string[-4:] == "AND ":
            filter_string = filter_string[:-4]

        return filter_string

    def _build_properties(self, identification, data):
        base_properties = {mapper(key): value for key, value in data.items() if mapper(key)}
        base_properties["cmis:objectTypeId"] = "D:drc:document"
        base_properties['cmis:name'] = f"{data.get('titel')}-{self.get_random_string()}"
        base_properties[mapper("identificatie")] = identification
        return base_properties

    def _build_case_properties(self, data, allow_empty=True):
        props = {}
        if data.get("object") or allow_empty:
            props[mapper("object", "connection")] = data.get("object")
        if data.get("object_type") or allow_empty:
            props[mapper("object_type", "connection")] = data.get("object_type")
        if data.get("aard_relatie") or allow_empty:
            props[mapper("aard_relatie", "connection")] = data.get("aard_relatie")
        if data.get("titel") or allow_empty:
            props[mapper("titel", "connection")] = data.get("titel")
        if data.get("beschrijving") or allow_empty:
            props[mapper("beschrijving", "connection")] = data.get("beschrijving")
        if data.get("registratiedatum") or allow_empty:
            props[mapper("registratiedatum", "connection")] = data.get("registratiedatum")

        return props

    def _check_document_exists(self, identification):
        try:
            self.get_cmis_document(identification, self.document_via_identification_query)
        except DocumentDoesNotExistError:
            pass
        else:
            error_string = "Document identificatie {} is niet uniek".format(identification)
            raise DocumentExistsError(error_string)


cmis_client = CMISDRCClient()

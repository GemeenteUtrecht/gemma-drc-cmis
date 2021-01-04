from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


class Id:
    pass


class Url:
    pass


@dataclass
class EnkelvoudigInformatieObject:
    version_label: Decimal
    object_type_id: Id
    name: str
    integriteit_waarde: str
    titel: str
    bestandsnaam: str
    formaat: str
    ondertekening_soort: str
    beschrijving: str
    identificatie: str
    verzenddatum: date
    taal: str
    indicatie_gebruiksrecht: str
    verwijderd: bool
    status: str
    ontvangstdatum: date
    informatieobjecttype: Url
    auteur: str
    vertrouwelijkheidaanduiding: str
    begin_registratie: datetime
    ondertekening_datum: date
    bronorganisatie: str
    integriteit_datum: date
    link: Url
    creatiedatum: date
    versie: Decimal
    lock: str
    uuid: str
    integriteit_algoritme: str
    kopie_van: str


@dataclass
class Gebruiksrechten:
    uuid: str
    version_label: Decimal
    object_type_id: Id
    name: str
    einddatum: datetime
    omschrijving_voorwaarden: str
    informatieobject: Url
    startdatum: datetime
    kopie_van: str


@dataclass
class Oio:
    uuid: str
    version_label: Decimal
    object_type_id: Id
    name: str
    object_type: str
    besluit: Url
    zaak: Url
    informatieobject: Url


@dataclass
class ZaakFolderData:
    object_type_id: Id
    url: Url
    identificatie: str
    zaaktype: Url
    bronorganisatie: str


@dataclass
class ZaakTypeFolderData:
    object_type_id: Id
    url: Url
    identificatie: str


CONVERTER = {
    str: "propertyString",
    date: "propertyDateTime",
    datetime: "propertyDateTime",
    Decimal: "propertyDecimal",
    bool: "propertyBoolean",
    Id: "propertyId",
    Url: "propertyString",
}


def get_cmis_type(model: type, name: str) -> str:
    """Get the CMIS type of a property"""
    type_annotations = getattr(model, "__annotations__")
    property_type = type_annotations[name]
    return CONVERTER[property_type]

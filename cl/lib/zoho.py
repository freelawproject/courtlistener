from typing import Any, Protocol

from django.conf import settings
from django.core.cache import cache
from zohocrmsdk.src.com.zoho.api.authenticator import OAuthToken
from zohocrmsdk.src.com.zoho.crm.api import (
    HeaderMap,
    Initializer,
    ParameterMap,
)
from zohocrmsdk.src.com.zoho.crm.api.record import (
    ActionWrapper,
    APIException,
    BodyWrapper,
    Field,
    Record,
    RecordOperations,
    ResponseWrapper,
    SearchRecordsParam,
)


class HasModuleName(Protocol):
    module_name: str


def get_zoho_cache_key() -> str:
    return "zoho_token"


def build_zoho_payload_from_user(user) -> dict[str | Field, Any]:
    """
    Build a Zoho CRM payload dictionary from a User instance.

    This function maps a User’s attributes and related profile data
    to the corresponding Zoho CRM fields. Standard Zoho fields are represented
    by `Field` instances, while custom fields use string keys.

    :param user: The user whose data will be mapped to Zoho CRM fields.
    :return: A dictionary mapping Zoho field identifiers (either `Field`
    instances or string keys) to their corresponding values.
    """
    payload = {
        "CourtListener_ID": user.pk,
        Field.Leads.email(): user.email,
    }
    # Basic user info
    if user.first_name:
        payload[Field.Leads.first_name()] = user.first_name
    if user.last_name:
        payload[Field.Leads.last_name()] = user.last_name

    # Profile-related fields
    profile = user.profile
    if profile.employer:
        payload[Field.Leads.company()] = profile.employer

    if profile.city:
        payload[Field.Leads.city()] = profile.city

    if profile.state:
        payload[Field.Leads.state()] = profile.state

    if profile.zip_code:
        payload[Field.Leads.zip_code()] = profile.zip_code

    return payload


class ZohoModule:
    module_name: str = ""

    @staticmethod
    def initialize():
        refresh_token = cache.get(f"{get_zoho_cache_key()}:refresh")
        if not refresh_token:
            raise Exception(
                f"Cache miss: no value found for key {get_zoho_cache_key()}:refresh. "
                "Please run `cl_get_zoho_tokens` to refresh and store new tokens."
            )
        token = OAuthToken(
            client_id=settings.ZOHO_CLIENT_ID,
            client_secret=settings.ZOHO_CLIENT_SECRET,
            refresh_token=refresh_token,
        )
        Initializer.initialize(
            environment=settings.ZOHO_ENV,
            token=token,
            store=settings.ZOHO_STORE,
            resource_path=settings.ZOHO_RESOURCE_PATH,
        )

    @staticmethod
    def handle_api_response(response):
        """
        Handle a Zoho API response, raising exceptions on errors.

        :param response: The response object from a Zoho API call.
        :return: The data from the response if successful.
        :raises Exception: if the response is None, empty, or contains an APIException.
        """
        if response is None:
            raise Exception("Received no response from the API.")

        status_code = response.get_status_code()
        if status_code in [204, 304]:
            msg = "No Content" if status_code == 204 else "Not Modified"
            raise Exception(f"Zoho API returned no records ({msg}).")

        response_object = response.get_object()
        if response_object is None:
            raise Exception("Zoho API returned an empty response object.")

        if isinstance(response_object, ResponseWrapper | ActionWrapper):
            return response_object.get_data()

        if isinstance(response_object, APIException):
            status = response_object.get_status().get_value()
            code = response_object.get_code().get_value()
            message = response_object.get_message().get_value()
            details = response_object.get_details()

            detail_str = ", ".join(f"{k}: {v}" for k, v in details.items())
            raise Exception(
                f"Zoho API Exception [{code}] {status}: {message} | Details: {detail_str}"
            )

        raise Exception("Unexpected response type received from the Zoho API.")


class SearchRecordMixin:
    def get_record_by_cl_id_or_email(
        self: HasModuleName, cl_ids: list[int], email: list[str]
    ):
        record_operations = RecordOperations(self.module_name)
        param_instance = ParameterMap()

        ids_str = ",".join([str(i) for i in cl_ids])
        emails_str = ",".join(email)

        criteria = []
        if emails_str:
            criteria.append(f"(Email:in:{emails_str})")
        if ids_str:
            criteria.append(f"(CourtListener_ID:in:{ids_str})")

        criteria_str = " or ".join(criteria)
        param_instance.add(SearchRecordsParam.criteria, f"({criteria_str})")

        header_instance = HeaderMap()
        response = record_operations.search_records(
            param_instance, header_instance
        )

        return ZohoModule.handle_api_response(response)


class CreateRecordMixin:
    def create_record(self: HasModuleName, fields: dict[str | Field, Any]):
        """
        Create a single Zoho CRM record with the given field values.

        This method and sends a record creation request to the Zoho CRM API.
        It supports both standard Zoho fields (represented by `Field`
        instances) and custom fields (represented by string keys).

        :param fields: A mapping of Zoho fields to their new values. Keys may
            be `Field` instances for standard CRM fields or strings for custom
            fields.
        :return: The Zoho API response data, parsed and validated by
            `ZohoModule.handle_api_response`.
        """
        record_operations = RecordOperations(self.module_name)
        request = BodyWrapper()

        record = Record()
        # Populate record fields
        for key, value in fields.items():
            if isinstance(key, Field):
                record.add_field_value(key, value)
            else:
                record.add_key_value(key, value)

        # Build the request
        request.set_data([record])
        request.set_trigger(["approval", "workflow", "blueprint"])
        request.set_process(["review_process"])

        # Execute and handle response
        response = record_operations.create_records(request, HeaderMap())
        return ZohoModule.handle_api_response(response)


class UpdateRecordMixin:
    def update_record(
        self: HasModuleName, record_id: int, fields: dict[str | Field, Any]
    ):
        """
        Update a Zoho CRM record with the given field values.

        :param record_id: The Zoho CRM record ID to update.
        :param fields: A mapping of Zoho fields to their new values. Keys may be
            `Field` instances for standard CRM fields or strings for custom fields.
        :return: The Zoho API response data, parsed and validated by
            `ZohoModule.handle_api_response`.
        """
        record_operations = RecordOperations(self.module_name)
        request = BodyWrapper()

        record = Record()
        # Populate record fields
        record.set_id(record_id)
        for key, value in fields.items():
            if isinstance(key, Field):
                record.add_field_value(key, value)
            else:
                record.add_key_value(key, value)

        # Add Record instance to the list
        request.set_data([record])
        request.set_trigger(["approval", "workflow", "blueprint"])
        response = record_operations.update_record(
            record_id, request, HeaderMap()
        )
        return ZohoModule.handle_api_response(response)


class LeadsModule(
    CreateRecordMixin, UpdateRecordMixin, SearchRecordMixin, ZohoModule
):
    module_name = "Leads"


class ContactsModule(
    CreateRecordMixin, UpdateRecordMixin, SearchRecordMixin, ZohoModule
):
    module_name = "Contacts"

from django.conf import settings
from django.core.cache import cache
from zohocrmsdk.src.com.zoho.api.authenticator import OAuthToken
from zohocrmsdk.src.com.zoho.crm.api import (
    HeaderMap,
    Initializer,
    ParameterMap,
)
from zohocrmsdk.src.com.zoho.crm.api.record import (
    APIException,
    RecordOperations,
    ResponseWrapper,
    SearchRecordsParam,
)


def get_zoho_cache_key() -> str:
    return "zoho_token"


class SearchableModule:
    module_name: str = ""

    def __init__(self):
        if Initializer.get_initializer() is None:
            self.initialize()

        if not self.module_name:
            raise Exception("Subclasses must set `module_name`.")

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

    def get_record_by_cl_id_or_email(
        self, cl_ids: list[int], email: list[str]
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

        if response is None:
            raise Exception("Received no response from the Zoho API.")

        status_code = response.get_status_code()
        if status_code in [204, 304]:
            msg = "No Content" if status_code == 204 else "Not Modified"
            raise Exception(f"Zoho query returned no records ({msg}).")

        response_object = response.get_object()
        if response_object is None:
            raise Exception("Zoho API returned an empty response object.")

        if isinstance(response_object, ResponseWrapper):
            return response_object.get_data()

        elif isinstance(response_object, APIException):
            status = response_object.get_status().get_value()
            code = response_object.get_code().get_value()
            message = response_object.get_message().get_value()
            details = response_object.get_details()

            detail_str = ", ".join(f"{k}: {v}" for k, v in details.items())
            raise Exception(
                f"Zoho API Exception [{code}] {status}: {message} | Details: {detail_str}"
            )

        raise Exception("Unexpected response type received from the Zoho API.")


class LeadsModule(SearchableModule):
    module_name = "Leads"


class ContactsModule(SearchableModule):
    module_name = "Contacts"

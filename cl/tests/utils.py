from typing import Tuple

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait


def make_client(user_pk: int) -> APIClient:
    user = User.objects.get(pk=user_pk)
    token, created = Token.objects.get_or_create(user=user)
    token_header = f"Token {token}"
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=token_header)
    return client


def get_with_wait(
    wait: WebDriverWait,
    locator: Tuple[str, str],
) -> WebElement:
    """Get an element from a selenium browser without all the rigamarole

    :param wait: A webdriver wait for a bparticular browser instance
    :param locator: A two-string tuple that identifies the type of lookup and
    the lookup string for the lookup. For example, it might be:
    (By.TAG_NAME, "body")
    :return: A webelement if it can be found during the wait.
    """
    return wait.until(EC.presence_of_element_located(locator))

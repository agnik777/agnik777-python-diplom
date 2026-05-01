# backend/throttles.py
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

class RegisterThrottle(AnonRateThrottle):
    """
    Ограничение для регистрации — 3 запроса в час с одного IP.
    """
    scope = 'register'
    rate = '3/hour'

class LoginThrottle(AnonRateThrottle):
    """
    Ограничение для входа — 5 запросов в минуту с одного IP.
    """
    scope = 'login'
    rate = '5/minute'

class ConfirmEmailThrottle(AnonRateThrottle):
    """
    Ограничение для подтверждения email — 10 запросов в минуту.
    """
    scope = 'confirm_email'
    rate = '10/minute'

class PartnerUpdateThrottle(UserRateThrottle):
    """
    Ограничение для импорта прайса — 2 запроса в час от одного пользователя.
    """
    scope = 'partner_update'
    rate = '2/hour'
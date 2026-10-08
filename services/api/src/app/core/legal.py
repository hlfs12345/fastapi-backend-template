from enum import StrEnum


class LegalAcceptanceScope(StrEnum):
    USER = "USER"
    TENANT = "TENANT"


class ApplicationPlatform(StrEnum):
    WEB = "WEB"
    ANDROID = "ANDROID"
    IOS = "IOS"

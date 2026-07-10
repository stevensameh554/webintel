from enum import StrEnum


class CrawlJobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ImportantPageType(StrEnum):
    PRICING = "pricing"
    CAREERS = "careers"
    BLOG = "blog"
    CONTACT = "contact"
    ABOUT = "about"
    DOCS = "docs"
    LOGIN = "login"
    SIGNUP = "signup"
    TERMS = "terms"
    PRIVACY = "privacy"

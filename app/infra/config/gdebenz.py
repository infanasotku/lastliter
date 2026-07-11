from pydantic import BaseModel


class GdebenzSettings(BaseModel):
    fingerprint: str

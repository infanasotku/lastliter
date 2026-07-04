from pydantic import BaseModel


class AdminSettings(BaseModel):
    username: str
    password: str
    secret: str

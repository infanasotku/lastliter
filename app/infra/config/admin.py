from pydantic import BaseModel


class AdminSettings(BaseModel):
    username: str
    password: str
    secret: str
    map_url: str = "http://localhost:5173"

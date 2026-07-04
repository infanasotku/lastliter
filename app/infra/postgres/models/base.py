from typing import Annotated

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, mapped_column


class Base(DeclarativeBase): ...


strpk = Annotated[str, mapped_column(String, primary_key=True)]

from abc import ABC, abstractmethod
from typing import AsyncContextManager, Generic, Literal, TypeVar, overload

PlainContextT = TypeVar("PlainContextT")
TxContextT = TypeVar("TxContextT")


class UnitOfWork(ABC, Generic[PlainContextT, TxContextT]):
    @overload
    def begin(self, *, write: Literal[True]) -> AsyncContextManager[TxContextT]: ...
    @overload
    def begin(self, *, write: Literal[False]) -> AsyncContextManager[PlainContextT]: ...
    @abstractmethod
    def begin(self, *, write: bool) -> AsyncContextManager[TxContextT | PlainContextT]: ...

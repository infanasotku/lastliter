import logging
import re

import uvicorn.logging

from app.infra.common.correlation import get_request_context_save


class CustomLoggerMixin(logging.Formatter):
    CYAN = "\033[96m"
    RESET = "\033[0m"

    def formatMessage(self, record):
        msg = super().formatMessage(record)

        words = msg.split(" ")

        for index, word in enumerate(words):
            if "\033[" not in word:
                words[index] = re.sub(r"\[([^\s\[\]]+)\]", rf"[{self.CYAN}\1{self.RESET}]", word)

        return " ".join(words)


class DefaultLogFormatter(CustomLoggerMixin, uvicorn.logging.DefaultFormatter): ...


class AccessLogFormatter(CustomLoggerMixin, uvicorn.logging.AccessFormatter): ...


class CorrelationIdFilter(logging.Filter):
    def filter(self, record):
        ctx = get_request_context_save()
        record.correlation_id = ctx.request_id if ctx else "-"
        return True

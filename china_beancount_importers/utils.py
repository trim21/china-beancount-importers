import datetime
from typing import TypeVar

from beancount.core import data
from beancount.core.amount import Amount
from beancount.core.position import Cost, CostSpec

T = TypeVar("T")


def cast_checked(t: type[T], val: object) -> T:
    if not isinstance(val, t):
        raise TypeError("expecting type {}, got {!r} instead".format(t, val))
    return val


def make_posting(
    account: data.Account,
    units: Amount | None,
    *,
    cost: Cost | CostSpec | None = None,
    price: Amount | None = None,
    flag: data.Flag | None = None,
    meta: data.Meta | None = None,
) -> data.Posting:
    return data.Posting(account, units, cost, price, flag, meta)


def make_transaction(
    meta: data.Meta,
    date: datetime.date,
    flag: data.Flag | None = "*",
    payee: str | None = None,
    narration: str | None = None,
    tags: frozenset[str] = data.EMPTY_SET,
    links: frozenset[str] = data.EMPTY_SET,
    postings: list[data.Posting] | None = None,
) -> data.Transaction:
    if postings is None:
        postings = []
    return data.Transaction(meta, date, flag, payee, narration, tags, links, postings)

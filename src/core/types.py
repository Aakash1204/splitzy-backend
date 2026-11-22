from decimal import Decimal
from typing import Annotated

from pydantic import Field
from sqlalchemy import Numeric
from sqlalchemy.orm import mapped_column

# Strict financial precision: NUMERIC(12, 2) mapped to Python Decimal (never float)
MoneyNumeric = Numeric(precision=12, scale=2, asdecimal=True)

# SQLAlchemy 2.0 mapped_column annotations for financial fields
Money = Annotated[Decimal, mapped_column(MoneyNumeric, nullable=False)]
NullableMoney = Annotated[Decimal | None, mapped_column(MoneyNumeric, nullable=True)]

# Pydantic v2 validated decimal for financial requests/responses
MoneyDecimal = Annotated[
    Decimal,
    Field(
        ge=Decimal("0.00"),
        decimal_places=2,
        max_digits=12,
        description="Strict financial monetary amount mapped to Decimal (never float)",
    ),
]

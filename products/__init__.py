"""Credit product registry."""
from products import (
    captive_invoice_financing,
    forward_credit,
    securitised_yield_originator,
)

REGISTRY = {
    captive_invoice_financing.PRODUCT_ID: captive_invoice_financing,
    forward_credit.PRODUCT_ID: forward_credit,
    securitised_yield_originator.PRODUCT_ID: securitised_yield_originator,
}

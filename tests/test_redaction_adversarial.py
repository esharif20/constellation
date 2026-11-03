"""Generated attacks on redact(): hypothesis hunts for inputs where a secret survives."""

import base64
import string
from urllib.parse import quote, quote_plus

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from constellation.redact import REDACTED, redact

ALNUM = string.ascii_letters + string.digits
CONTEXT = st.text(alphabet=string.printable, max_size=40)  # arbitrary text before and after the secret
# No brackets or percent signs, so surrounding text cannot rebuild a value out of the "[REDACTED]" marker.
KNOWN = st.text(alphabet=ALNUM + "-_.~!*", min_size=8, max_size=40)
ADVERSARIAL = settings(max_examples=200, deadline=500)  # the deadline also catches a pattern that backtracks badly


@ADVERSARIAL
@given(prefix=CONTEXT, suffix=CONTEXT, value=KNOWN)
def test_known_value_never_survives_wherever_it_sits(prefix, suffix, value):
    assume(value not in REDACTED)

    assert value not in redact(prefix + value + suffix, known=[value])


ENCODABLE = st.text(alphabet=ALNUM + "/+ =&?\"'", min_size=8, max_size=30)


@ADVERSARIAL
@given(
    prefix=CONTEXT,
    suffix=CONTEXT,
    value=ENCODABLE,
    encode=st.sampled_from([quote_plus, lambda v: quote(v, safe=""), lambda v: base64.b64encode(v.encode()).decode()]),
)
def test_encoded_copy_of_a_known_value_never_survives(prefix, suffix, value, encode):
    encoded = encode(value)
    assume(encoded not in REDACTED)

    assert encoded not in redact(prefix + encoded + suffix, known=[value])


KEY_FORMATS = st.one_of(
    st.text(alphabet=ALNUM, min_size=36, max_size=36).map("ghp_".__add__),
    st.text(alphabet=ALNUM + "_-", min_size=20, max_size=60).map("sk-".__add__),
    st.text(alphabet=string.ascii_uppercase + string.digits, min_size=16, max_size=16).map("AKIA".__add__),
    st.text(alphabet=ALNUM + "-", min_size=10, max_size=40).map("xoxb-".__add__),
)


@ADVERSARIAL
@given(prefix=CONTEXT, suffix=CONTEXT, secret=KEY_FORMATS)
def test_key_formatted_secret_never_survives_wherever_it_sits(prefix, suffix, secret):
    assert secret not in redact(prefix + secret + suffix)


@ADVERSARIAL
@given(
    name=st.sampled_from(["token", "api_key", "apikey", "secret", "password", "passwd", "auth", "credential", "bearer"]),
    sep=st.sampled_from(["=", ": ", " = ", " ", ":"]),
    # A value starting "--" is read as the next flag (--token --prod), the one deliberate exemption.
    value=st.text(alphabet=ALNUM + "-_.~!*/+", min_size=1, max_size=30).filter(lambda v: not v.startswith("--")),
)
def test_whatever_follows_a_secret_name_is_fully_replaced(name, sep, value):
    assert redact(f"run --{name}{sep}{value} --prod") == f"run --{name}{sep}{REDACTED} --prod"


@ADVERSARIAL
@given(text=st.text(max_size=300))
def test_redact_never_crashes_and_is_idempotent(text):
    once = redact(text)

    assert redact(once) == once

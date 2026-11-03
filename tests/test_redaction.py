import base64
import json
import random
import string
from urllib.parse import quote, quote_plus

import pytest
from fakes import FakeEmbedder, FakeLLM

from constellation import scan
from constellation.redact import redact


def _t(*parts: str) -> str:
    return "".join(parts)  # secrets are assembled at runtime so no token-shaped string sits in the repo


SECRETS = {
    "github": ("{s}", _t("ghp_", "aB3dE5gH" * 4, "7jK9")),
    "anthropic": ("{s}", _t("sk-ant-", "api03-", "Zq8Lm2Xv5Nc7Bt1Hr4Ky6Wd9Pf3Sg0Ja")),
    "aws": ("{s}", _t("AKIA", "IOSFODNN7", "EXAMPLE")),
    "slack": ("{s}", _t("xoxb-", "123456789012-", "AbCdEfGhIjKlMnOpQrStUvWx")),
    "bearer": ("Authorization: Bearer {s}", _t("eyJhbGciOi", "JIUzI1NiIsInR5cCI6", "IkpXVCJ9")),
}


@pytest.mark.parametrize("context, secret", SECRETS.values(), ids=SECRETS.keys())
def test_key_shaped_secret_never_reaches_the_llm(tmp_path, context, secret):
    text = context.format(s=secret)
    (tmp_path / "skills" / "leaky").mkdir(parents=True)
    (tmp_path / "skills" / "leaky" / "SKILL.md").write_text(
        f"---\nname: leaky\ndescription: {json.dumps(f'Deploys using {text} inline')}\n---\n"
    )
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"gh": {"command": "gh-mcp", "args": ["--auth", text]}}}))
    llm = FakeLLM({})

    scan(tmp_path, llm=llm)

    assert len(llm.prompts) == 2  # both Items were sent, so the check below is not vacuous
    assert not any(secret in p for p in llm.prompts)


# Not any known key format: only exact-value matching against the config's own secret files can catch it.
TOKEN = "internal-" + "7f3a91c2e4b0" + "-prod"
PLUGIN = "plugins/cache/mkt/demo/1.0.0"

SOURCES = {
    "mcp-env": {".mcp.json": {"mcpServers": {"gh": {"command": "gh-mcp", "args": ["--auth", TOKEN], "env": {"GH_TOKEN": TOKEN}}}}},
    "settings-env": {"settings.json": {"env": {"DEPLOY_TOKEN": TOKEN}}},
    "dotenv": {".env": f'# deploy\nDEPLOY_TOKEN="{TOKEN}"\n'},
    "auth-file": {".credentials.json": {"oauth": {"accessToken": TOKEN}}},
    "plugin-mcp-env": {
        f"{PLUGIN}/.claude-plugin/plugin.json": {"name": "demo"},
        f"{PLUGIN}/.mcp.json": {"mcpServers": {"gh": {"command": "gh-mcp", "env": {"GH_TOKEN": TOKEN}}}},
    },
}


@pytest.mark.parametrize("files", SOURCES.values(), ids=SOURCES.keys())
def test_secret_values_from_the_configs_own_files_never_reach_the_llm(tmp_path, files):
    (tmp_path / "skills" / "leaky").mkdir(parents=True)
    (tmp_path / "skills" / "leaky" / "SKILL.md").write_text(f"---\nname: leaky\ndescription: Deploys with {TOKEN} inline\n---\n")
    for rel, content in files.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content))
    llm = FakeLLM({})

    scan(tmp_path, llm=llm)

    assert any("Deploys with" in p for p in llm.prompts)  # the leaky skill was sent, so the check below is not vacuous
    assert not any(TOKEN in p for p in llm.prompts)


VALUE = _t("hunter2-", "plain", "-value")  # no known format, not in any config file: only its name or position gives it away

NAMED = {
    "flag": "deploy --token <S> --prod",
    "flag-equals": "deploy --token=<S> --prod",
    "flag-compound": "run --api-key <S>",
    "url-query": "curl https://api.example.com/v1?key=<S>&page=2",
    "env-prefix": "GH_TOKEN=<S> gh api /user",
    "env-quoted": "DB_PASSWORD='<S>' migrate",
    "json": '{"client_secret": "<S>"}',
    "colon": "password: <S>",
}


@pytest.mark.parametrize("text", NAMED.values(), ids=NAMED.keys())
def test_value_under_a_secret_sounding_name_is_redacted(text):
    assert VALUE not in redact(text.replace("<S>", VALUE))


def test_harmless_text_is_left_alone():
    text = "Reads the keyboard layout from https://api.example.com/v1?page=2 and sets mode: fast"

    assert redact(text) == text


def _random(alphabet: str, n: int, seed: int) -> str:
    return "".join(random.Random(seed).choices(alphabet, k=n))  # seeded: the same "random" secrets every run


ALNUM = string.ascii_letters + string.digits
RANDOM = {
    "hex-32": _random("0123456789abcdef", 32, 1),
    "commit-sha-40": _random("0123456789abcdef", 40, 2),
    "base64-44": _random(ALNUM + "+/", 44, 3),
    "alnum-46": _random(ALNUM, 46, 4),
}


@pytest.mark.parametrize("secret", RANDOM.values(), ids=RANDOM.keys())
def test_random_looking_string_is_redacted_even_with_no_name_or_format(secret):
    assert secret not in redact(f"connects using {secret} to the host")


HARMLESS = {
    "prose": "Please redact everything that looks like a credential, but leave natural phrases and punctuation alone, even in long text.",
    "long-words": "internationalization and counterrevolutionaries are extraordinarily long dictionary words",
    "kebab-identifier": "skill-creator-plugin-marketplace-installer-v2",
    "snake-identifier": "update_user_notification_preferences_for_account_2",
    "camel-identifier": "getUserNotificationPreferencesForAccount2",
    "path": "/Users/someone/Documents/projects/constellation/src/constellation/claude_code",
    "alphabet-run": "abcdefghijklmnopqrstuvwxyz0123456789abcdefgh",
    "repeated": "a1" * 20,
}


@pytest.mark.parametrize("text", HARMLESS.values(), ids=HARMLESS.keys())
def test_long_but_not_random_text_is_left_alone(text):
    assert redact(text) == text


# Pins found by mutation testing: each input reaches exactly one rule of redact().
def test_a_hex_run_at_exactly_the_hex_entropy_bar_is_redacted():
    run = "035bec0c5bf3fcbcea30fa03ebe5af5a"  # 8 symbols x4: exactly 3.0 bits per character

    assert redact(run) != run


PINNED_AS_HARMLESS = {
    "kebab-identifier-with-high-entropy": "the-quick-brown-fox-jumps-over-a-lazy-dog-while-sphinx-of-black-quartz-judge-my-vow-v2",
    "snake-identifier-with-high-entropy": "the_quick_brown_fox_jumps_over_a_lazy_dog_while_sphinx_of_black_quartz_judge_my_vow_v2",
    "non-hex-below-the-4-bit-bar": "GPJRSMRNPMSH7HL7QKQKLQNN7KRSHMGPLJJG",  # 12 symbols x3: 3.58 bits, not hex
}


@pytest.mark.parametrize("text", PINNED_AS_HARMLESS.values(), ids=PINNED_AS_HARMLESS.keys())
def test_long_text_that_is_high_in_one_measure_but_not_random_is_left_alone(text):
    assert redact(text) == text


LETTERS_OR_DIGITS_ONLY = {
    "letters-only": "GMPXMVbyXHUfymCDaloVNiPhGgaTklZTpXCJkWJY",
    "digits-only": "7842064737287456158286830884016295263995",
}


@pytest.mark.parametrize("text", LETTERS_OR_DIGITS_ONLY.values(), ids=LETTERS_OR_DIGITS_ONLY.keys())
def test_entropy_layer_only_treats_runs_mixing_letters_and_digits_as_random(text):
    # Design limit, not a guarantee of safety: paths and identifiers look the same as random letters, so only the other layers catch these.
    assert redact(text) == text


ORDER = {
    "short-sorts-first": ("secretvalue1", "secretvalue1-Qk7pXn94"),
    "short-sorts-last": ("zzzzzzzz1", "Qk7pXn94-zzzzzzzz1"),
}


@pytest.mark.parametrize("short, long", ORDER.values(), ids=ORDER.keys())
def test_a_known_value_that_contains_another_is_removed_whole(short, long):
    assert "Qk7pXn94" not in redact(f"uses {long} here", known=[short, long])


ENCODERS = {
    "quote_plus": quote_plus,
    "quote": lambda v: quote(v, safe=""),
    "base64": lambda v: base64.b64encode(v.encode()).decode(),
}


@pytest.mark.parametrize("encode", ENCODERS.values(), ids=ENCODERS.keys())
def test_encoded_copy_of_a_value_with_space_slash_plus_and_equals_is_removed(encode):
    value = "ab cd/ef+gh=ij"
    encoded = encode(value)

    assert encoded not in redact(f"x {encoded} y", known=[value])


def test_a_run_at_exactly_the_identifier_like_limit_is_still_judged_on_entropy():
    run = "tukm2OYhznlvxmtrAxppg3xxxkJzmTcZqhnigswv"  # 32 of 40 characters lowercase: exactly 0.8, not above it

    assert redact(run) != run


def test_a_run_at_exactly_the_sequential_limit_is_still_judged_on_entropy():
    run = "UJYJ33QYK9mnopY5678QFGHI9Z7U4ZZWJUabcdUQ"  # 12 of 40 neighbouring pairs are consecutive: exactly 0.3, not above it

    assert redact(run) != run


def test_secrets_never_reach_the_embedder(tmp_path):
    key = SECRETS["github"][1]  # a key-formatted secret, caught by the format layer
    (tmp_path / "skills" / "leaky").mkdir(parents=True)
    (tmp_path / "skills" / "leaky" / "SKILL.md").write_text(f"---\nname: leaky\ndescription: Uses {key} and {TOKEN}\n---\n")
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"gh": {"command": "gh-mcp", "env": {"GH_TOKEN": TOKEN}}}}))
    embedder = FakeEmbedder({})

    scan(tmp_path, llm=FakeLLM({}), embedder=embedder)

    assert any("Uses" in t for t in embedder.texts)  # the leaky skill was embedded, so the check below is not vacuous
    assert not any(key in t or TOKEN in t for t in embedder.texts)


def test_a_secret_echoed_in_a_provider_error_never_reaches_the_warnings(tmp_path):
    (tmp_path / "skills" / "leaky").mkdir(parents=True)
    (tmp_path / "skills" / "leaky" / "SKILL.md").write_text("---\nname: leaky\ndescription: Does a thing\n---\n")
    (tmp_path / ".env").write_text(f"DEPLOY_TOKEN={TOKEN}\n")
    llm = FakeLLM({}, fail_for={"leaky": f"401 rejected credential {TOKEN}"})

    constellation = scan(tmp_path, llm=llm)

    assert any("ConnectionError" in w for w in constellation.warnings)  # the failure was reported, so the check below is not vacuous
    assert not any(TOKEN in w for w in constellation.warnings)


def test_a_secret_echoed_in_an_embedder_error_never_reaches_the_warnings(tmp_path):
    (tmp_path / ".env").write_text(f"DEPLOY_TOKEN={TOKEN}\n")
    (tmp_path / "skills" / "plain").mkdir(parents=True)
    (tmp_path / "skills" / "plain" / "SKILL.md").write_text("---\nname: plain\ndescription: Does a thing\n---\n")

    constellation = scan(tmp_path, embedder=FakeEmbedder({}, fail_with=f"401 rejected credential {TOKEN}"))

    assert any("ConnectionError" in w for w in constellation.warnings)
    assert not any(TOKEN in w for w in constellation.warnings)

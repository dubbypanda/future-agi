from unittest.mock import patch

from ee.agenthub.trace_scanner import compress


def test_missing_nltk_stopwords_uses_safe_fallback():
    with patch.object(
        compress._nltk_stopwords,
        "words",
        side_effect=LookupError("missing stopwords corpus"),
    ):
        assert compress._load_nltk_stopwords() == set()

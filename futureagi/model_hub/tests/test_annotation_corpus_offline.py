from model_hub.utils import utils


def test_annotation_corpus_builder_never_downloads_at_runtime(monkeypatch):
    def fail_download(*_args, **_kwargs):
        raise AssertionError("NLTK downloads are forbidden at application runtime")

    monkeypatch.setattr(utils.nltk, "download", fail_download)
    monkeypatch.setattr(utils.stopwords, "words", lambda language: ["the"])

    builder = utils.AnnotationCorpusBuilder()

    assert builder.stop_words == {"the"}

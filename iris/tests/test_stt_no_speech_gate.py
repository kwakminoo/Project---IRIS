"""STT no-speech gate — 세그먼트 메타데이터 기반."""

from iris.audio.stt_engine import SttSegment, evaluate_stt_result


def test_no_speech_when_high_no_speech_prob() -> None:
    segments = [
        SttSegment(
            text="한국어 음성 비서 이리스",
            no_speech_prob=0.95,
            avg_logprob=-0.2,
            compression_ratio=1.0,
        )
    ]
    result = evaluate_stt_result(
        segments,
        no_speech_threshold=0.6,
        min_avg_logprob=-1.0,
    )
    assert result.no_speech is True
    assert result.text is None


def test_accepts_speech_with_low_no_speech_prob() -> None:
    segments = [
        SttSegment(
            text="크롬 열어줘",
            no_speech_prob=0.1,
            avg_logprob=-0.3,
            compression_ratio=1.2,
        )
    ]
    result = evaluate_stt_result(
        segments,
        no_speech_threshold=0.6,
        min_avg_logprob=-1.0,
    )
    assert result.no_speech is False
    assert result.text == "크롬 열어줘"


def test_empty_segments_are_no_speech() -> None:
    result = evaluate_stt_result([], no_speech_threshold=0.6, min_avg_logprob=-1.0)
    assert result.no_speech is True
    assert result.text is None

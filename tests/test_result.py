from model_envoy import ConsultResult


def test_successful_result() -> None:
    result = ConsultResult(
        success=True,
        response="Everything looks good.",
        error=None,
        metadata={"latency_ms": 42},
    )
    assert result.success is True
    assert result.response == "Everything looks good."
    assert result.error is None
    assert result.metadata == {"latency_ms": 42}


def test_failed_result() -> None:
    result = ConsultResult(
        success=False,
        response=None,
        error="The configured model could not complete the request.",
    )
    assert result.success is False
    assert result.response is None
    assert result.error is not None


def test_defaults() -> None:
    result = ConsultResult(success=False, response=None, error=None)
    assert result.metadata == {}
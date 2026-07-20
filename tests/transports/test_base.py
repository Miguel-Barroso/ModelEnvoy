import pytest

from model_envoy.transports.base import Transport
from model_envoy import ConsultResult


def test_abstract_transport() -> None:
    with pytest.raises(TypeError):
        Transport()  # cannot instantiate abstract class


def test_concrete_subclass_works() -> None:
    class MockTransport(Transport):
        def consult(self, prompt: str) -> ConsultResult:
            return ConsultResult(
                success=True, response=prompt, error=None,
                metadata={"mock": True},
            )

    transport = MockTransport()
    result = transport.consult("test")
    assert result.success is True
    assert result.response == "test"
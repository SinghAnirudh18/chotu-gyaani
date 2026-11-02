from app.providers.llm import MockLLM
from tests.evals.runner import run


async def test_mock_llm_meets_eval_targets() -> None:
    result = await run(MockLLM(), verbose=True)
    target = result["targets"]["mock"]
    overall = result["scores"]["all"]
    assert overall["n"] >= 40
    assert overall["intent"] >= target["intent"], result["failures"]
    assert overall["entities"] >= target["entities"], result["failures"]

import math
import pytest

from backend.services.pricing_registry import PricingRegistry


@pytest.fixture()
def registry():
    """Return a fresh PricingRegistry instance using only default pricing."""
    # Pass firestore_service=None so the registry loads its baked-in defaults.
    return PricingRegistry(firestore_service=None)


def test_usd_to_credits_conversion_accuracy(registry):
    """Verify USD→credit conversion with default 5x markup for token-based pricing."""
    # Use the built-in GPT-5.2 Pro prices: $0.021 /1k prompt, $0.168 /1k completion.
    usage = {
        "prompt_tokens": 1000,   # 1K prompt tokens ⇒ $0.021 raw
        "completion_tokens": 500  # 0.5K completion tokens ⇒ $0.084 raw
    }

    calc = registry.calculate_credits("openai", "gpt-4o", usage)

    # Raw cost = 0.021 + 0.084 = 0.105 USD
    assert math.isclose(calc.raw_cost_usd, 0.105, rel_tol=1e-9)
    # With 5× markup ⇒ 0.105 * 5 = 0.525 USD ⇒ 52.5 ¢ ⇒ ceil→53 credits
    assert calc.credits == 53, "Expected 53 credits after 5× markup"
    # Ensure markup multiplier recorded correctly
    assert calc.markup_applied == 5.0


def test_job_based_pricing_conversion(registry):
    """Verify job-based pricing (e.g. DALL-E) converts correctly to credits."""
    usage = {"job_count": 1}
    calc = registry.calculate_credits("openai", "dall-e-3", usage)

    # Raw cost = 0.04 USD * 5× markup = 0.20 USD ⇒ 20 credits
    assert math.isclose(calc.raw_cost_usd, 0.04, rel_tol=1e-9)
    assert calc.credits == 20, "Expected 20 credits for single DALL-E 3 image generation"


def test_unknown_model_returns_zero_cost(registry):
    """Requesting cost for an unknown model should return zero cost and credits."""
    usage = {"prompt_tokens": 100, "completion_tokens": 100}
    calc = registry.calculate_credits("openai", "non-existent-model", usage)

    assert calc.raw_cost_usd == 0.0
    assert calc.credits == 0

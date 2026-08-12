import unittest

from market_intelligence import MarketQuote, market_priority


class MarketRankingSemanticsTests(unittest.TestCase):
    def test_listing_count_is_informational_not_liquidity_score(self):
        scarce = MarketQuote("Same Item", 1, "$1.00", 1.0, "https://example.invalid/1")
        crowded = MarketQuote("Same Item", 5000, "$1.00", 1.0, "https://example.invalid/2")
        self.assertEqual(
            market_priority(scarce, rarity_rank=6, item_type="GEAR", has_enchantments=False),
            market_priority(crowded, rarity_rank=6, item_type="GEAR", has_enchantments=False),
        )

    def test_observed_ask_price_remains_a_ranking_signal(self):
        lower = MarketQuote("Lower", 10, "$1.00", 1.0, "https://example.invalid/1")
        higher = MarketQuote("Higher", 10, "$2.00", 2.0, "https://example.invalid/2")
        self.assertGreater(
            market_priority(higher, rarity_rank=6, item_type="GEAR", has_enchantments=False),
            market_priority(lower, rarity_rank=6, item_type="GEAR", has_enchantments=False),
        )


if __name__ == "__main__":
    unittest.main()

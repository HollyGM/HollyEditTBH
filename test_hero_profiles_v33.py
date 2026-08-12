import json
import unittest
from pathlib import Path


PROFILE_FILE = Path(__file__).resolve().parent / "hero_profiles.json"


class HeroProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
        cls.heroes = cls.raw["heroes"]
        cls.default = float(cls.raw["default_unprofiled_weight"])

    def weight(self, hero_key, stat_type):
        return float(self.heroes[str(hero_key)]["weights"].get(str(stat_type), self.default))

    def test_every_hero_profile_declares_role_and_priorities(self):
        self.assertEqual(set(self.heroes), {"101", "201", "301", "401", "501", "601"})
        for profile in self.heroes.values():
            self.assertTrue(profile.get("role"))
            self.assertGreaterEqual(len(profile.get("priorities", [])), 4)

    def test_knight_prioritizes_survivability(self):
        self.assertGreater(self.weight(101, 3), self.weight(101, 1))
        self.assertGreater(self.weight(101, 5), self.default)
        self.assertGreater(self.weight(101, 12), self.default)

    def test_ranger_prioritizes_speed_crit_and_projectiles(self):
        self.assertGreater(self.weight(201, 2), self.default)
        self.assertGreater(self.weight(201, 10), self.default)
        self.assertGreater(self.weight(201, 24), self.default)

    def test_sorcerer_prioritizes_cast_cooldown_and_area(self):
        self.assertGreater(self.weight(301, 7), self.default)
        self.assertGreater(self.weight(301, 9), self.default)
        self.assertGreater(self.weight(301, 19), self.default)

    def test_priest_prioritizes_heal_cooldown_and_health(self):
        self.assertGreater(self.weight(401, 22), self.default)
        self.assertGreater(self.weight(401, 9), self.default)
        self.assertGreater(self.weight(401, 3), self.default)

    def test_hunter_prioritizes_crit_projectile_and_cooldown(self):
        self.assertGreater(self.weight(501, 8), self.default)
        self.assertGreater(self.weight(501, 10), self.default)
        self.assertGreater(self.weight(501, 24), self.default)
        self.assertGreater(self.weight(501, 9), self.default)

    def test_slayer_prioritizes_health_and_sustain(self):
        self.assertGreater(self.weight(601, 3), self.default)
        self.assertGreater(self.weight(601, 16), self.default)
        self.assertGreater(self.weight(601, 18), self.default)


if __name__ == "__main__":
    unittest.main()

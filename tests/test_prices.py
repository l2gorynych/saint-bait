from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import unittest

from saint_bait.prices import estimate_price
from saint_bait.telemetry.inventory import filetime_iso,silver_cents


class MarketPriceTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,18,12,tzinfo=timezone.utc)
        self.fish=SimpleNamespace(fish_id='target',species='perch',weight_g=500,grade=1,
                                  caught_at=self.now.isoformat())
        self.rows=[dict(id=f'quote-{i}',fish_id=f'fish-{i}',species='perch',weight_g=w,
                        grade=1,freshness=100,price_cents=w//5,waterbody_id='lake',
                        observed_at=self.now.isoformat()) for i,w in enumerate((450,500,550))]

    def estimate(self,rows=None):
        return estimate_price(self.fish,'lake',self.rows if rows is None else rows,self.now)

    def test_quote_parsing_and_native_clock(self):
        self.assertEqual(silver_cents('1 234,56'),123456)
        self.assertEqual(silver_cents('0,05'),5)
        for value in ('-1','1.234','free',None):self.assertIsNone(silver_cents(value))
        value=116444736000000000+int(self.now.timestamp())*10000000
        self.assertEqual(filetime_iso(value),self.now.isoformat())
        self.assertIsNone(filetime_iso(0))

    def test_three_independent_comparable_fish_allow_an_estimate(self):
        result=self.estimate()
        self.assertEqual(result['cents'],100)
        self.assertEqual(result['samples'],3)
        self.assertFalse(result['exact'])

    def test_repeated_observation_of_one_fish_does_not_make_three_samples(self):
        self.assertIsNone(self.estimate([dict(self.rows[0],id=str(i)) for i in range(5)]))

    def test_other_market_grade_weight_freshness_or_old_quotes_do_not_count(self):
        changes=({'waterbody_id':'river'},{'grade':2},{'weight_g':2000},{'freshness':80},
                 {'observed_at':(self.now-timedelta(days=2)).isoformat()})
        for change in changes:
            with self.subTest(change=change):
                self.assertIsNone(self.estimate([dict(row,**change) for row in self.rows]))

    def test_widely_varying_prices_are_not_guessed(self):
        self.assertIsNone(self.estimate([*self.rows[:2],dict(self.rows[2],price_cents=500)]))

    def test_recent_quote_for_this_exact_fish_has_priority(self):
        quote=dict(self.rows[0],fish_id='target',price_cents=117)
        result=self.estimate([quote])
        self.assertTrue(result['exact'])
        self.assertEqual(result['cents'],117)
        quote['observed_at']=(self.now-timedelta(minutes=2)).isoformat()
        self.assertIsNone(self.estimate([quote]))

    def test_unknown_fish_identity_does_not_match_anonymous_quote(self):
        self.fish.fish_id=None
        self.assertIsNone(self.estimate([dict(self.rows[0],fish_id=None)]))

    def test_spoiled_fish_cannot_use_fresh_quotes(self):
        self.fish.caught_at=(self.now-timedelta(days=2)).isoformat()
        self.assertIsNone(self.estimate())
        self.assertIsNotNone(self.estimate([dict(row,freshness=0) for row in self.rows]))

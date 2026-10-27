import unittest

from scout.filters import dedupe_key, relevant


class FilterTests(unittest.TestCase):
    def test_keeps_senior_commercial_roles_in_israel(self):
        for title, loc in [
            ("VP Sales", "Tel Aviv, Israel"),
            ("Head of Partnerships - IL", "Tel Aviv"),
            ("Chief Business Officer", "Herzliya, Israel"),
            ("VP of Strategic Partnerships", "Ra'anana"),
            ("General Manager, Israel", "Israel"),
            ("Director, Business Development EMEA", "Petah Tikva, IL"),
            ("VP GTM", "Remote - Israel"),
            ("Head of AI Practice", "Jerusalem"),
            ("COO", "Haifa, Israel"),
        ]:
            keep, why = relevant(title, loc)
            self.assertTrue(keep, f"{title} / {loc}: {why}")

    def test_drops_engineering_and_other_functions(self):
        for title in [
            "VP R&D",
            "Director of Engineering",
            "Head of Data Science",
            "VP Finance",
            "Director, Legal",
            "Head of People",
            "Senior Software Engineer",
            "Chief Technology Officer",
        ]:
            keep, _ = relevant(title, "Tel Aviv, Israel")
            self.assertFalse(keep, title)

    def test_sales_engineering_director_is_dropped_but_vp_sales_kept(self):
        self.assertFalse(relevant("Director, Sales Engineering", "Tel Aviv")[0])
        self.assertTrue(relevant("Director of Sales", "Tel Aviv")[0])

    def test_drops_non_senior(self):
        self.assertFalse(relevant("Account Executive", "Tel Aviv")[0])
        self.assertFalse(relevant("Partner Manager", "Tel Aviv")[0])

    def test_location_filter(self):
        self.assertFalse(relevant("VP Sales", "New York, NY")[0])
        self.assertFalse(relevant("VP Sales", "London, UK")[0])
        self.assertTrue(relevant("VP Sales", "")[0])  # unknown location is kept for review

    def test_dedupe_key(self):
        self.assertEqual(dedupe_key("ScaleOps", "Head of Partnerships - IL"), dedupe_key("scaleops", "Head of Partnerships – IL"))


if __name__ == "__main__":
    unittest.main()

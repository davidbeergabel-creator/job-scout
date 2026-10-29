import unittest

from scout.filters import clean_title, dedupe_key, relevant


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
            "Executive Assistant to the CRO",
            "Sales Operations Analyst",
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
        self.assertFalse(relevant("Account Director Central", "United States - IL Remote")[0])  # IL = Illinois here
        self.assertTrue(relevant("VP Sales", "Tel Aviv, IL")[0])

    def test_clean_title(self):
        self.assertEqual(clean_title("<p>\nVP Operations \n</p>"), "VP Operations")
        self.assertEqual(clean_title("Head of Sales &amp; Partnerships"), "Head of Sales & Partnerships")

    def test_dedupe_key(self):
        self.assertEqual(dedupe_key("ScaleOps", "Head of Partnerships - IL"), dedupe_key("scaleops", "Head of Partnerships – IL"))



class SniffTests(unittest.TestCase):
    def test_sniff_page_finds_embedded_ats(self):
        from scout.ats import sniff_page
        self.assertEqual(sniff_page('<iframe src="https://boards.greenhouse.io/embed/job_board?for=scaleops">'), ("greenhouse", "scaleops"))
        self.assertEqual(sniff_page('<a href="https://jobs.lever.co/logz/123">'), ("lever", "logz"))
        self.assertEqual(sniff_page('<a href="https://apply.workable.com/novidea/">'), ("workable", "novidea"))
        self.assertIsNone(sniff_page("<html>no ats here</html>"))

    def test_comeet_init_block_and_wp_links(self):
        from scout.ats import _comeet_creds, _comeet_wp
        page = 'COMEET.init({\n "token":       "1785E0758A482F01785E01782F05E0",\n "company-uid": "A1.B23", "lang": "en"})'
        self.assertEqual(_comeet_creds(page), ("A1.B23", "1785E0758A482F01785E01782F05E0"))
        wp = '<a href="https://allcloud.io/careers/co/israel/E0.47A/account-executive-enterprise-sector/all">x</a> <a href="/careers/co/united-states/CB.37A/global-vice-president-marketing/all">y</a>'
        jobs = _comeet_wp(wp, "https://allcloud.io/careers/", "AllCloud")
        self.assertEqual([j["title"] for j in jobs], ["Account Executive Enterprise Sector", "Global Vice President Marketing"])
        self.assertEqual(jobs[1]["location"], "United States")
        self.assertTrue(jobs[1]["url"].startswith("https://allcloud.io/"))

    def test_comeet_creds_in_js_bundle(self):
        from scout.ats import _comeet_creds, _script_urls
        js = 'e.exports={comeet:{uid:"88.123",token:"ABCDEF0123456789ABCDEF0123456789"}}'
        self.assertEqual(_comeet_creds(js), ("88.123", "ABCDEF0123456789ABCDEF0123456789"))
        page = '<script src="/_nuxt/entry.js"></script><script src="https://cdn.other.com/x.js"></script><script src="/_nuxt/careers.js"></script>'
        self.assertEqual(_script_urls(page, "https://www.vastdata.com/careers"), ["https://www.vastdata.com/_nuxt/careers.js", "https://www.vastdata.com/_nuxt/entry.js"])

    def test_comeet_creds_from_widget(self):
        from scout.ats import _comeet_creds
        page = '<script src="//www.comeet.co/careers-api/careers.js?company=AllCloud&token=0123456789abcdef0123456789abcdef&uid=A1.B23"></script>'
        self.assertEqual(_comeet_creds(page), ("A1.B23", "0123456789abcdef0123456789abcdef"))


if __name__ == "__main__":
    unittest.main()

"""Red-flag escalation lexicon for incoming patient Q&A (AES-1801).

Pure + deterministic: the ingest classifier that marks an urgent patient question. It errs toward
sensitivity, so these pin both the must-catch emergencies (the eval's QD-05 vascular occlusion) and
that ordinary reassurance questions stay calm.
"""
import unittest

from app.services.qa_knowledge import escalation


class ClassifyUrgencyTests(unittest.TestCase):
    def test_qd05_vascular_occlusion_is_urgent_vision_first(self):
        # The hardest must-catch: skin blanching + severe pain + vision change (filler occlusion).
        flags = escalation.classify_urgency("پوستم سفید شده و خیلی درد دارم و تار می‌بینم")
        self.assertTrue(escalation.is_urgent("پوستم سفید شده و خیلی درد دارم و تار می‌بینم"))
        self.assertIn("vision", flags)
        self.assertIn("necrosis", flags)
        self.assertIn("severe_pain", flags)
        self.assertEqual(flags[0], "vision")  # vision drives the toast label «تاری دید»

    def test_english_red_flags(self):
        self.assertEqual(escalation.classify_urgency("I have blurred vision and severe pain")[0], "vision")
        self.assertIn("breathing", escalation.classify_urgency("I have shortness of breath"))
        self.assertIn("fever", escalation.classify_urgency("I have a fever and chills"))

    def test_fa_single_token_flags(self):
        self.assertIn("vision", escalation.classify_urgency("چشمم تاری داره"))
        self.assertIn("breathing", escalation.classify_urgency("تنگی نفس دارم"))
        self.assertIn("fever", escalation.classify_urgency("تب دارم"))

    def test_ordinary_reassurance_questions_are_not_urgent(self):
        # The benign QD-01 case + the owner's own repro question must stay calm (no false escalation).
        self.assertFalse(escalation.is_urgent("بعد از فیلر لبم یکم ورم داره، طبیعیه؟"))
        self.assertFalse(escalation.is_urgent("کی میتونم ورزش کنم؟"))
        self.assertFalse(escalation.is_urgent("When can I wear makeup again?"))
        self.assertEqual(escalation.classify_urgency(""), [])
        self.assertEqual(escalation.classify_urgency(None), [])

    def test_categories_are_stable_and_ordered(self):
        # The frontend localizes these keys (qa.redflag.<key>) — order is the label priority.
        self.assertEqual(escalation.RED_FLAG_CATEGORIES[0], "vision")
        self.assertEqual(
            set(escalation.RED_FLAG_CATEGORIES), {"vision", "necrosis", "breathing", "severe_pain", "fever"}
        )


if __name__ == "__main__":
    unittest.main()

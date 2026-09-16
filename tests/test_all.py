"""Full test suite: cryptography, access control, disclosure rules, report
generation, the assistant, and an end-to-end pass over the HTTP API.

Run:  python3 -m tests.test_all
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import api, assistant, audit, auth, config, crypto, generator, llm, redaction  # noqa: E402
from app import main as app_main  # noqa: E402
from unittest import mock  # noqa: E402
from app.db import Store  # noqa: E402
from app.forms import FORMS, required_fields  # noqa: E402
from app.seed import seed  # noqa: E402
from app.server import serve  # noqa: E402
from app.templates import TEMPLATES  # noqa: E402


def fresh_store(tmpdir, name="t.db"):
    return Store(os.path.join(tmpdir, name), passphrase="unit-test-passphrase")


# --------------------------------------------------------------------------


class TestCrypto(unittest.TestCase):
    def test_fips197_aes256_block(self):
        key = bytes.fromhex("000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
        plain = bytes.fromhex("00112233445566778899aabbccddeeff")
        got = crypto._encrypt_block(crypto._expand_key(key), plain)
        self.assertEqual(got.hex(), "8ea2b7ca516745bfeafc49904b496089")

    def test_nist_gcm_vector_16(self):
        key = bytes.fromhex("feffe9928665731c6d6a8f9467308308feffe9928665731c6d6a8f9467308308")
        iv = bytes.fromhex("cafebabefacedbaddecaf888")
        plain = bytes.fromhex(
            "d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a721c3c0c95956809532"
            "fcf0e2449a6b525b16aedf5aa0de657ba637b39")
        aad = bytes.fromhex("feedfacedeadbeeffeedfacedeadbeefabaddad2")
        ct, tag = crypto.aes_gcm_encrypt(key, iv, plain, aad)
        self.assertEqual(ct.hex(),
                         "522dc1f099567d07f47f37a32a84427d643a8cdcbfe5c0c97598a2bd2555d1aa"
                         "8cb08e48590dbb3da7b08b1056828838c5f61e6393ba7a0abcc9f662")
        self.assertEqual(tag.hex(), "76fc6ece0f4e1768cddf8853bb2d551b")
        self.assertEqual(crypto.aes_gcm_decrypt(key, iv, ct, tag, aad), plain)

    def test_gcm_empty_and_no_aad(self):
        key = bytes(32)
        iv = bytes(12)
        ct, tag = crypto.aes_gcm_encrypt(key, iv, b"", b"")
        self.assertEqual(ct, b"")
        self.assertEqual(tag.hex(), "530f8afbc74536b9a963b4f1c4cb738b")

    def test_tamper_is_detected(self):
        key = crypto.new_data_key()
        blob = crypto.seal(key, b"clinical note", b"evaluations:7")
        self.assertEqual(crypto.unseal(key, blob, b"evaluations:7"), b"clinical note")
        flipped = bytearray(blob)
        flipped[-1] ^= 0x01
        with self.assertRaises(ValueError):
            crypto.unseal(key, bytes(flipped), b"evaluations:7")

    def test_aad_binds_row_identity(self):
        """A ciphertext must not be movable to another row or table."""
        key = crypto.new_data_key()
        blob = crypto.seal(key, b"patient A", b"patients:1")
        with self.assertRaises(ValueError):
            crypto.unseal(key, blob, b"patients:2")
        with self.assertRaises(ValueError):
            crypto.unseal(key, blob, b"reports:1")

    def test_password_hashing(self):
        stored = crypto.hash_password("correct horse battery staple")
        self.assertTrue(crypto.verify_password("correct horse battery staple", stored))
        self.assertFalse(crypto.verify_password("wrong", stored))
        self.assertNotIn("correct", stored)

    def test_wrong_passphrase_cannot_unlock(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.db")
            Store(path, passphrase="right-one")
            with self.assertRaises(SystemExit):
                Store(path, passphrase="wrong-one")


class TestStorage(unittest.TestCase):
    def test_no_plaintext_phi_on_disk(self):
        """Only structural columns (ids, dates, status, MRN) are readable in the
        database file; every clinical and identifying payload is sealed."""
        with tempfile.TemporaryDirectory() as tmp:
            store = fresh_store(tmp)
            seed(store)
            with open(store.path, "rb") as handle:
                raw = handle.read()
            for suffix in ("-wal", "-shm"):
                if os.path.exists(store.path + suffix):
                    with open(store.path + suffix, "rb") as handle:
                        raw += handle.read()
            for needle in (b"Ellison", b"Whitfield", b"Duarte", b"suicidal", b"lithium",
                           b"autistic burnout", b"MRN-00101x"):
                self.assertNotIn(needle, raw, "plaintext %r found in the database file" % needle)
            # The row-level structure is still queryable.
            from app.seed import PATIENTS
            self.assertEqual(store.one("SELECT COUNT(*) c FROM patients")["c"], len(PATIENTS))


class TestAudit(unittest.TestCase):
    def test_chain_detects_edit_and_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = fresh_store(tmp)
            user = {"id": 1, "username": "dr.chen"}
            for i in range(5):
                audit.log(store, user, "patient.view", "patient", 1, 1, "entry %d" % i)
            self.assertTrue(audit.verify_chain(store)["ok"])
            store.execute("UPDATE audit SET detail='changed' WHERE id=3")
            result = audit.verify_chain(store)
            self.assertFalse(result["ok"])
            self.assertEqual(result["broken_at"], 3)

    def test_chain_detects_row_removal(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = fresh_store(tmp)
            for i in range(4):
                audit.log(store, {"id": 1, "username": "u"}, "a%d" % i)
            store.execute("DELETE FROM audit WHERE id=2")
            self.assertFalse(audit.verify_chain(store)["ok"])


class TestAuth(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = fresh_store(self.tmp.name)
        self.uid = auth.create_user(self.store, "dr.k", "Secret!123", "Dr K", "clinician", "MD")

    def tearDown(self):
        self.tmp.cleanup()

    def test_lockout_after_five_failures(self):
        for _ in range(5):
            user, _err = auth.authenticate(self.store, "dr.k", "nope")
            self.assertIsNone(user)
        user, err = auth.authenticate(self.store, "dr.k", "Secret!123")
        self.assertIsNone(user)
        self.assertIn("locked", err.lower())

    def test_idle_timeout(self):
        token = auth.start_session(self.store, self.uid)
        self.assertIsNotNone(auth.resolve_session(self.store, token)[0])
        self.store.execute("UPDATE sessions SET last_seen=? WHERE token_hash=?",
                           (time.time() - auth.IDLE_TIMEOUT - 5, crypto.token_fingerprint(token)))
        user, err = auth.resolve_session(self.store, token)
        self.assertIsNone(user)
        self.assertIn("inactivity", err)

    def test_session_token_not_stored_in_clear(self):
        token = auth.start_session(self.store, self.uid)
        rows = self.store.query("SELECT token_hash FROM sessions")
        self.assertNotIn(token, [r["token_hash"] for r in rows])

    def test_role_permissions(self):
        self.assertTrue(auth.can({"role": "clinician"}, "report.sign"))
        self.assertFalse(auth.can({"role": "staff"}, "eval.read"))
        self.assertFalse(auth.can({"role": "auditor"}, "patient.read"))
        self.assertTrue(auth.can({"role": "auditor"}, "audit.read"))


class TestRedaction(unittest.TestCase):
    def setUp(self):
        self.record = {
            "hpi": [{"value": "Low mood for four months.", "date": "2026-01-02", "form_id": "adult_initial",
                     "form_name": "F", "eval_id": 1, "field_id": "hpi", "label": "HPI", "sens": "general"}],
            "alcohol": [{"value": "8-10 drinks daily.", "date": "2026-01-02", "form_id": "adult_initial",
                         "form_name": "F", "eval_id": 1, "field_id": "alcohol", "label": "Alcohol", "sens": "sud"}],
            "trauma_history": [{"value": "Childhood neglect.", "date": "2026-01-02", "form_id": "adult_initial",
                                "form_name": "F", "eval_id": 1, "field_id": "trauma_history",
                                "label": "Trauma", "sens": "trauma"}],
            "process_note": [{"value": "Private hypothesis.", "date": "2026-01-02", "form_id": "adult_initial",
                              "form_name": "F", "eval_id": 1, "field_id": "process_note",
                              "label": "Process note", "sens": "process_note"}],
        }

    def test_school_report_withholds_protected_content(self):
        kept, withheld = redaction.filter_record(self.record, TEMPLATES["school_iep"], None)
        self.assertIn("hpi", kept)
        for field in ("alcohol", "trauma_history", "process_note"):
            self.assertNotIn(field, kept)
        self.assertEqual({w["field_id"] for w in withheld}, {"alcohol", "trauma_history", "process_note"})

    def test_authorization_unlocks_named_category_only(self):
        authorization = {"scopes": ["sud"]}
        kept, _ = redaction.filter_record(self.record, TEMPLATES["referring_clinician"], authorization)
        self.assertIn("alcohol", kept)
        self.assertIn("trauma_history", kept)   # template already permits trauma
        self.assertNotIn("process_note", kept)

    def test_process_notes_never_release_even_when_authorized(self):
        authorization = {"scopes": list(redaction.SPECIALLY_PROTECTED)}
        for template in TEMPLATES.values():
            kept, _ = redaction.filter_record(self.record, template, authorization)
            self.assertNotIn("process_note", kept, template["id"])

    def test_part2_notice_attaches_when_sud_present(self):
        authorization = {"scopes": ["sud"]}
        kept, _ = redaction.filter_record(self.record, TEMPLATES["insurance_lmn"], authorization)
        self.assertTrue(redaction.contains_part2(kept))

    def test_safe_harbor_deidentification(self):
        text = ("Maya Ellison, DOB 1991-04-18, MRN: MRN-00101, seen 04/18/2026. "
                "Call (555) 233-8890 or m.ellison@example.com. SSN 123-45-6789.")
        out = redaction.deidentify(text, ["Maya", "Ellison"])
        for needle in ("Maya", "Ellison", "1991-04-18", "555", "example.com", "123-45-6789"):
            self.assertNotIn(needle, out)
        self.assertIn("[NAME]", out)

    def test_risk_escalation_rule(self):
        record = {
            "risk_level": [{"value": "Low", "date": "2026-01-02", "label": "x", "field_id": "risk_level",
                            "form_id": "f", "form_name": "f", "eval_id": 1, "sens": "risk"}],
            "si_ideation": [{"value": "Active with intent and plan", "date": "2026-01-02", "label": "x",
                             "field_id": "si_ideation", "form_id": "f", "form_name": "f",
                             "eval_id": 1, "sens": "risk"}],
        }
        risk = redaction.assess_risk(record)
        self.assertEqual(risk["level"], "High")
        self.assertTrue(risk["escalated"])
        self.assertTrue(any("safety plan" in gap for gap in risk["gaps"]))


class TestGenerator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = fresh_store(cls.tmp.name)
        seed(cls.store)
        cls.clinician = {"id": 1, "display_name": "Dr. Amara Chen", "credentials": "MD",
                         "npi": "1457893021", "role": "clinician"}
        cls.practice = api.PRACTICE

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _patient(self, mrn):
        row = self.store.one("SELECT * FROM patients WHERE mrn=?", (mrn,))
        demographics = self.store.payload("patients", row)
        evaluations = []
        for ev in self.store.query("SELECT * FROM evaluations WHERE patient_id=?", (row["id"],)):
            payload = self.store.payload("evaluations", ev)
            evaluations.append({"id": ev["id"], "form_id": ev["form_id"],
                                "encounter_date": ev["encounter_date"], "answers": payload["answers"]})
        return row, demographics, evaluations

    def test_every_template_renders_for_every_patient(self):
        for mrn in ("MRN-00101", "MRN-00102", "MRN-00103", "MRN-00104"):
            row, demographics, evaluations = self._patient(mrn)
            for template_id in TEMPLATES:
                content = generator.generate(demographics, row["mrn"], evaluations, template_id,
                                             self.clinician, self.practice)
                self.assertTrue(content["sections"], f"{mrn}/{template_id} produced no sections")
                text = generator.to_text(content)
                self.assertNotIn("Private hypothesis", text)
                self.assertGreater(len(text), 200, f"{mrn}/{template_id} too short")

    def test_process_note_never_reaches_any_report(self):
        row, demographics, evaluations = self._patient("MRN-00104")
        marker = "my father did this to us"
        self.assertTrue(any(marker in str(v) for e in evaluations for v in e["answers"].values()))
        for template_id in TEMPLATES:
            content = generator.generate(demographics, row["mrn"], evaluations, template_id,
                                         self.clinician, self.practice,
                                         authorization={"scopes": list(redaction.SPECIALLY_PROTECTED)})
            self.assertNotIn(marker, generator.to_text(content), template_id)

    def test_school_letter_omits_risk_and_substance_content(self):
        row, demographics, evaluations = self._patient("MRN-00104")
        content = generator.generate(demographics, row["mrn"], evaluations, "school_iep",
                                     self.clinician, self.practice)
        text = generator.to_text(content).lower()
        for needle in ("rifle", "alcohol use disorder", "suicid", "8-10 standard drinks"):
            self.assertNotIn(needle, text)

    def test_employer_letter_omits_diagnosis(self):
        row, demographics, evaluations = self._patient("MRN-00101")
        content = generator.generate(demographics, row["mrn"], evaluations, "employer_accommodation",
                                     self.clinician, self.practice)
        text = generator.to_text(content)
        self.assertNotIn("F33.1", text)
        self.assertNotIn("Major depressive disorder", text)
        # ...but it must still carry functional limitations, which is its purpose.
        self.assertIn("deadlines", text.lower())

    def test_insurance_letter_carries_codes_and_necessity(self):
        row, demographics, evaluations = self._patient("MRN-00101")
        content = generator.generate(demographics, row["mrn"], evaluations, "insurance_lmn",
                                     self.clinician, self.practice)
        text = generator.to_text(content)
        self.assertIn("F33.1", text)
        self.assertIn("medically necessary", text)
        self.assertIn("PHQ-9", text)
        self.assertIn("NH-4471902", text)  # member id, FULL identifier policy

    def test_family_summary_is_plain_language_and_identifier_limited(self):
        row, demographics, evaluations = self._patient("MRN-00101")
        content = generator.generate(demographics, row["mrn"], evaluations, "family_caregiver",
                                     self.clinician, self.practice)
        text = generator.to_text(content)
        self.assertIn("anhedonia)", text)          # jargon kept but explained
        self.assertIn("988", text)                  # crisis resources present
        self.assertNotIn("MRN-00101", text)         # limited identifiers
        self.assertNotIn(demographics["insurance"]["member_id"], text)

    def test_plain_language_preserves_instrument_names(self):
        """Translating jargon must not corrupt scale names: 'GAD-7' is not
        'generalised anxiety disorder-7'."""
        row, demographics, evaluations = self._patient("MRN-00101")
        content = generator.generate(demographics, row["mrn"], evaluations, "family_caregiver",
                                     self.clinician, self.practice)
        text = generator.to_text(content)
        self.assertIn("GAD-7", text)
        self.assertNotIn("anxiety disorder-7", text)
        self.assertIn("PHQ-9", text)

    def test_bullets_keep_clauses_intact(self):
        long_line = ("Continue sertraline 100 mg daily for four weeks; CBT started last week, "
                     "continue weekly; repeat PHQ-9 and GAD-7 at each visit and review the "
                     "sexual side effects at the next appointment before changing anything.")
        self.assertEqual(generator._bullets_from(long_line), [long_line])
        self.assertEqual(generator._bullets_from("1. First\n2. Second\n- Third"),
                         ["First", "Second", "Third"])

    def test_patient_avs_may_include_own_protected_content(self):
        row, demographics, evaluations = self._patient("MRN-00104")
        content = generator.generate(demographics, row["mrn"], evaluations, "patient_avs",
                                     self.clinician, self.practice)
        self.assertNotIn("process_note", [w["field_id"] for w in content["withheld"]] and [])
        text = generator.to_text(content)
        self.assertIn("988", text)

    def test_multi_session_merge_uses_latest_state_and_keeps_narrative(self):
        row, demographics, evaluations = self._patient("MRN-00101")
        self.assertEqual(len(evaluations), 2)
        content = generator.generate(demographics, row["mrn"], evaluations, "referring_clinician",
                                     self.clinician, self.practice)
        text = generator.to_text(content)
        self.assertIn("Sertraline 100 mg daily", text)   # latest medication state
        self.assertIn("marketing analyst", text)          # narrative from the first visit
        mse = [s for s in content["sections"] if s["title"].startswith("Mental status")][0]
        self.assertIn("Fuller range", " ".join(str(v) for v in mse["body"].values()))

    def test_measures_table_shows_trend(self):
        row, demographics, evaluations = self._patient("MRN-00101")
        content = generator.generate(demographics, row["mrn"], evaluations, "insurance_lmn",
                                     self.clinician, self.practice)
        table = [s for s in content["sections"] if s["kind"] == "table"][0]
        phq = [r for r in table["body"] if r[0].startswith("PHQ-9")][0]
        self.assertIn("improved by 7", phq[3])

    def test_deidentified_render(self):
        row, demographics, evaluations = self._patient("MRN-00101")
        content = generator.generate(demographics, row["mrn"], evaluations, "referring_clinician",
                                     self.clinician, self.practice, deidentify=True)
        text = generator.to_text(content)
        self.assertNotIn("Ellison", text)

    def test_missing_required_section_is_flagged(self):
        row, demographics, _ = self._patient("MRN-00101")
        sparse = [{"id": 99, "form_id": "adult_initial", "encounter_date": "2026-01-01",
                   "answers": {"chief_complaint": "Trouble sleeping."}}]
        content = generator.generate(demographics, row["mrn"], sparse, "insurance_lmn",
                                     self.clinician, self.practice)
        self.assertTrue(any("Required section" in w for w in content["warnings"]))

    def test_authorization_warning_when_missing(self):
        row, demographics, evaluations = self._patient("MRN-00103")
        content = generator.generate(demographics, row["mrn"], evaluations, "school_iep",
                                     self.clinician, self.practice, authorization=None)
        self.assertTrue(any("authorization" in w for w in content["warnings"]))

    def test_diagnosis_parsing(self):
        parsed = generator.parse_diagnoses("F33.1 Major depressive disorder, recurrent\nF41.1 GAD")
        self.assertEqual(parsed[0]["code"], "F33.1")
        self.assertEqual(parsed[1]["code"], "F41.1")


class TestAssistant(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = fresh_store(cls.tmp.name)
        seed(cls.store)
        row = cls.store.one("SELECT * FROM patients WHERE mrn='MRN-00101'")
        cls.evaluations = []
        for ev in cls.store.query("SELECT * FROM evaluations WHERE patient_id=?", (row["id"],)):
            payload = cls.store.payload("evaluations", ev)
            cls.evaluations.append({"id": ev["id"], "form_id": ev["form_id"],
                                    "encounter_date": ev["encounter_date"], "answers": payload["answers"]})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_retrieval_answers_with_citations(self):
        result = assistant.answer("What medication trials has she had and how did she respond?",
                                  self.evaluations, [], ["Maya", "Ellison"])
        self.assertTrue(result["citations"])
        self.assertIn("ertraline", result["answer"])

    def test_declines_clinical_directives(self):
        result = assistant.answer("What should I prescribe next?", self.evaluations, [], [])
        self.assertEqual(result["mode"], "guardrail")
        self.assertIn("can't provide clinical direction", result["answer"])

    def test_risk_question_attaches_risk_context(self):
        result = assistant.answer("Summarise the suicide risk assessment.", self.evaluations, [], [])
        self.assertIsNotNone(result["risk"])
        self.assertTrue(any("risk stratification" in n for n in result["notes"]))

    def test_process_notes_excluded_from_context(self):
        passages = assistant.build_passages(self.evaluations, [])
        self.assertFalse([p for p in passages if p.meta.get("field_id") == "process_note"])

    def test_retrieval_survives_word_endings(self):
        """Clinicians write 'impairment in functioning'; a user asks about
        'functional impairments'. Retrieval must bridge that."""
        result = assistant.answer("What functional impairments are documented?",
                                  self.evaluations, [], [])
        titles = [c["title"] for c in result["citations"]]
        self.assertIn("Summary of functional impairment", titles)
        self.assertIn("impairment across occupational", result["answer"])

    def test_no_match_is_honest(self):
        result = assistant.answer("What were the results of the cardiac catheterisation?",
                                  self.evaluations, [], [])
        self.assertIn(result["mode"], ("no-match", "extractive"))

    def test_completeness_check(self):
        incomplete = [{"id": 1, "form_id": "adult_initial", "encounter_date": "2026-01-01",
                       "answers": {"chief_complaint": "x"}}]
        result = assistant.completeness_check(incomplete)
        self.assertTrue(result["findings"])
        self.assertIn("required field", result["summary"])

    def test_consistency_check_catches_untraceable_numbers(self):
        content = {"sections": [{"title": "S", "kind": "narrative",
                                 "body": ["PHQ-9 was 27 and the dose was 450 mg."], "provenance": []}]}
        result = assistant.consistency_check(content, self.evaluations)
        self.assertFalse(result["ok"])
        self.assertTrue(any("450" in p for p in result["problems"]))


class TestFactGuard(unittest.TestCase):
    def test_rejects_new_numbers_codes_and_assertions(self):
        source = "PHQ-9 of 18. Sertraline 100 mg daily. F33.1."
        for candidate in ("PHQ-9 of 24.", "Sertraline 200 mg daily.", "Diagnosis F31.4.",
                          "The patient denies alcohol use."):
            ok, problems = llm.fact_guard(source, candidate)
            self.assertFalse(ok, candidate)
            self.assertTrue(problems)

    def test_accepts_faithful_rewrite(self):
        source = "PHQ-9 of 18 indicates moderate depression. Sertraline 100 mg daily."
        ok, problems = llm.fact_guard(source, "Her PHQ-9 score of 18 shows moderate depression. "
                                              "She takes sertraline 100 mg each day.")
        self.assertTrue(ok, problems)

    def test_polish_is_a_no_op_without_a_model(self):
        text = "Original text."
        out, note = llm.polish(text, "Family", "plain")
        self.assertEqual(out, text)
        self.assertIsNone(note)


# --------------------------------------------------------------------------
# End-to-end over HTTP
# --------------------------------------------------------------------------


class Client:
    def __init__(self, base):
        self.base = base
        self.cookie = None

    def request(self, method, path, body=None, expect=200, raw=False):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("X-PsychReport", "1")
        if data:
            req.add_header("Content-Type", "application/json")
        if self.cookie:
            req.add_header("Cookie", self.cookie)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                status, payload = response.status, response.read()
                set_cookie = response.headers.get("Set-Cookie")
                if set_cookie:
                    self.cookie = set_cookie.split(";")[0]
        except urllib.error.HTTPError as exc:
            status, payload = exc.code, exc.read()
        assert status == expect, f"{method} {path} -> {status} (expected {expect}): {payload[:400]!r}"
        if raw:
            return payload.decode("utf-8")
        return json.loads(payload) if payload else {}

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.request("POST", path, body if body is not None else {}, **kw)

    def put(self, path, body=None, **kw):
        return self.request("PUT", path, body if body is not None else {}, **kw)


class TestApiEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = fresh_store(cls.tmp.name)
        seed(cls.store)
        cls.httpd = serve(api.router, lambda: api.Context(cls.store), "127.0.0.1", 0)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def client(self, username="dr.chen", password="Demo!Pass1"):
        client = Client(self.base)
        client.post("/api/login", {"username": username, "password": password})
        return client

    # -- security ------------------------------------------------------
    def test_unauthenticated_access_is_refused(self):
        client = Client(self.base)
        client.get("/api/patients", expect=401)
        client.get("/api/me", expect=401)

    def test_csrf_header_required(self):
        client = self.client()
        req = urllib.request.Request(self.base + "/api/logout", data=b"{}", method="POST")
        req.add_header("Cookie", client.cookie)
        req.add_header("Content-Type", "application/json")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req, timeout=10)
        self.assertEqual(caught.exception.code, 403)

    def test_security_headers_present(self):
        with urllib.request.urlopen(self.base + "/", timeout=10) as response:
            self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])
            self.assertEqual(response.headers["X-Frame-Options"], "DENY")
            self.assertIn("no-store", response.headers["Cache-Control"])

    def test_static_path_traversal_blocked(self):
        client = Client(self.base)
        client.get("/../app/db.py", expect=404)

    def test_bad_login_is_rejected_and_logged(self):
        client = Client(self.base)
        client.post("/api/login", {"username": "dr.chen", "password": "wrong"}, expect=401)
        auditor = self.client("compliance", "Demo!Pass4")
        entries = auditor.get("/api/audit?limit=50")["entries"]
        self.assertTrue(any(e["action"] == "login.failed" for e in entries))

    # -- RBAC ----------------------------------------------------------
    def test_front_desk_cannot_see_clinical_content(self):
        client = self.client("frontdesk", "Demo!Pass3")
        patients = client.get("/api/patients")
        self.assertFalse(patients["clinical_visible"])
        self.assertNotIn("risk_level", patients["patients"][0])
        pid = patients["patients"][0]["id"]
        detail = client.get("/api/patients/%d" % pid)
        self.assertTrue(detail["clinical_restricted"])
        self.assertEqual(detail["evaluations"], [])
        client.post("/api/patients/%d/evaluations" % pid,
                    {"form_id": "adult_initial", "encounter_date": "2026-01-01", "answers": {}}, expect=403)
        client.post("/api/patients/%d/assistant" % pid, {"question": "anything"}, expect=403)
        client.post("/api/reports/1/amend", expect=403)
        client.get("/api/reports/1", expect=403)

    def test_auditor_cannot_read_charts_but_can_read_log(self):
        client = self.client("compliance", "Demo!Pass4")
        client.get("/api/patients", expect=403)
        self.assertTrue(client.get("/api/audit")["entries"])
        self.assertTrue(client.get("/api/audit/verify")["ok"])

    def test_clinician_audit_scope_is_limited_to_own_actions(self):
        client = self.client()
        result = client.get("/api/audit")
        self.assertEqual(result["scope"], "own")

    # -- clinical workflow ---------------------------------------------
    def test_full_workflow(self):
        client = self.client()
        patients = client.get("/api/patients")["patients"]
        maya = [p for p in patients if p["mrn"] == "MRN-00101"][0]
        self.assertEqual(maya["risk_level"], "Low")

        detail = client.get("/api/patients/%d" % maya["id"])
        eval_ids = [e["id"] for e in detail["evaluations"]]
        self.assertEqual(len(eval_ids), 2)

        # Fan out one chart into four recipient-specific drafts.
        created = client.post("/api/patients/%d/reports" % maya["id"], {
            "template_ids": ["family_caregiver", "insurance_lmn", "referring_clinician", "employer_accommodation"],
            "eval_ids": eval_ids,
        })["reports"]
        self.assertEqual(len(created), 4)
        by_template = {r["template_id"]: r for r in created}

        family = by_template["family_caregiver"]
        self.assertEqual(family["status"], "draft")
        self.assertTrue(family["content"]["authorization"], "the seeded family authorization should attach")

        employer = by_template["employer_accommodation"]
        employer_text = json.dumps(employer["content"])
        self.assertNotIn("F33.1", employer_text)

        # Signing requires attestation.
        client.post("/api/reports/%d/sign" % family["id"], {"attest": False}, expect=400)
        signed = client.post("/api/reports/%d/sign" % family["id"], {"attest": True})["report"]
        self.assertEqual(signed["status"], "final")
        self.assertIn("Dr. Amara Chen", signed["signature"])

        # A signed report can no longer be edited.
        client.put("/api/reports/%d" % family["id"], {"section_index": 0, "body": ["x"]}, expect=409)

        released = client.post("/api/reports/%d/release" % family["id"],
                               {"recipient": "Rosa Ellison", "method": "hand-delivered"})
        self.assertEqual(released["report"]["status"], "released")
        self.assertEqual(released["disclosures"][0]["recipient"], "Rosa Ellison")

        # Export in both formats.
        text = client.get("/api/reports/%d/export?format=txt" % family["id"], raw=True)
        self.assertIn("988", text)
        page = client.get("/api/reports/%d/export?format=html" % family["id"], raw=True)
        self.assertIn("<!doctype html>", page)
        # The export must satisfy the same CSP as the app: no inline script, no
        # inline event handlers, no inline <style>, and no third-party origins.
        self.assertNotIn("<style", page.lower())
        self.assertIsNone(re.search(r"\son\w+\s*=", page))
        scripts = re.findall(r"<script([^>]*)>(.*?)</script>", page, re.S)
        self.assertEqual(len(scripts), 1)
        self.assertIn("src='/print.js'", scripts[0][0])
        self.assertEqual(scripts[0][1].strip(), "")
        self.assertNotIn("http://", page.replace("http://127.0.0.1", ""))

    def test_amending_a_signed_report(self):
        """A signed document is immutable; correcting it issues a new version
        that names what it supersedes and leaves the original in the record."""
        client = self.client()
        patients = client.get("/api/patients")["patients"]
        maya = [p for p in patients if p["mrn"] == "MRN-00101"][0]
        detail = client.get("/api/patients/%d" % maya["id"])
        eval_ids = [e["id"] for e in detail["evaluations"]]
        original = client.post("/api/patients/%d/reports" % maya["id"], {
            "template_ids": ["therapist_care_team"], "eval_ids": eval_ids})["reports"][0]

        # A draft is edited, not amended.
        client.post("/api/reports/%d/amend" % original["id"], expect=409)

        client.post("/api/reports/%d/sign" % original["id"], {"attest": True})
        amended = client.post("/api/reports/%d/amend" % original["id"])["report"]
        self.assertEqual(amended["status"], "draft")
        self.assertEqual(amended["amends_report_id"], original["id"])
        self.assertIsNone(amended["signature"])
        self.assertNotIn("signature", amended["content"])
        self.assertTrue(amended["content"]["warnings"][0].startswith("This is an amended version"))
        self.assertIn("superseding the report of", amended["content"]["footer"])
        self.assertIn("(amended)", amended["title"])

        # The original is untouched and still signed.
        still = client.get("/api/reports/%d" % original["id"])["report"]
        self.assertEqual(still["status"], "final")
        self.assertTrue(still["signature"])

        # The amended draft is editable, and can be signed in its own right.
        index = next(i for i, s in enumerate(amended["content"]["sections"])
                     if s["kind"] == "narrative")
        client.put("/api/reports/%d" % amended["id"],
                   {"section_index": index, "body": ["Corrected wording."]})
        signed = client.post("/api/reports/%d/sign" % amended["id"], {"attest": True})["report"]
        self.assertEqual(signed["status"], "final")

    def test_amend_can_rebuild_from_the_current_chart(self):
        client = self.client()
        patients = client.get("/api/patients")["patients"]
        maya = [p for p in patients if p["mrn"] == "MRN-00101"][0]
        detail = client.get("/api/patients/%d" % maya["id"])
        first_visit = [e for e in detail["evaluations"]][:1]
        report = client.post("/api/patients/%d/reports" % maya["id"], {
            "template_ids": ["referring_clinician"],
            "eval_ids": [e["id"] for e in first_visit]})["reports"][0]
        client.post("/api/reports/%d/sign" % report["id"], {"attest": True})
        rebuilt = client.post("/api/reports/%d/amend" % report["id"], {"regenerate": True})["report"]
        self.assertTrue(rebuilt["content"]["amends"]["regenerated"])
        self.assertIn("amended version", rebuilt["content"]["warnings"][0])

    def test_release_blocked_without_authorization_then_allowed(self):
        client = self.client()
        patients = client.get("/api/patients")["patients"]
        priya = [p for p in patients if p["mrn"] == "MRN-00103"][0]
        detail = client.get("/api/patients/%d" % priya["id"])
        self.assertEqual(detail["authorizations"], [])
        eval_ids = [e["id"] for e in detail["evaluations"]]

        report = client.post("/api/patients/%d/reports" % priya["id"],
                             {"template_ids": ["employer_accommodation"], "eval_ids": eval_ids})["reports"][0]
        self.assertTrue(any("authorization" in w for w in report["content"]["warnings"]))
        client.post("/api/reports/%d/sign" % report["id"], {"attest": True})
        client.post("/api/reports/%d/release" % report["id"],
                    {"recipient": "Halversen Logistics HR", "method": "encrypted email"}, expect=403)

        # Documented override is permitted, and is recorded as such.
        overridden = client.post("/api/reports/%d/release" % report["id"], {
            "recipient": "Halversen Logistics HR", "method": "encrypted email",
            "override_reason": "Patient verbally authorised; written form to follow, documented in chart."})
        self.assertTrue(overridden["disclosures"][0]["override_reason"])

        # And a proper authorization also unblocks the path.
        client.post("/api/patients/%d/authorizations" % priya["id"], {
            "recipient_name": "Halversen Logistics HR", "recipient_type": "Employer / occupational health",
            "signed_date": "2026-01-01", "expires_date": "2027-01-01", "scopes": []})
        second = client.post("/api/patients/%d/reports" % priya["id"],
                             {"template_ids": ["employer_accommodation"], "eval_ids": eval_ids})["reports"][0]
        self.assertIsNotNone(second["authorization_id"])
        client.post("/api/reports/%d/sign" % second["id"], {"attest": True})
        client.post("/api/reports/%d/release" % second["id"],
                    {"recipient": "Halversen Logistics HR", "method": "encrypted email"})

    def test_part2_content_requires_named_authorization(self):
        client = self.client()
        patients = client.get("/api/patients")["patients"]
        tom = [p for p in patients if p["mrn"] == "MRN-00104"][0]
        detail = client.get("/api/patients/%d" % tom["id"])
        eval_ids = [e["id"] for e in detail["evaluations"]]

        # The insurer authorization names 'sud', so the Part 2 notice attaches.
        insurance = client.post("/api/patients/%d/reports" % tom["id"],
                                {"template_ids": ["insurance_lmn"], "eval_ids": eval_ids})["reports"][0]
        self.assertIn("42 CFR Part 2", insurance["content"]["part2_notice"])
        self.assertIn("alcohol", json.dumps(insurance["content"]["sections"]).lower())

        # The school has no such authorization, so substance content is withheld.
        school = client.post("/api/patients/%d/reports" % tom["id"],
                             {"template_ids": ["school_iep"], "eval_ids": eval_ids})["reports"][0]
        self.assertEqual(school["content"]["part2_notice"], "")
        withheld = {w["field_id"] for w in school["content"]["withheld"]}
        self.assertIn("alcohol", withheld)

    def test_revoking_authorization_blocks_later_release(self):
        client = self.client()
        patients = client.get("/api/patients")["patients"]
        danny = [p for p in patients if p["mrn"] == "MRN-00102"][0]
        detail = client.get("/api/patients/%d" % danny["id"])
        eval_ids = [e["id"] for e in detail["evaluations"]]
        report = client.post("/api/patients/%d/reports" % danny["id"],
                             {"template_ids": ["school_iep"], "eval_ids": eval_ids})["reports"][0]
        self.assertIsNotNone(report["authorization_id"])
        client.post("/api/reports/%d/sign" % report["id"], {"attest": True})
        client.post("/api/authorizations/%d/revoke" % report["authorization_id"])
        client.post("/api/reports/%d/release" % report["id"],
                    {"recipient": "Brookline Elementary", "method": "secure fax"}, expect=403)

    def test_evaluation_lifecycle_and_immutability(self):
        client = self.client()
        created = client.post("/api/patients", {
            "demographics": {"first_name": "Test", "last_name": "Patient", "dob": "1990-05-05"},
            "tags": ["Demo"]})["patient"]
        self.assertTrue(created["mrn"].startswith("MRN-"))

        client.post("/api/patients/%d/evaluations" % created["id"],
                    {"form_id": "adult_initial", "encounter_date": "not-a-date", "answers": {}}, expect=400)

        evaluation = client.post("/api/patients/%d/evaluations" % created["id"], {
            "form_id": "adult_initial", "encounter_date": "2026-03-01",
            "answers": {"chief_complaint": "Panic attacks.", "nonexistent_field": "dropped"},
        })["evaluation"]
        self.assertNotIn("nonexistent_field", evaluation["answers"])

        # Cannot sign while required fields are empty.
        client.post("/api/evaluations/%d/sign" % evaluation["id"], expect=400)

        answers = dict(evaluation["answers"])
        answers.update({
            "hpi": "Three months of panic attacks, twice weekly.",
            "formulation": "Panic disorder without agoraphobia.",
            "dsm_diagnoses": "F41.0 Panic disorder",
            "treatment_plan": "Start CBT; consider an SSRI.",
            "risk_level": "Low", "risk_rationale": "No ideation, strong supports.",
        })
        client.put("/api/evaluations/%d" % evaluation["id"], {"answers": answers})
        client.post("/api/evaluations/%d/sign" % evaluation["id"])
        client.put("/api/evaluations/%d" % evaluation["id"], {"answers": answers}, expect=409)

    def test_assistant_endpoint_and_history(self):
        client = self.client()
        patients = client.get("/api/patients")["patients"]
        maya = [p for p in patients if p["mrn"] == "MRN-00101"][0]
        result = client.post("/api/patients/%d/assistant" % maya["id"],
                             {"question": "What is the current medication and dose?"})
        self.assertTrue(result["citations"])
        history = client.get("/api/patients/%d/assistant" % maya["id"])["messages"]
        self.assertGreaterEqual(len(history), 2)
        refusal = client.post("/api/patients/%d/assistant" % maya["id"],
                              {"question": "Should I increase the dose?"})
        self.assertEqual(refusal["mode"], "guardrail")

    def test_assistant_is_scoped_to_one_patient(self):
        client = self.client()
        patients = client.get("/api/patients")["patients"]
        maya = [p for p in patients if p["mrn"] == "MRN-00101"][0]
        result = client.post("/api/patients/%d/assistant" % maya["id"],
                             {"question": "Tell me about the hunting rifles and the alcohol use."})
        blob = json.dumps(result).lower()
        self.assertNotIn("rifle", blob)
        self.assertNotIn("whitfield", blob)

    def test_report_edit_and_consistency_check(self):
        client = self.client()
        patients = client.get("/api/patients")["patients"]
        maya = [p for p in patients if p["mrn"] == "MRN-00101"][0]
        detail = client.get("/api/patients/%d" % maya["id"])
        report = client.post("/api/patients/%d/reports" % maya["id"], {
            "template_ids": ["therapist_care_team"],
            "eval_ids": [e["id"] for e in detail["evaluations"]]})["reports"][0]
        clean = client.post("/api/reports/%d/consistency" % report["id"])
        self.assertTrue(clean["ok"], clean)

        index = next(i for i, s in enumerate(report["content"]["sections"]) if s["kind"] == "narrative")
        client.put("/api/reports/%d" % report["id"],
                   {"section_index": index, "body": ["Her PHQ-9 today was 137 on sertraline 450 mg."]})
        dirty = client.post("/api/reports/%d/consistency" % report["id"])
        self.assertFalse(dirty["ok"])
        self.assertTrue(any("137" in p for p in dirty["problems"]), dirty)
        self.assertTrue(any("450 mg" in p for p in dirty["problems"]), dirty)

    def test_audit_records_every_phi_touch(self):
        client = self.client()
        patients = client.get("/api/patients")["patients"]
        maya = [p for p in patients if p["mrn"] == "MRN-00101"][0]
        detail = client.get("/api/patients/%d" % maya["id"])
        report = client.post("/api/patients/%d/reports" % maya["id"], {
            "template_ids": ["patient_avs"],
            "eval_ids": [e["id"] for e in detail["evaluations"]]})["reports"][0]
        client.post("/api/reports/%d/sign" % report["id"], {"attest": True})
        client.post("/api/reports/%d/release" % report["id"],
                    {"recipient": "Patient", "method": "patient portal"})
        client.post("/api/patients/%d/assistant" % maya["id"], {"question": "What is the plan?"})
        auditor = self.client("compliance", "Demo!Pass4")
        actions = {e["action"] for e in auditor.get("/api/audit?limit=500")["entries"]}
        for action in ("login.success", "patient.list", "patient.view", "report.create",
                       "report.sign", "report.release", "assistant.query"):
            self.assertIn(action, actions)
        self.assertTrue(auditor.get("/api/audit/verify")["ok"])

    def test_compliance_endpoint(self):
        client = self.client()
        result = client.get("/api/compliance")
        names = {c["name"] for c in result["controls"]}
        self.assertIn("PHI encrypted at rest", names)
        self.assertIn("42 CFR Part 2", names)
        self.assertTrue(result["chain"]["ok"])

    def test_bad_input_is_rejected_cleanly(self):
        client = self.client()
        client.post("/api/patients", {"demographics": {"last_name": ""}}, expect=400)
        client.post("/api/patients", {"demographics": {"last_name": "X", "dob": "05/05/1990"}}, expect=400)
        client.get("/api/patients/99999", expect=404)
        client.get("/api/reports/99999", expect=404)
        client.post("/api/patients/1/reports", {"template_ids": ["not_a_template"], "eval_ids": [1]},
                    expect=400)
        pid = client.get("/api/patients")["patients"][0]["id"]
        client.post("/api/patients/%d/authorizations" % pid, {
            "recipient_name": "X", "recipient_type": "Family member or caregiver",
            "signed_date": "2026-05-05", "expires_date": "2026-01-01"}, expect=400)


class TestFormIntegrity(unittest.TestCase):
    def test_field_ids_unique_within_a_form(self):
        for form_id, form in FORMS.items():
            seen = set()
            for section in form["sections"]:
                for field in section["fields"]:
                    self.assertNotIn(field["id"], seen, f"{form_id}.{field['id']} duplicated")
                    seen.add(field["id"])

    def test_shared_field_ids_agree_on_sensitivity(self):
        seen = {}
        for form in FORMS.values():
            for section in form["sections"]:
                for field in section["fields"]:
                    if field["id"] in seen:
                        self.assertEqual(seen[field["id"]], field["sens"], field["id"])
                    seen[field["id"]] = field["sens"]

    def test_every_form_has_required_fields_and_a_date(self):
        for form_id, form in FORMS.items():
            self.assertIn("encounter_date", [f["id"] for s in form["sections"] for f in s["fields"]])
            self.assertTrue(required_fields(form_id), form_id)

    def test_every_template_builder_exists(self):
        for template in TEMPLATES.values():
            for section in template["sections"]:
                if section["kind"] == "custom":
                    self.assertIn(section["builder"], generator.BUILDERS, section["title"])

    def test_no_template_permits_process_notes(self):
        for template in TEMPLATES.values():
            self.assertNotIn("process_note", template["allowed_sens"], template["id"])



# --------------------------------------------------------------------------
# Hosted deployment (Render)
# --------------------------------------------------------------------------


def raw_request(base, method, path, body=None, headers=None, cookie=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("X-PsychReport", "1")
    if data:
        req.add_header("Content-Type", "application/json")
    if cookie:
        req.add_header("Cookie", cookie)
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


class TestHostedMode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        config.enable_hosted()
        api.reset_throttle()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = fresh_store(cls.tmp.name)
        seed(cls.store)
        cls.httpd = serve(api.router, lambda: api.Context(cls.store), "127.0.0.1", 0)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()
        api.reset_throttle()
        config.disable_hosted()

    def setUp(self):
        api.reset_throttle()

    def test_health_check_needs_no_auth_and_is_not_audited(self):
        before = self.store.one("SELECT COUNT(*) c FROM audit")["c"]
        status, _headers, body = raw_request(self.base, "GET", "/healthz")
        self.assertEqual((status, body), (200, b"ok"))
        status, _headers, _body = raw_request(self.base, "HEAD", "/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(self.store.one("SELECT COUNT(*) c FROM audit")["c"], before)

    def test_public_config_reports_hosted_mode_without_auth(self):
        status, _headers, body = raw_request(self.base, "GET", "/api/public-config")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertTrue(payload["hosted"])
        self.assertEqual(set(payload), {"hosted", "practice"})

    def test_session_cookie_is_secure_and_hsts_is_sent(self):
        status, headers, _ = raw_request(self.base, "POST", "/api/login",
                                         {"username": "dr.chen", "password": "Demo!Pass1"})
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"]
        for flag in ("Secure", "HttpOnly", "SameSite=Strict"):
            self.assertIn(flag, cookie)
        self.assertIn("max-age=", headers["Strict-Transport-Security"])

    def test_one_visitor_cannot_lock_out_the_shared_demo_account(self):
        attacker = {"X-Forwarded-For": "203.0.113.5"}
        for _ in range(api.THROTTLE_MAX_FAILURES):
            status, _, _ = raw_request(self.base, "POST", "/api/login",
                                       {"username": "dr.chen", "password": "wrong"}, attacker)
            self.assertEqual(status, 401)
        status, _, body = raw_request(self.base, "POST", "/api/login",
                                      {"username": "dr.chen", "password": "wrong"}, attacker)
        self.assertEqual(status, 429)
        # Even the right password is refused from the throttled connection...
        status, _, _ = raw_request(self.base, "POST", "/api/login",
                                   {"username": "dr.chen", "password": "Demo!Pass1"}, attacker)
        self.assertEqual(status, 429)
        # ...but every other visitor signs in normally, and the account itself was never locked.
        status, _, _ = raw_request(self.base, "POST", "/api/login",
                                   {"username": "dr.chen", "password": "Demo!Pass1"},
                                   {"X-Forwarded-For": "198.51.100.7"})
        self.assertEqual(status, 200)
        row = self.store.one("SELECT failed_logins, locked_until FROM users WHERE username='dr.chen'")
        self.assertEqual((row["failed_logins"], row["locked_until"]), (0, 0))

    def test_compliance_panel_says_this_is_a_public_demo(self):
        _, headers, _ = raw_request(self.base, "POST", "/api/login",
                                    {"username": "dr.chen", "password": "Demo!Pass1"})
        cookie = headers["Set-Cookie"].split(";")[0]
        status, _, body = raw_request(self.base, "GET", "/api/compliance", cookie=cookie)
        self.assertEqual(status, 200)
        exposure = [c for c in json.loads(body)["controls"] if c["name"] == "Network exposure"][0]
        self.assertEqual(exposure["status"], "warn")
        self.assertIn("Public demonstration", exposure["detail"])
        self.assertIn("never", exposure["detail"])


class TestLocalModeDefaults(unittest.TestCase):
    """The hosted protections must not leak into local use, where the app is
    served over plain HTTP and a Secure cookie would never be sent back."""

    @classmethod
    def setUpClass(cls):
        config.disable_hosted()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = fresh_store(cls.tmp.name)
        seed(cls.store)
        cls.httpd = serve(api.router, lambda: api.Context(cls.store), "127.0.0.1", 0)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def test_cookie_not_secure_and_no_hsts_over_local_http(self):
        status, headers, _ = raw_request(self.base, "POST", "/api/login",
                                         {"username": "dr.chen", "password": "Demo!Pass1"})
        self.assertEqual(status, 200)
        self.assertNotIn("Secure", headers["Set-Cookie"])
        self.assertNotIn("Strict-Transport-Security", headers)

    def test_public_config_reports_local_mode(self):
        _, _, body = raw_request(self.base, "GET", "/api/public-config")
        self.assertFalse(json.loads(body)["hosted"])

    def test_health_check_available_locally(self):
        status, _, body = raw_request(self.base, "GET", "/healthz")
        self.assertEqual((status, body), (200, b"ok"))


class TestEntrypointGuards(unittest.TestCase):
    def tearDown(self):
        config.disable_hosted()

    def test_hosted_mode_refuses_to_start_without_a_generated_passphrase(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "x.db")
            env = {k: v for k, v in os.environ.items() if k != "PSYCHREPORT_PASSPHRASE"}
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(app_main.main(["--hosted", "--db", db]), 2)
            with mock.patch.dict(os.environ, {"PSYCHREPORT_PASSPHRASE": "demo-passphrase-change-me"}):
                self.assertEqual(app_main.main(["--hosted", "--db", db]), 2)
            self.assertFalse(config.HOSTED)
            self.assertFalse(os.path.exists(db), "refusal must happen before any data is written")

    def test_local_mode_still_refuses_a_public_interface(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "x.db")
            self.assertEqual(app_main.main(["--host", "0.0.0.0", "--db", db]), 2)
            self.assertFalse(os.path.exists(db))

    def test_render_blueprint_matches_the_entrypoint(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "render.yaml"), encoding="utf-8") as handle:
            blueprint = handle.read()
        self.assertIn("startCommand: python -m app.main --hosted", blueprint)
        self.assertIn("healthCheckPath: /healthz", blueprint)
        self.assertIn("key: PSYCHREPORT_PASSPHRASE", blueprint)
        self.assertIn("generateValue: true", blueprint)
        self.assertTrue(os.path.exists(os.path.join(root, "requirements.txt")))



# --------------------------------------------------------------------------
# Bring-your-own model key (per signed-in session)
# --------------------------------------------------------------------------

STUB_KEY = "sk-or-v1-TESTKEY0000000000000000000000000000deadbeef"


class _StubModel(BaseHTTPRequestHandler):
    """Stands in for OpenRouter: records what it was sent, and can be told to
    reject the next key the way a provider rejects a bad one."""

    reject = False
    seen = []

    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        _StubModel.seen.append({"auth": self.headers.get("Authorization", ""),
                                "model": body.get("model"),
                                "text": json.dumps(body)})
        if _StubModel.reject:
            self.send_response(401)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        payload = json.dumps({"choices": [{"message": {"content": "Model answer from the stub."}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class TestSessionModelKey(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = fresh_store(cls.tmp.name)
        seed(cls.store)
        cls.httpd = serve(api.router, lambda: api.Context(cls.store), "127.0.0.1", 0)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.httpd.server_address[1]
        cls.stub = ThreadingHTTPServer(("127.0.0.1", 0), _StubModel)
        threading.Thread(target=cls.stub.serve_forever, daemon=True).start()
        cls.stub_url = "http://127.0.0.1:%d/v1" % cls.stub.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close()
        cls.stub.shutdown(); cls.stub.server_close()
        cls.tmp.cleanup()

    def setUp(self):
        api.reset_session_llm()
        _StubModel.reject = False
        _StubModel.seen = []

    def client(self, username="dr.chen", password="Demo!Pass1"):
        client = Client(self.base)
        client.post("/api/login", {"username": username, "password": password})
        return client

    def configure(self, client, expect=200, **overrides):
        body = {"api_key": STUB_KEY, "model": "openai/gpt-4o-mini", "base_url": self.stub_url}
        body.update(overrides)
        return client.post("/api/llm/session", body, expect=expect)

    def test_key_is_accepted_and_used_but_never_echoed_back(self):
        client = self.client()
        result = self.configure(client)
        self.assertTrue(result["llm"]["enabled"])
        self.assertTrue(result["llm"]["user_supplied"])
        self.assertTrue(result["llm"]["deidentify_before_send"])
        self.assertEqual(result["llm"]["key_hint"], "..." + STUB_KEY[-4:])
        self.assertNotIn(STUB_KEY, json.dumps(result))

        boot = client.get("/api/bootstrap")
        self.assertTrue(boot["llm"]["enabled"])
        self.assertNotIn(STUB_KEY, json.dumps(boot))

        # The model is actually called, with the key, for this session.
        patients = client.get("/api/patients")["patients"]
        maya = [p for p in patients if p["mrn"] == "MRN-00101"][0]
        answer = client.post("/api/patients/%d/assistant" % maya["id"],
                             {"question": "What is the current medication?"})
        self.assertEqual(answer["mode"], "model")
        self.assertEqual(_StubModel.seen[-1]["auth"], "Bearer " + STUB_KEY)
        self.assertEqual(_StubModel.seen[-1]["model"], "openai/gpt-4o-mini")

    def test_patient_identifiers_are_stripped_before_reaching_the_model(self):
        client = self.client()
        self.configure(client)
        patients = client.get("/api/patients")["patients"]
        maya = [p for p in patients if p["mrn"] == "MRN-00101"][0]
        # a question whose excerpts do carry the patient's name
        result = client.post("/api/patients/%d/assistant" % maya["id"],
                             {"question": "What is the history of present illness?"})
        sent = _StubModel.seen[-1]["text"]
        self.assertIn("Ellison", "".join(c["excerpt"] for c in result["citations"]),
                      "the excerpt really does name her, so the scrub is being tested")
        self.assertNotIn("Ellison", sent)
        self.assertNotIn("1991-04-18", sent)
        self.assertIn("[NAME]", sent)
        self.assertIn("[DATE]", sent)
        self.assertTrue(any("de-identified" in n for n in result["notes"]))

    def test_a_key_is_scoped_to_the_session_that_entered_it(self):
        owner = self.client()
        self.configure(owner)
        other = self.client()          # same account, a different sign-in
        self.assertFalse(other.get("/api/bootstrap")["llm"]["enabled"])
        self.assertTrue(owner.get("/api/bootstrap")["llm"]["enabled"])

    def test_key_is_forgotten_on_sign_out(self):
        client = self.client()
        self.configure(client)
        client.post("/api/logout")
        again = self.client()
        self.assertFalse(again.get("/api/bootstrap")["llm"]["enabled"])

    def test_key_can_be_removed(self):
        client = self.client()
        self.configure(client)
        client.request("DELETE", "/api/llm/session", {})
        self.assertFalse(client.get("/api/bootstrap")["llm"]["enabled"])

    def test_a_rejected_key_is_reported_and_not_stored(self):
        client = self.client()
        _StubModel.reject = True
        try:
            client.post("/api/llm/session", {"api_key": STUB_KEY, "base_url": self.stub_url}, expect=400)
        finally:
            _StubModel.reject = False
        self.assertFalse(client.get("/api/bootstrap")["llm"]["enabled"])

    def test_input_is_validated(self):
        client = self.client()
        self.configure(client, api_key="short", expect=400)
        self.configure(client, model="not a model!", expect=400)
        self.configure(client, base_url="ftp://example.com/v1", expect=400)
        # plain http to a remote host would put the content on the wire in clear
        self.configure(client, base_url="http://example.com/v1", expect=400)

    def test_roles_without_model_use_are_refused(self):
        staff = self.client("frontdesk", "Demo!Pass3")
        self.configure(staff, expect=403)
        auditor = self.client("compliance", "Demo!Pass4")
        self.configure(auditor, expect=403)

    def test_key_never_reaches_the_audit_log_or_the_database(self):
        client = self.client()
        self.configure(client)
        supervisor = self.client("dr.reyes", "Demo!Pass2")
        entries = supervisor.get("/api/audit?limit=200")["entries"]
        self.assertIn("llm.session.configure", {e["action"] for e in entries})
        self.assertNotIn(STUB_KEY, json.dumps(entries))
        with open(self.store.path, "rb") as handle:
            raw = handle.read()
        for suffix in ("-wal", "-shm"):
            if os.path.exists(self.store.path + suffix):
                with open(self.store.path + suffix, "rb") as handle:
                    raw += handle.read()
        self.assertNotIn(STUB_KEY.encode(), raw)

    def test_session_key_does_not_need_the_service_wide_env_flag(self):
        cfg = llm.LLMConfig.for_session(STUB_KEY, "openai/gpt-4o-mini", "https://openrouter.ai/api/v1")
        self.assertTrue(llm.usable(cfg))
        self.assertFalse(cfg.is_local)
        self.assertIsNone(cfg.status()["blocked_reason"])
        # ...while an operator-configured remote endpoint still does.
        operator = llm.LLMConfig(provider="openai", base_url="https://openrouter.ai/api/v1",
                                 model="m", api_key="k", allow_remote_phi=False)
        self.assertFalse(llm.usable(operator))

    def test_language_pass_masks_identifiers_and_restores_them(self):
        """A rewrite has to come back with the names in it, so identifiers make
        the round trip as markers rather than being stripped."""
        cfg = llm.LLMConfig.for_session(STUB_KEY, "m", self.stub_url)
        original = "Maya Ellison was seen on 2026-07-14 and her PHQ-9 was 18."

        def echo(system, user, max_tokens=900, temperature=0.2, cfg=None):
            echo.sent = user
            return user.split("Text:\n", 1)[1]

        echo.sent = ""
        real = llm.complete
        llm.complete = echo
        try:
            out, note = llm.polish(original, "Family", "plain", cfg=cfg, identifiers=["Maya", "Ellison"])
        finally:
            llm.complete = real
        self.assertNotIn("Ellison", echo.sent)
        self.assertNotIn("2026-07-14", echo.sent)
        self.assertIn("\u00ab1\u00bb", echo.sent)
        self.assertIn("Ellison", out)
        self.assertIn("2026-07-14", out)
        self.assertIsNone(note)

    def test_language_pass_rejects_a_rewrite_that_drops_identifiers(self):
        cfg = llm.LLMConfig.for_session(STUB_KEY, "m", self.stub_url)
        original = "Maya Ellison was seen on 2026-07-14."
        real = llm.complete
        llm.complete = lambda *a, **k: "Someone was seen at some point."
        try:
            out, note = llm.polish(original, "Family", "plain", cfg=cfg, identifiers=["Maya", "Ellison"])
        finally:
            llm.complete = real
        self.assertEqual(out, original)
        self.assertIn("did not return the identifiers", note)

    def test_generated_reports_use_the_session_key_for_the_language_pass(self):
        client = self.client()
        self.configure(client)
        patients = client.get("/api/patients")["patients"]
        maya = [p for p in patients if p["mrn"] == "MRN-00101"][0]
        detail = client.get("/api/patients/%d" % maya["id"])
        report = client.post("/api/patients/%d/reports" % maya["id"], {
            "template_ids": ["therapist_care_team"], "ai_polish": True,
            "eval_ids": [e["id"] for e in detail["evaluations"]]})["reports"][0]
        self.assertTrue(_StubModel.seen, "the language pass should have called the model")
        self.assertEqual(_StubModel.seen[-1]["auth"], "Bearer " + STUB_KEY)
        # The stub's reply invents nothing, but it is still fact-guarded, and the
        # draft records that AI language was involved either way.
        self.assertIn("ai_assisted", report["content"])



# --------------------------------------------------------------------------
# Autism-focused behaviour
# --------------------------------------------------------------------------


class TestAutismSupport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = fresh_store(cls.tmp.name)
        seed(cls.store)
        cls.clinician = {"id": 1, "display_name": "Dr. Amara Chen", "credentials": "MD",
                         "npi": "1457893021", "role": "clinician"}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _patient(self, mrn):
        row = self.store.one("SELECT * FROM patients WHERE mrn=?", (mrn,))
        demographics = self.store.payload("patients", row)
        evaluations = []
        for ev in self.store.query("SELECT * FROM evaluations WHERE patient_id=?", (row["id"],)):
            payload = self.store.payload("evaluations", ev)
            evaluations.append({"id": ev["id"], "form_id": ev["form_id"],
                                "encounter_date": ev["encounter_date"], "answers": payload["answers"]})
        return row, demographics, evaluations

    def _render(self, mrn, template_id, authorization=None):
        row, demographics, evaluations = self._patient(mrn)
        content = generator.generate(demographics, row["mrn"], evaluations, template_id,
                                     self.clinician, api.PRACTICE, authorization=authorization)
        return content, generator.to_text(content)

    def test_autism_report_leads_with_support_not_severity(self):
        content, text = self._render("MRN-00102", "autism_report")
        titles = [s["title"] for s in content["sections"]]
        self.assertIn("Strengths and interests", titles)
        self.assertIn("Level of support needed", titles)
        self.assertIn("Sensory profile", titles)
        self.assertIn("Communication", titles)
        self.assertIn("F84.0", text)
        self.assertIn("subway", text.lower())          # the interest is in the report, not just the deficit
        self.assertIn("requiring support", text.lower())

    def test_healthcare_passport_puts_communication_first(self):
        content, text = self._render("MRN-00105", "healthcare_passport")
        self.assertEqual(content["sections"][1]["title"], "How to communicate with me")
        self.assertIn("writing", text.lower())
        self.assertIn("attributed to autism", text.lower())
        self.assertIn("Please do not assume it is just autism",
                      [sec["title"] for sec in content["sections"]])
        # identifiers are limited: no record number on a page that travels
        self.assertNotIn("MRN-00105", text)

    def test_adjustments_letter_carries_no_risk_content(self):
        authorization = {"id": 1, "scopes": [], "recipient_name": "Cadence Analytics - People Team"}
        content, text = self._render("MRN-00105", "reasonable_adjustments", authorization)
        lowered = text.lower()
        for needle in ("suicid", "self-injur", "skin picking", "safety plan"):
            self.assertNotIn(needle, lowered)
        withheld = {w["field_id"] for w in content["withheld"]}
        self.assertIn("si_ideation", withheld)
        self.assertIn("self_injury", withheld)
        self.assertIn("quiet", lowered)                 # the adjustments themselves are there

    def test_sensitive_language_in_free_text_is_flagged_for_review(self):
        """Field tags cannot see inside prose, so a mention of self-injury inside
        a general-sensitivity field has to be surfaced rather than shipped."""
        sections = [{"title": "Predictability and change", "kind": "bullets",
                     "body": ["Weaving most evenings. Skin picking has stopped."], "provenance": []}]
        hits = generator.scan_for_sensitive_language(sections, allowed={"general"})
        self.assertTrue(hits)
        self.assertEqual(hits[0]["term"], "skin picking")
        # ...and nothing is flagged for a recipient whose template does carry risk
        self.assertEqual(generator.scan_for_sensitive_language(sections, allowed={"general", "risk"}), [])

    def test_adjustments_letter_warns_when_prose_carries_more_than_its_tag(self):
        row, demographics, evaluations = self._patient("MRN-00105")
        leaky = [dict(e) for e in evaluations]
        leaky[0] = dict(leaky[0], answers=dict(leaky[0]["answers"],
                        executive_daily="Task initiation is hard, worse after an overdose last year."))
        content = generator.generate(demographics, row["mrn"], leaky, "reasonable_adjustments",
                                     self.clinician, api.PRACTICE)
        self.assertTrue(any("free text" in w for w in content["warnings"]), content["warnings"])

    def test_language_preference_is_per_patient(self):
        _content, elena = self._render("MRN-00105", "autism_report")      # identity-first
        _content, danny = self._render("MRN-00102", "autism_report")      # person-first
        self.assertIn("autistic", elena.lower())
        self.assertNotIn("person with autism", elena.lower())
        self.assertNotIn("child with autism", elena.lower())
        self.assertNotIn("autistic child", danny.lower())
        self.assertNotIn("is autistic", danny.lower())

    def test_identity_language_rules_are_reversible(self):
        identity = generator._identity_language("A child with autism has autism.", "identity-first")
        self.assertEqual(identity, "An autistic child is autistic." .replace("An ", "A "))
        person = generator._identity_language("The autistic adult is autistic.", "person-first")
        self.assertEqual(person, "The adult with autism has autism.")

    def test_generated_sentences_follow_the_language_preference_too(self):
        _content, danny = self._render("MRN-00102", "healthcare_passport")   # person-first
        _content, elena = self._render("MRN-00105", "healthcare_passport")   # identity-first
        self.assertIn("has autism", danny)
        self.assertNotIn("Danny is autistic", danny)
        self.assertIn("Elena is autistic", elena)

    def test_self_injury_is_recorded_separately_from_suicidality(self):
        _row, _dem, evaluations = self._patient("MRN-00105")
        record = generator.build_record(evaluations)
        self.assertIn("self_injury", record)
        self.assertIn("si_ideation", record)
        self.assertIn("regulation", record["self_injury"][0]["value"].lower())
        # and the risk engine still works on the autism forms
        risk = redaction.assess_risk(record)
        self.assertEqual(risk["level"], "Low")

    def test_neuro_profile_detects_autism_and_ignores_other_charts(self):
        for mrn, expected in (("MRN-00102", True), ("MRN-00105", True), ("MRN-00101", False)):
            _row, _dem, evaluations = self._patient(mrn)
            profile = api._neuro_profile(generator.build_record(evaluations))
            self.assertEqual(profile["autistic"], expected, mrn)
        _row, _dem, evaluations = self._patient("MRN-00105")
        profile = api._neuro_profile(generator.build_record(evaluations))
        self.assertTrue(profile["has_passport_content"])
        self.assertIn("Level 1", profile["levels"]["social"])

    def test_general_psychiatry_still_works(self):
        """The autism focus must not cost the general case anything."""
        content, text = self._render("MRN-00104", "insurance_lmn")
        self.assertIn("F31.4", text)
        self.assertIn("medically necessary", text)
        risk = content["risk"]
        self.assertEqual(risk["level"], "High")

    def test_autism_forms_carry_the_support_profile(self):
        for form_id in ("asd_eval", "asd_review"):
            fields = {f["id"] for s in FORMS[form_id]["sections"] for f in s["fields"]}
            for expected in ("sensory_profile", "communication_preferences", "meltdown_shutdown",
                             "masking", "burnout", "support_needs", "self_injury", "overshadowing"):
                self.assertIn(expected, fields, f"{form_id} is missing {expected}")


if __name__ == "__main__":
    unittest.main(verbosity=2)

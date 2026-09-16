"""Recipient-specific report templates.

A template is a disclosure contract as much as a document layout.  It declares
who the audience is, the lawful purpose of the disclosure, which sensitivity
classes it may ever carry (HIPAA minimum-necessary), how much identity to
include, and the reading level.  app/generator.py renders it; app/redaction.py
enforces it.
"""

from __future__ import annotations

# Identifier policies
FULL = "full"           # name, DOB, MRN -- clinical recipients / payers
LIMITED = "limited"     # name + DOB only
MINIMAL = "minimal"     # name only (or initials for de-identified previews)

PLAIN = "plain"                  # ~8th grade, jargon translated
PROFESSIONAL = "professional"    # clinician to clinician
ADMINISTRATIVE = "administrative"  # payer / school / employer administrator

# Sensitivity classes every template gets for free.
BASE_SENS = ("general",)


def _s(title, kind="narrative", sources=(), intro="", builder=None, required=False, note=""):
    return {"title": title, "kind": kind, "sources": list(sources), "intro": intro,
            "builder": builder, "required": required, "note": note}


FAMILY_CAREGIVER = {
    "id": "family_caregiver",
    "name": "Summary for Family / Caregiver",
    "recipient_type": "Family member or caregiver",
    "purpose": "Involvement of a designated support person in care, at the patient's request",
    "reading_level": PLAIN,
    "identifiers": LIMITED,
    "requires_authorization": True,
    "allowed_sens": BASE_SENS + ("risk",),
    "audience_note": "Written for a non-clinical reader. Clinical terms are translated; "
                     "substance use, trauma, sexual and legal history are withheld unless the "
                     "patient's authorization names them.",
    "sections": [
        _s("Why we met", "narrative", ["chief_complaint", "referral_source"], required=True),
        _s("What we talked about", "narrative", ["hpi", "interval_history", "symptom_review"]),
        _s("What I found", "narrative", ["summary", "formulation", "assessment"], required=True),
        _s("The diagnosis, in plain terms", "codes", ["dsm_diagnoses"],
           intro="A diagnosis is a shorthand clinicians use to describe a pattern of symptoms. "
                 "It describes something the person is experiencing, not who they are."),
        _s("How this affects day-to-day life", "bullets",
           ["func_work_school", "func_social", "func_selfcare", "func_cognitive", "impairment"]),
        _s("Strengths we are building on", "narrative", ["strengths", "protective"]),
        _s("The plan", "bullets", ["treatment_plan", "recommendations_clinical", "recommendations_family"],
           required=True),
        _s("How you can help", "narrative", ["recommendations_family"],
           intro="Practical ways a support person can help between visits."),
        _s("Safety", "custom", builder="safety_family"),
        _s("If you need help right now", "custom", builder="crisis_resources"),
        _s("Questions", "custom", builder="contact_block"),
    ],
    "footer": "This summary was shared with your permission. It is not a complete copy of the "
              "medical record. If anything here does not match your understanding, tell your "
              "clinician -- the record should be corrected.",
}

PATIENT_AVS = {
    "id": "patient_avs",
    "name": "After-Visit Summary for the Patient",
    "recipient_type": "Patient",
    "purpose": "Treatment; patient's right of access to their own information",
    "reading_level": PLAIN,
    "identifiers": LIMITED,
    "requires_authorization": False,
    "allowed_sens": BASE_SENS + ("risk", "sud", "trauma", "sexual", "hiv", "genetic", "forensic"),
    "audience_note": "The patient has a right of access to their own record (45 CFR 164.524). "
                     "Psychotherapy process notes are the one category excluded.",
    "sections": [
        _s("What we discussed today", "narrative", ["chief_complaint", "hpi", "interval_history"], required=True),
        _s("What we decided", "narrative", ["assessment", "summary", "formulation"]),
        _s("Your diagnoses", "codes", ["dsm_diagnoses"]),
        _s("Your medicines", "bullets", ["current_medications", "medication_current"],
           intro="Take these as prescribed. Tell your clinician about side effects before stopping anything."),
        _s("Side effects to watch for", "narrative", ["side_effects", "informed_consent", "monitoring"]),
        _s("Your plan before the next visit", "bullets", ["treatment_plan", "recommendations_clinical"], required=True),
        _s("Your safety plan", "custom", builder="safety_plan_patient"),
        _s("Next appointment", "kv", ["followup", "reassessment"]),
        _s("If you need help right now", "custom", builder="crisis_resources"),
    ],
    "footer": "You have the right to a copy of your record and to ask for corrections.",
}

SCHOOL_IEP = {
    "id": "school_iep",
    "name": "Letter to School Team (IEP / 504)",
    "recipient_type": "School / educational team",
    "purpose": "Support an educational eligibility determination or accommodation plan",
    "reading_level": ADMINISTRATIVE,
    "identifiers": LIMITED,
    "requires_authorization": True,
    "allowed_sens": BASE_SENS,
    "audience_note": "Schools need functional impact and actionable accommodations, not the full "
                     "clinical history. Risk content, substance use, trauma, sexual and family "
                     "genetic history are withheld by default; a diagnosis is included only "
                     "because eligibility categories require it.",
    "sections": [
        _s("Purpose of this letter", "custom", builder="school_intro", required=True),
        _s("Evaluation completed", "kv", ["encounter_date", "informants"],
           intro="Sources of information for this evaluation:"),
        _s("Instruments administered", "bullets",
           ["ados_module", "ados_scores", "adir", "rating_scales", "cognitive", "language_assessment",
            "adaptive", "vanderbilt", "conners", "academic", "cognitive_testing"]),
        _s("Diagnostic conclusions", "codes", ["dsm_diagnoses"], required=True),
        _s("How this presents in the classroom", "narrative",
           ["func_work_school", "func_cognitive", "impairment", "school_history", "d_impairment"], required=True),
        _s("Strengths", "narrative", ["strengths"]),
        _s("Recommended supports and accommodations", "bullets",
           ["recommendations_school"], required=True,
           intro="The following are clinical recommendations. Educational eligibility and the "
                 "contents of an IEP or 504 plan are determined by the school team with the family."),
        _s("Re-evaluation", "kv", ["reassessment", "followup"]),
        _s("Contact", "custom", builder="contact_block"),
    ],
    "footer": "Released with written authorization from the parent/guardian. This letter is a "
              "clinical opinion for educational planning; it does not itself establish eligibility "
              "under IDEA or Section 504. Please do not redisclose without a new authorization.",
}

INSURANCE_LMN = {
    "id": "insurance_lmn",
    "name": "Letter of Medical Necessity (Insurer)",
    "recipient_type": "Insurance company / utilisation review",
    "purpose": "Payment; prior authorisation or appeal of a coverage determination",
    "reading_level": ADMINISTRATIVE,
    "identifiers": FULL,
    "requires_authorization": False,
    "allowed_sens": BASE_SENS + ("risk",),
    "audience_note": "Disclosure for payment is permitted without authorization, but is still "
                     "bound by minimum necessary. Substance use content requires a Part 2 "
                     "consent naming the payer; trauma, sexual, genetic and legal detail are withheld.",
    "sections": [
        _s("Member and provider information", "custom", builder="insurance_header", required=True),
        _s("Diagnoses", "codes", ["dsm_diagnoses", "severity_specifiers"], required=True),
        _s("Clinical presentation", "narrative", ["hpi", "symptom_review", "interval_history"], required=True),
        _s("Objective findings", "custom", builder="measures_table", required=True),
        _s("Mental status examination", "kv",
           ["mse_appearance", "mse_mood", "mse_affect", "mse_thought_process", "mse_thought_content",
            "mse_cognition", "mse_insight", "mse_judgment"]),
        _s("Risk", "custom", builder="risk_summary_clinical"),
        _s("Functional impairment", "bullets",
           ["func_work_school", "func_social", "func_selfcare", "func_cognitive", "func_impact_summary",
            "impairment"], required=True),
        _s("Treatment history and response", "narrative",
           ["prior_treatment", "medication_trials", "psychotherapy_history", "adherence"], required=True,
           intro="Prior interventions, dose, duration and outcome -- documenting why less intensive "
                 "or alternative treatment has been insufficient:"),
        _s("Requested services", "bullets", ["treatment_plan", "monitoring", "followup"], required=True),
        _s("Medical necessity statement", "custom", builder="necessity_statement", required=True),
        _s("Attestation", "custom", builder="attestation"),
    ],
    "footer": "Submitted for utilisation review. Contains protected health information disclosed "
              "for payment purposes under 45 CFR 164.506(c)(3), limited to the minimum necessary.",
}

REFERRING_CLINICIAN = {
    "id": "referring_clinician",
    "name": "Consultation Letter to Referring Clinician",
    "recipient_type": "Referring or consulting clinician",
    "purpose": "Treatment; continuity of care",
    "reading_level": PROFESSIONAL,
    "identifiers": FULL,
    "requires_authorization": False,
    "allowed_sens": BASE_SENS + ("risk", "trauma", "genetic", "sexual", "hiv"),
    "audience_note": "Treatment disclosure between clinicians. Substance use content still "
                     "requires a 42 CFR Part 2 consent; psychotherapy process notes are never included.",
    "sections": [
        _s("Reason for referral", "narrative", ["referral_source", "chief_complaint"], required=True),
        _s("History of present illness", "narrative", ["hpi", "symptom_review", "interval_history"], required=True),
        _s("Past psychiatric history", "narrative",
            ["prior_diagnoses", "prior_treatment", "medication_trials", "psychotherapy_history"]),
        _s("Medical history and medications", "narrative",
            ["medical_conditions", "current_medications", "medication_current", "allergies",
             "surgical_neuro", "vitals_labs", "baseline_vitals"]),
        _s("Family and social history", "narrative",
            ["family_psych_history", "family_medical_history", "developmental", "education_work",
             "relationships", "trauma_history", "social_determinants"]),
        _s("Mental status examination", "kv",
           ["mse_appearance", "mse_attitude", "mse_motor", "mse_speech", "mse_mood", "mse_affect",
            "mse_thought_process", "mse_thought_content", "mse_perception", "mse_cognition",
            "mse_insight", "mse_judgment"], required=True),
        _s("Testing and measures", "custom", builder="measures_table"),
        _s("Risk assessment", "custom", builder="risk_summary_clinical", required=True),
        _s("Formulation", "narrative", ["formulation", "differential", "summary"], required=True),
        _s("Diagnoses", "codes", ["dsm_diagnoses", "severity_specifiers", "specifiers"], required=True),
        _s("Plan", "bullets", ["treatment_plan", "recommendations_clinical", "monitoring", "followup"], required=True),
        _s("Attestation", "custom", builder="attestation"),
    ],
    "footer": "Confidential clinical correspondence. Redisclosure beyond the treatment relationship "
              "requires patient authorization.",
}

THERAPIST_CARE_TEAM = {
    "id": "therapist_care_team",
    "name": "Care Coordination Summary (Therapist / Care Team)",
    "recipient_type": "Psychotherapist or care team member",
    "purpose": "Treatment; coordination of concurrent care",
    "reading_level": PROFESSIONAL,
    "identifiers": LIMITED,
    "requires_authorization": False,
    "allowed_sens": BASE_SENS + ("risk", "trauma"),
    "audience_note": "Scoped to what a concurrent therapist needs: current presentation, "
                     "medication, risk, and the division of labour between clinicians.",
    "sections": [
        _s("Current presentation", "narrative", ["interval_history", "hpi", "symptom_review"], required=True),
        _s("Diagnoses", "codes", ["dsm_diagnoses"], required=True),
        _s("Current medication and monitoring", "bullets",
           ["current_medications", "medication_current", "side_effects", "monitoring"]),
        _s("Measures", "custom", builder="measures_table"),
        _s("Risk and safety plan", "custom", builder="risk_summary_clinical", required=True),
        _s("Suggested therapy targets", "bullets",
           ["treatment_plan", "recommendations_clinical", "func_impact_summary"], required=True),
        _s("Coordination", "custom", builder="coordination_block"),
    ],
    "footer": "Shared for coordination of concurrent treatment. Please contact the prescriber "
              "directly for any change in risk status.",
}

EMPLOYER_ACCOMMODATION = {
    "id": "employer_accommodation",
    "name": "Workplace Accommodation Letter (ADA / FMLA)",
    "recipient_type": "Employer / occupational health",
    "purpose": "Support a request for reasonable accommodation or protected leave",
    "reading_level": ADMINISTRATIVE,
    "identifiers": MINIMAL,
    "requires_authorization": True,
    "allowed_sens": BASE_SENS,
    "audience_note": "Employers are entitled to functional limitations and the accommodation "
                     "requested, not to the diagnosis or clinical history. Diagnosis is omitted "
                     "unless the patient specifically authorises its release.",
    "sections": [
        _s("Purpose", "custom", builder="employer_intro", required=True),
        _s("Treatment relationship", "custom", builder="treatment_relationship", required=True),
        _s("Functional limitations relevant to work", "bullets",
           ["func_work_school", "func_cognitive", "func_social", "func_impact_summary", "impairment"],
           required=True),
        _s("Requested accommodations", "bullets", ["recommendations_school", "treatment_plan"], required=True,
           intro="The following adjustments are expected to allow the employee to perform the "
                 "essential functions of their role:"),
        _s("Expected duration and review", "kv", ["followup", "reassessment", "prognosis"]),
        _s("Contact", "custom", builder="contact_block"),
    ],
    "footer": "This letter addresses functional capacity only. Under the ADA, medical information "
              "must be kept in a confidential file separate from the personnel file.",
}

DISABILITY_SSA = {
    "id": "disability_ssa",
    "name": "Disability / Functional Capacity Report",
    "recipient_type": "Disability adjudicator (SSA or private carrier)",
    "purpose": "Determination of eligibility for disability benefits",
    "reading_level": ADMINISTRATIVE,
    "identifiers": FULL,
    "requires_authorization": True,
    "allowed_sens": BASE_SENS + ("risk",),
    "audience_note": "Organised around the four broad areas of mental functioning used in "
                     "adjudication: understanding and applying information; interacting with "
                     "others; concentrating, persisting or maintaining pace; adapting or "
                     "managing oneself.",
    "sections": [
        _s("Treatment relationship", "custom", builder="treatment_relationship", required=True),
        _s("Diagnoses", "codes", ["dsm_diagnoses", "severity_specifiers"], required=True),
        _s("Clinical findings supporting the diagnoses", "narrative",
           ["hpi", "symptom_review", "mse_thought_content", "mse_affect", "mse_cognition"], required=True),
        _s("Objective measures", "custom", builder="measures_table"),
        _s("Understanding, remembering and applying information", "narrative", ["func_cognitive", "cognitive"]),
        _s("Interacting with others", "narrative", ["func_social", "relationships"]),
        _s("Concentrating, persisting and maintaining pace", "narrative", ["func_cognitive", "func_work_school"]),
        _s("Adapting and managing oneself", "narrative", ["func_selfcare", "adaptive"]),
        _s("Treatment, response and prognosis", "narrative",
           ["medication_trials", "prior_treatment", "adherence", "treatment_plan", "prognosis"], required=True),
        _s("Expected absences and off-task time", "bullets", ["func_impact_summary", "impairment"]),
        _s("Attestation", "custom", builder="attestation"),
    ],
    "footer": "Prepared at the request of the patient with written authorization. Opinions are "
              "based on the treatment record and examination findings documented above.",
}


AUTISM_REPORT = {
    "id": "autism_report",
    "name": "Autism Diagnostic Report",
    "recipient_type": "Autistic person and family",
    "purpose": "Diagnostic feedback and support planning",
    "reading_level": PLAIN,
    "identifiers": LIMITED,
    "requires_authorization": False,
    "allowed_sens": BASE_SENS + ("risk", "genetic"),
    "audience_note": "The report the family actually keeps. Written to be read by the autistic person "
                     "and the people around them, and organised so the support profile carries as much "
                     "weight as the diagnosis. Released under the right of access; sharing it onward is "
                     "the family's decision.",
    "sections": [
        _s("Why this assessment happened", "narrative", ["referral_source", "chief_complaint"], required=True),
        _s("How the assessment was done", "kv", ["encounter_date", "informants", "adjustments_made"]),
        _s("What was administered", "bullets",
           ["ados_module", "ados_scores", "adir", "rating_scales", "adult_instruments", "cognitive",
            "language_assessment", "adaptive", "comorbid_screens"]),
        _s("Development over time", "narrative",
           ["milestones", "language_dev", "social_dev", "rrb_history", "sensory_history"]),
        _s("Social communication: what was observed", "narrative", ["a1", "a2", "a3"]),
        _s("Repetitive behaviour, interests and sensory responses", "narrative", ["b1", "b2", "b3", "b4"]),
        _s("Present from early on, and affecting daily life", "narrative",
           ["c_onset", "d_impairment", "e_differential"]),
        _s("What else was considered", "narrative", ["differential"]),
        _s("The conclusion", "codes", ["dsm_diagnoses"], required=True,
           intro="A diagnosis describes a pattern and unlocks support. It does not describe a person's "
                 "worth, potential, or personality."),
        _s("Level of support needed", "custom", builder="support_levels"),
        _s("Strengths and interests", "narrative", ["strengths", "special_interests"], required=True),
        _s("Sensory profile", "narrative", ["sensory_profile", "sensory_supports"]),
        _s("Communication", "narrative", ["communication_profile", "aac", "communication_preferences"]),
        _s("Regulation, meltdown and shutdown", "narrative",
           ["regulation_profile", "meltdown_shutdown", "masking", "burnout"]),
        _s("Other conditions that travel with this", "narrative", ["co_occurring", "overshadowing"]),
        _s("Support needs", "bullets", ["support_needs", "executive_daily"]),
        _s("What helps", "bullets",
           ["recommendations_clinical", "recommendations_family", "recommendations_school"], required=True),
        _s("Safety", "bullets", ["elopement", "self_injury", "safety_plan"]),
        _s("Next steps", "kv", ["reassessment", "followup"]),
        _s("Questions", "custom", builder="contact_block"),
    ],
    "footer": "This report belongs to the person it describes. If anything here does not match how you "
              "see yourself or your child, say so - the record should be corrected.",
}

HEALTHCARE_PASSPORT = {
    "id": "healthcare_passport",
    "name": "Healthcare Communication Passport",
    "recipient_type": "Hospital or other healthcare team",
    "purpose": "Treatment; reasonable adjustments in a healthcare setting",
    "reading_level": PLAIN,
    "identifiers": LIMITED,
    "requires_authorization": False,
    "allowed_sens": BASE_SENS + ("risk",),
    "audience_note": "One page for an emergency department, ward or clinic that has never met this "
                     "person. Communication and sensory needs come first because that is what is "
                     "needed in the first five minutes; the diagnosis matters less than knowing how "
                     "to approach someone.",
    "sections": [
        _s("About this passport", "custom", builder="passport_intro", required=True),
        _s("How to communicate with me", "narrative",
           ["communication_preferences", "communication_profile", "aac"], required=True),
        _s("My sensory needs", "narrative", ["sensory_profile", "sensory_supports"]),
        _s("If I seem distressed", "narrative",
           ["distress_signs", "meltdown_shutdown", "regulation_profile"]),
        _s("What helps me", "bullets", ["sensory_supports", "support_needs", "special_interests"]),
        _s("Please do not assume it is just autism", "narrative", ["overshadowing"],
           intro="Pain and illness in autistic people are routinely missed because a change in "
                 "behaviour gets attributed to autism. Investigate a new symptom as you would for "
                 "anyone else."),
        _s("My health", "narrative",
           ["co_occurring", "medical_history", "medical_conditions", "current_medications",
            "medication_current", "allergies"]),
        _s("My diagnoses", "codes", ["dsm_diagnoses"]),
        _s("Safety", "bullets", ["elopement", "self_injury", "safety_plan"]),
        _s("Who to contact", "custom", builder="contact_block"),
    ],
    "footer": "Prepared by the person's psychiatric team to support reasonable adjustments. "
              "Please keep it with the notes and read it before approaching.",
}

REASONABLE_ADJUSTMENTS = {
    "id": "reasonable_adjustments",
    "name": "Reasonable Adjustments Letter",
    "recipient_type": "Education or employment support service",
    "purpose": "Support a request for reasonable adjustments",
    "reading_level": ADMINISTRATIVE,
    "identifiers": LIMITED,
    "requires_authorization": True,
    "allowed_sens": BASE_SENS,
    "audience_note": "Adjustments are changes to the environment and the demands, not to the person. "
                     "Written so each recommendation names the barrier it removes. Risk, trauma and "
                     "substance content are withheld; the diagnosis is included only because statutory "
                     "support usually requires it.",
    "sections": [
        _s("Purpose of this letter", "custom", builder="adjustments_intro", required=True),
        _s("Basis for this opinion", "custom", builder="treatment_relationship"),
        _s("Diagnosis", "codes", ["dsm_diagnoses"]),
        _s("How this presents day to day", "bullets",
           ["executive_daily", "func_work_school", "func_cognitive", "d_impairment", "impairment",
            "func_impact_summary"], required=True),
        _s("Sensory environment", "bullets", ["sensory_profile", "sensory_supports"]),
        _s("Communication", "bullets", ["communication_preferences", "communication_profile", "aac"]),
        _s("Predictability and change", "bullets", ["meltdown_shutdown"],
           intro="Shutdown is not refusal, and a change of plan costs more than it appears to:"),
        _s("Adjustments recommended", "bullets",
           ["recommendations_school", "support_needs", "treatment_plan"], required=True,
           intro="Each of these removes a specific barrier rather than lowering a standard:"),
        _s("Strengths to build on", "narrative", ["strengths", "special_interests"]),
        _s("Review", "kv", ["followup", "reassessment"]),
        _s("Contact", "custom", builder="contact_block"),
    ],
    "footer": "This letter describes functional needs and the adjustments that address them. Under the "
              "ADA, medical information must be kept confidential and separate from the personnel file.",
}


TEMPLATES = {t["id"]: t for t in (
    AUTISM_REPORT, HEALTHCARE_PASSPORT, REASONABLE_ADJUSTMENTS, SCHOOL_IEP,
    FAMILY_CAREGIVER, PATIENT_AVS, INSURANCE_LMN,
    REFERRING_CLINICIAN, THERAPIST_CARE_TEAM, EMPLOYER_ACCOMMODATION, DISABILITY_SSA,
)}


# Plain-language glossary used when reading_level == PLAIN.  Terms are
# replaced with an everyday phrase that keeps the clinical word in brackets so
# the reader can look it up and the meaning is not lost.
GLOSSARY = {
    # Autism vocabulary, explained without being explained away.
    "masking": "hiding autistic traits to fit in, which is exhausting (masking)",
    "camouflaging": "hiding autistic traits to fit in (camouflaging)",
    "autistic burnout": "exhaustion and loss of skills after too much demand (autistic burnout)",
    "meltdown": "an overwhelmed reaction that is not a tantrum and is not chosen (meltdown)",
    "shutdown": "withdrawing and going quiet when overwhelmed (shutdown)",
    "stimming": "repeated movement or sound that helps with regulation (stimming)",
    "dysregulation": "finding it hard to settle emotions or arousal",
    "interoception": "the sense of what is happening inside the body, like hunger or pain (interoception)",
    "proprioception": "the sense of where the body is in space (proprioception)",
    "AAC": "communication aids such as a speech app, signing or picture cards (AAC)",
    "elopement": "leaving a safe place suddenly, often to escape something overwhelming",
    "special interest": "a deep, focused interest",
    "neurodivergent": "having a brain that works differently from what is typical (neurodivergent)",
    "hyperreactivity": "reacting strongly to sights, sounds or touch",
    "hyporeactivity": "reacting less than expected to sights, sounds or touch",
    "diagnostic overshadowing": "blaming every new symptom on an existing diagnosis "
                                "(diagnostic overshadowing)",
    "anhedonia": "loss of interest or enjoyment (anhedonia)",
    "psychomotor retardation": "moving and thinking more slowly than usual (psychomotor retardation)",
    "psychomotor agitation": "restlessness that is hard to control (psychomotor agitation)",
    "euthymic": "in a stable mood (euthymic)",
    "dysphoric": "low or uncomfortable in mood (dysphoric)",
    "labile": "quickly shifting (labile)",
    "affect": "outward emotional expression",
    "insomnia": "trouble sleeping (insomnia)",
    "hypersomnia": "sleeping much more than usual (hypersomnia)",
    "suicidal ideation": "thoughts of suicide",
    "homicidal ideation": "thoughts of harming others",
    "passive suicidal ideation": "wishing not to be alive, without a plan",
    "auditory hallucinations": "hearing things others do not hear",
    "hallucinations": "seeing or hearing things others do not",
    "delusions": "strongly held beliefs that are not shared by others (delusions)",
    "paranoia": "fear that others mean harm (paranoia)",
    "comorbid": "occurring alongside",
    "etiology": "cause",
    "titration": "adjusting the dose step by step (titration)",
    "adherence": "taking treatment as prescribed",
    "prognosis": "the likely course over time",
    "sequelae": "lasting effects",
    "hypervigilance": "being constantly on guard (hypervigilance)",
    "avolition": "difficulty starting or finishing things (avolition)",
    "executive function": "planning, organising and getting started (executive function)",
    "perseveration": "getting stuck on one thing (perseveration)",
    "echolalia": "repeating words or phrases heard (echolalia)",
    "stereotyped": "repeated in the same way each time",
    "restricted, repetitive": "narrow and repeated",
    "reciprocity": "back-and-forth exchange",
    "social-emotional reciprocity": "back-and-forth social connection",
    "adaptive functioning": "everyday living skills",
    "sensory reactivity": "how strongly senses are experienced",
    "psychoeducation": "learning about the condition and how to manage it",
    "SSRI": "a common antidepressant (SSRI)",
    "MDD": "major depressive disorder",
    "GAD": "generalised anxiety disorder",
    "PTSD": "post-traumatic stress disorder",
    "ASD": "autism spectrum disorder",
    "ADHD": "attention-deficit/hyperactivity disorder",
    "prn": "as needed",
    "qhs": "at bedtime",
    "bid": "twice a day",
    "tid": "three times a day",
    "po": "by mouth",
}


def template_ids():
    return list(TEMPLATES.keys())

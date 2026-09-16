"""Clinical intake instruments.

Structure follows the APA *Practice Guidelines for the Psychiatric Evaluation
of Adults, 3rd ed.* (nine recommended domains: psychiatric symptom review,
trauma history, treatment history, substance use, suicide risk, aggression
risk, cultural factors, medical health, quantitative measures) plus the
documentation elements payers require for CPT 90791/90792.

Every field carries a `sens` (sensitivity) tag.  The redaction engine uses
those tags to enforce HIPAA minimum-necessary and the stricter 42 CFR Part 2
rules for substance-use-disorder content -- see app/redaction.py.
"""

from __future__ import annotations

# Sensitivity classes ------------------------------------------------------
# identifier        direct identifiers (HIPAA Safe Harbor list)
# general           routine clinical content
# risk              suicide / homicide / aggression risk content
# trauma            trauma & abuse history
# sud               substance use disorder content (42 CFR Part 2)
# sexual            sexual history / reproductive / gender-identity content
# genetic           genetic and family-genomic information (GINA)
# hiv               HIV / communicable disease status (state-law protected)
# forensic          legal / justice-system involvement
# process_note      clinician's private process/psychotherapy note content
#                   (HIPAA "psychotherapy notes" -- never auto-released)

SENSITIVITY_LABELS = {
    "identifier": "Direct identifiers",
    "general": "General clinical",
    "risk": "Risk assessment",
    "trauma": "Trauma history",
    "sud": "Substance use (42 CFR Part 2)",
    "sexual": "Sexual / reproductive history",
    "genetic": "Genetic / family genomic",
    "hiv": "HIV / communicable disease",
    "forensic": "Legal / forensic",
    "process_note": "Psychotherapy process note",
}

# Categories that may never be included in an outbound report unless the
# patient's authorization explicitly names them.
SPECIALLY_PROTECTED = ("sud", "hiv", "genetic", "trauma", "sexual", "forensic", "process_note")


def _f(fid, label, ftype="textarea", sens="general", **kw):
    field = {"id": fid, "label": label, "type": ftype, "sens": sens}
    field.update(kw)
    return field


MSE_SECTION = {
    "id": "mse",
    "title": "Mental Status Examination",
    "help": "Observed at the time of interview. All ten standard domains.",
    "fields": [
        _f("mse_appearance", "Appearance & behaviour", "textarea",
           help="Grooming, hygiene, dress, eye contact, cooperation."),
        _f("mse_attitude", "Attitude toward examiner", "select",
           options=["Cooperative", "Guarded", "Evasive", "Hostile", "Apathetic", "Seductive", "Other"]),
        _f("mse_motor", "Motor activity", "select",
           options=["Normal", "Psychomotor retardation", "Psychomotor agitation", "Tremor",
                    "Tics", "Akathisia", "Dyskinesia", "Catatonic features"]),
        _f("mse_speech", "Speech", "textarea", help="Rate, rhythm, volume, prosody, latency."),
        _f("mse_mood", "Mood (patient's own words)", "text"),
        _f("mse_affect", "Affect", "textarea", help="Range, reactivity, congruence, quality."),
        _f("mse_thought_process", "Thought process", "select",
           options=["Linear and goal-directed", "Circumstantial", "Tangential", "Loosening of associations",
                    "Flight of ideas", "Thought blocking", "Perseveration", "Disorganised"]),
        _f("mse_thought_content", "Thought content", "textarea",
           help="Preoccupations, obsessions, delusions, ideas of reference."),
        _f("mse_perception", "Perception", "textarea",
           help="Hallucinations (modality), illusions, depersonalisation, derealisation."),
        _f("mse_cognition", "Cognition", "textarea",
           help="Orientation, attention, registration/recall, language, abstraction; screen used and score."),
        _f("mse_insight", "Insight", "select", options=["Good", "Fair", "Limited", "Poor", "Absent"]),
        _f("mse_judgment", "Judgment", "select", options=["Good", "Fair", "Limited", "Poor"]),
    ],
}

RISK_SECTION = {
    "id": "risk",
    "title": "Risk Assessment",
    "help": "APA recommends a documented estimate of suicide risk and of risk for aggressive behaviour, "
            "with the factors that informed it. Columbia-style probes are provided as prompts.",
    "fields": [
        _f("si_ideation", "Suicidal ideation (past month)", "select", sens="risk",
           options=["None", "Passive (wish to be dead)", "Active, non-specific",
                    "Active with method, no intent", "Active with intent", "Active with intent and plan"]),
        _f("si_plan", "Plan / preparatory behaviour", "textarea", sens="risk"),
        _f("si_intent", "Stated intent", "select", sens="risk",
           options=["None", "Ambivalent", "Present"]),
        _f("si_means", "Access to lethal means (incl. firearms)", "textarea", sens="risk",
           help="Document counselling on means restriction if applicable."),
        _f("si_history", "Prior attempts / self-injury", "textarea", sens="risk"),
        _f("hi_ideation", "Homicidal / violent ideation", "select", sens="risk",
           options=["None", "Non-specific anger", "Ideation without target", "Ideation with identified target"]),
        _f("hi_detail", "Aggression risk detail (targets, history, weapons access)", "textarea", sens="risk"),
        _f("duty_to_warn", "Duty-to-warn / protect analysis", "textarea", sens="risk",
           help="If an identifiable potential victim exists, document notification decision and rationale."),
        _f("protective", "Protective factors", "textarea", sens="risk",
           help="Reasons for living, supports, treatment engagement, responsibility for children/pets, beliefs."),
        _f("risk_level", "Overall suicide risk stratification", "select", sens="risk",
           options=["Low", "Moderate", "High", "Imminent"], req=True),
        _f("risk_rationale", "Clinical rationale for stratification", "textarea", sens="risk", req=True),
        _f("safety_plan", "Safety plan / crisis plan", "textarea", sens="risk",
           help="Stanley-Brown elements: warning signs, internal coping, social contacts, professionals, means restriction."),
    ],
}

MEASURES_SECTION = {
    "id": "measures",
    "title": "Quantitative Measures",
    "help": "APA recommends quantitative measures at baseline and to track change.",
    "fields": [
        _f("phq9", "PHQ-9 total (0-27)", "number"),
        _f("gad7", "GAD-7 total (0-21)", "number"),
        _f("cssrs", "C-SSRS screener result", "text", sens="risk"),
        _f("audit_c", "AUDIT-C total (0-12)", "number", sens="sud"),
        _f("dast10", "DAST-10 total (0-10)", "number", sens="sud"),
        _f("mdq", "MDQ screen (positive/negative)", "text"),
        _f("ymrs", "YMRS total (0-60)", "number"),
        _f("pcl5", "PCL-5 total (0-80)", "number", sens="trauma"),
        _f("whodas", "WHODAS 2.0 / functional score", "text"),
        _f("other_measures", "Other instruments and scores", "textarea"),
    ],
}


ADULT_INITIAL = {
    "id": "adult_initial",
    "name": "Adult Initial Psychiatric Evaluation",
    "cpt": "90792",
    "description": "APA-aligned comprehensive initial evaluation (with medical services).",
    "sections": [
        {
            "id": "encounter",
            "title": "Encounter Information",
            "fields": [
                _f("encounter_date", "Date of service", "date", req=True),
                _f("encounter_setting", "Setting", "select",
                   options=["Outpatient clinic", "Telepsychiatry", "Inpatient", "Emergency department",
                            "Consultation-liaison", "Partial hospital / IOP"]),
                _f("encounter_duration", "Time spent (minutes)", "number"),
                _f("informants", "Informants and records reviewed", "textarea",
                   help="Collateral sources, prior records, and the reliability of each."),
                _f("interpreter", "Interpreter used", "select", options=["No", "Yes - professional", "Yes - family (document why)"]),
            ],
        },
        {
            "id": "presenting",
            "title": "Chief Complaint & History of Present Illness",
            "fields": [
                _f("chief_complaint", "Chief complaint (patient's own words)", "text", req=True),
                _f("hpi", "History of present illness", "textarea", req=True,
                   help="Onset, course, duration, severity, frequency, precipitants, ameliorating/aggravating "
                        "factors, associated symptoms, prior self-management, functional consequences."),
                _f("symptom_review", "Psychiatric review of symptoms", "textarea",
                   help="Mood, anxiety, psychosis, obsessive-compulsive, trauma-related, eating, sleep, "
                        "attention, somatic. Include pertinent negatives."),
                _f("sleep", "Sleep", "textarea"),
                _f("appetite_weight", "Appetite & weight", "textarea"),
            ],
        },
        {
            "id": "psych_history",
            "title": "Past Psychiatric & Treatment History",
            "fields": [
                _f("prior_diagnoses", "Prior psychiatric diagnoses", "textarea"),
                _f("prior_treatment", "Prior treatment episodes", "textarea",
                   help="Outpatient, IOP/PHP, hospitalisations (dates, reasons), ECT/TMS/ketamine."),
                _f("medication_trials", "Medication trials", "textarea",
                   help="Agent, maximum dose, duration, response, reason stopped, adverse effects."),
                _f("psychotherapy_history", "Psychotherapy history", "textarea"),
                _f("adherence", "Adherence history and barriers", "textarea"),
            ],
        },
        {
            "id": "substance",
            "title": "Substance Use",
            "help": "42 CFR Part 2 applies to this section when the practice is a federally assisted "
                    "SUD program. It is withheld from every outbound report unless the patient's "
                    "authorization names substance use content.",
            "fields": [
                _f("alcohol", "Alcohol", "textarea", sens="sud",
                   help="Quantity/frequency, heaviest use, withdrawal, blackouts, treatment."),
                _f("tobacco", "Tobacco / nicotine", "textarea", sens="sud"),
                _f("cannabis", "Cannabis", "textarea", sens="sud"),
                _f("stimulants_opioids", "Stimulants, opioids, other substances", "textarea", sens="sud"),
                _f("rx_misuse", "Misuse of prescribed / OTC medications or supplements", "textarea", sens="sud"),
                _f("sud_treatment", "Substance use treatment history", "textarea", sens="sud"),
                _f("tox_screen", "Toxicology / laboratory findings", "textarea", sens="sud"),
            ],
        },
        {
            "id": "medical",
            "title": "Medical History",
            "fields": [
                _f("medical_conditions", "Active medical conditions", "textarea"),
                _f("current_medications", "Current medications & doses (incl. OTC/supplements)", "textarea"),
                _f("allergies", "Allergies / adverse drug reactions", "text"),
                _f("surgical_neuro", "Surgical, neurological and head-injury history", "textarea"),
                _f("vitals_labs", "Vitals, metabolic monitoring, ECG, labs", "textarea",
                   help="Weight/BMI, BP, HR; for antipsychotics: lipids, HbA1c; for lithium: level, TSH, Cr; QTc."),
                _f("pregnancy", "Reproductive / pregnancy status and contraception", "textarea", sens="sexual"),
                _f("infectious", "Communicable disease status", "textarea", sens="hiv"),
                _f("ros", "Review of systems", "textarea"),
            ],
        },
        {
            "id": "family_social",
            "title": "Family, Developmental & Social History",
            "fields": [
                _f("family_psych_history", "Family psychiatric history", "textarea", sens="genetic",
                   help="Include completed suicide, psychiatric hospitalisation, and medication response in relatives."),
                _f("family_medical_history", "Family medical history", "textarea", sens="genetic"),
                _f("developmental", "Developmental history", "textarea"),
                _f("education_work", "Education and occupational history", "textarea"),
                _f("relationships", "Relationships, supports and living situation", "textarea"),
                _f("trauma_history", "Trauma and abuse history", "textarea", sens="trauma"),
                _f("sexual_history", "Sexual and reproductive history", "textarea", sens="sexual"),
                _f("legal", "Legal / forensic involvement", "textarea", sens="forensic"),
                _f("military", "Military service", "text"),
                _f("firearms_home", "Firearms or other lethal means in the home", "textarea", sens="risk"),
                _f("cultural", "Cultural, religious and identity factors", "textarea",
                   help="DSM-5-TR Cultural Formulation Interview domains: cultural identity, cultural "
                        "explanations of illness, stressors and supports, clinician-patient relationship."),
                _f("social_determinants", "Social determinants (housing, food, transport, insurance)", "textarea"),
                _f("strengths", "Patient strengths, goals and preferences", "textarea"),
            ],
        },
        MSE_SECTION,
        RISK_SECTION,
        MEASURES_SECTION,
        {
            "id": "function",
            "title": "Functional Assessment",
            "help": "Drives medical-necessity determinations and school/employer accommodation letters.",
            "fields": [
                _f("func_work_school", "Work / school functioning", "textarea"),
                _f("func_social", "Social and family functioning", "textarea"),
                _f("func_selfcare", "Self-care and activities of daily living", "textarea"),
                _f("func_cognitive", "Concentration, persistence and pace", "textarea"),
                _f("func_impact_summary", "Summary of functional impairment", "textarea"),
            ],
        },
        {
            "id": "formulation",
            "title": "Formulation, Diagnosis & Plan",
            "fields": [
                _f("formulation", "Biopsychosocial formulation", "textarea", req=True,
                   help="Predisposing, precipitating, perpetuating and protective factors."),
                _f("differential", "Differential diagnosis and reasoning", "textarea"),
                _f("dsm_diagnoses", "DSM-5-TR diagnoses with ICD-10-CM codes", "textarea", req=True,
                   help="One per line, e.g. 'F33.1 Major depressive disorder, recurrent, moderate'. "
                        "Avoid unspecified codes where a specific code is supportable."),
                _f("severity_specifiers", "Severity and course specifiers", "textarea"),
                _f("treatment_plan", "Treatment plan", "textarea", req=True,
                   help="Medication (agent, dose, target), psychotherapy modality and frequency, labs/monitoring, "
                        "referrals, measurable goals and review interval."),
                _f("informed_consent", "Informed consent discussion", "textarea",
                   help="Risks/benefits/alternatives discussed, including off-label use and black-box warnings."),
                _f("capacity", "Decision-making capacity", "select",
                   options=["Intact", "Partially impaired", "Impaired - surrogate involved"]),
                _f("prognosis", "Prognosis", "textarea"),
                _f("followup", "Follow-up interval", "text"),
                _f("process_note", "Clinician process note (not released)", "textarea", sens="process_note",
                   help="HIPAA psychotherapy-note content. Kept separate; excluded from every generated report."),
            ],
        },
    ],
}


FOLLOW_UP = {
    "id": "followup",
    "name": "Psychiatric Follow-Up / Progress Note",
    "cpt": "99213 + 90833",
    "description": "Interval visit. Merges into the patient record and updates the longitudinal picture.",
    "sections": [
        {
            "id": "encounter",
            "title": "Encounter Information",
            "fields": [
                _f("encounter_date", "Date of service", "date", req=True),
                _f("encounter_setting", "Setting", "select",
                   options=["Outpatient clinic", "Telepsychiatry", "Inpatient", "Emergency department"]),
                _f("encounter_duration", "Time spent (minutes)", "number"),
            ],
        },
        {
            "id": "interval",
            "title": "Interval History",
            "fields": [
                _f("interval_history", "Interval history since last visit", "textarea", req=True),
                _f("target_symptoms", "Target symptom response", "textarea"),
                _f("medication_current", "Current regimen and adherence", "textarea"),
                _f("side_effects", "Adverse effects / tolerability", "textarea"),
                _f("substance_interval", "Interval substance use", "textarea", sens="sud"),
                _f("psychosocial", "Psychosocial stressors and supports", "textarea"),
            ],
        },
        MSE_SECTION,
        RISK_SECTION,
        MEASURES_SECTION,
        {
            "id": "plan",
            "title": "Assessment & Plan",
            "fields": [
                _f("assessment", "Assessment", "textarea", req=True),
                _f("dsm_diagnoses", "Active diagnoses with ICD-10-CM codes", "textarea"),
                _f("treatment_plan", "Plan changes", "textarea", req=True),
                _f("monitoring", "Monitoring / labs ordered", "textarea"),
                _f("followup", "Follow-up interval", "text"),
                _f("process_note", "Clinician process note (not released)", "textarea", sens="process_note"),
            ],
        },
    ],
}


ASD_EVAL = {
    "id": "asd_eval",
    "name": "Autism Spectrum Diagnostic Evaluation",
    "cpt": "90791 + 96116/96130",
    "description": "Multi-source ASD evaluation: developmental history, standardised observation "
                   "(ADOS-2), caregiver interview (ADI-R), rating scales, and DSM-5-TR criteria.",
    "sections": [
        {
            "id": "encounter",
            "title": "Evaluation Information",
            "fields": [
                _f("encounter_date", "Date(s) of evaluation", "date", req=True),
                _f("referral_source", "Referral source and question", "textarea", req=True),
                _f("informants", "Informants (caregivers, teachers) and records reviewed", "textarea", req=True),
                _f("chronological_age", "Chronological age at evaluation", "text"),
            ],
        },
        {
            "id": "developmental",
            "title": "Developmental & Medical History",
            "help": "ADI-R domains: early development, language/communication, reciprocal social "
                    "interaction, restricted and repetitive behaviour.",
            "fields": [
                _f("prenatal_birth", "Prenatal, perinatal and neonatal history", "textarea"),
                _f("milestones", "Developmental milestones", "textarea",
                   help="Motor, babbling, first words, phrase speech; any loss of skills and age at loss."),
                _f("language_dev", "Language and communication development", "textarea"),
                _f("social_dev", "Early social development and play", "textarea"),
                _f("rrb_history", "History of restricted/repetitive behaviour and interests", "textarea"),
                _f("sensory_history", "Sensory reactivity history", "textarea"),
                _f("medical_history", "Medical history", "textarea",
                   help="Seizures, sleep, GI, feeding, hearing and vision screening results."),
                _f("genetic_workup", "Genetic and metabolic workup", "textarea", sens="genetic",
                   help="Chromosomal microarray, Fragile X, exome; results and date."),
                _f("family_history", "Family history of ASD, ID, or psychiatric conditions", "textarea", sens="genetic"),
                _f("school_history", "Educational history and current supports", "textarea",
                   help="Current IEP/504 status, services, classroom placement."),
            ],
        },
        {
            "id": "instruments",
            "title": "Standardised Instruments",
            "fields": [
                _f("ados_module", "ADOS-2 module administered", "select",
                   options=["Toddler Module", "Module 1", "Module 2", "Module 3", "Module 4", "Not administered"]),
                _f("ados_scores", "ADOS-2 domain totals and comparison score", "textarea",
                   help="SA total, RRB total, overall total, classification, comparison score (1-10) where applicable."),
                _f("ados_observations", "ADOS-2 behavioural observations", "textarea"),
                _f("adir", "ADI-R algorithm scores", "textarea",
                   help="Reciprocal social interaction, communication, RRB, abnormality evident before 36 months; cut-offs."),
                _f("rating_scales", "Rating scales", "textarea",
                   help="SRS-2, SCQ, CARS-2, ASRS, RAADS-R (adults) - raw/T scores and interpretation."),
                _f("cognitive", "Cognitive assessment", "textarea",
                   help="Instrument, indices, FSIQ or nonverbal estimate; note if untestable and why."),
                _f("language_assessment", "Speech-language assessment", "textarea"),
                _f("adaptive", "Adaptive functioning (Vineland-3 / ABAS-3)", "textarea"),
                _f("comorbid_screens", "Co-occurring condition screens (ADHD, anxiety, mood)", "textarea"),
            ],
        },
        {
            "id": "dsm_a",
            "title": "DSM-5-TR Criterion A - Social Communication & Interaction",
            "help": "All three A criteria must be met, currently or by history. Record supporting examples.",
            "fields": [
                _f("a1", "A1. Social-emotional reciprocity", "textarea", req=True),
                _f("a2", "A2. Nonverbal communicative behaviours", "textarea", req=True),
                _f("a3", "A3. Developing, maintaining and understanding relationships", "textarea", req=True),
                _f("a_met", "Criterion A met", "select", options=["Yes", "No", "Partially / subthreshold"], req=True),
            ],
        },
        {
            "id": "dsm_b",
            "title": "DSM-5-TR Criterion B - Restricted, Repetitive Behaviour",
            "help": "At least two of four required, currently or by history.",
            "fields": [
                _f("b1", "B1. Stereotyped or repetitive motor movements, use of objects, or speech", "textarea"),
                _f("b2", "B2. Insistence on sameness, inflexible routines, ritualised behaviour", "textarea"),
                _f("b3", "B3. Highly restricted, fixated interests", "textarea"),
                _f("b4", "B4. Hyper- or hyporeactivity to sensory input", "textarea"),
                _f("b_count", "Number of B criteria met", "select", options=["0", "1", "2", "3", "4"], req=True),
            ],
        },
        {
            "id": "dsm_cde",
            "title": "DSM-5-TR Criteria C-E, Severity & Specifiers",
            "fields": [
                _f("c_onset", "C. Symptoms present in the early developmental period", "textarea", req=True),
                _f("d_impairment", "D. Clinically significant impairment in current functioning", "textarea", req=True),
                _f("e_differential", "E. Not better explained by intellectual disability or global developmental delay",
                   "textarea", req=True),
                _f("severity_social", "Severity - social communication", "select",
                   options=["Level 1 - requiring support", "Level 2 - requiring substantial support",
                            "Level 3 - requiring very substantial support", "Not applicable"]),
                _f("severity_rrb", "Severity - restricted, repetitive behaviours", "select",
                   options=["Level 1 - requiring support", "Level 2 - requiring substantial support",
                            "Level 3 - requiring very substantial support", "Not applicable"]),
                _f("specifiers", "Specifiers", "multiselect",
                   options=["With accompanying intellectual impairment", "Without accompanying intellectual impairment",
                            "With accompanying language impairment", "Without accompanying language impairment",
                            "Associated with a known genetic or medical condition",
                            "Associated with a neurodevelopmental, mental or behavioural problem",
                            "With catatonia"]),
            ],
        },
        {
            "id": "formulation",
            "title": "Conclusions & Recommendations",
            "fields": [
                _f("differential", "Differential diagnosis considered and ruled out", "textarea", req=True,
                   help="Language disorder, social (pragmatic) communication disorder, intellectual disability, "
                        "ADHD, anxiety/selective mutism, attachment-related presentations, hearing impairment."),
                _f("dsm_diagnoses", "Diagnoses with ICD-10-CM codes", "textarea", req=True,
                   help="e.g. 'F84.0 Autism spectrum disorder, requiring support (Level 1) for social communication'."),
                _f("summary", "Integrated summary", "textarea", req=True),
                _f("recommendations_clinical", "Clinical recommendations", "textarea", req=True),
                _f("recommendations_school", "Educational recommendations and accommodations", "textarea",
                   help="Written for a school team: environment, instruction, communication, sensory, "
                        "social, behaviour supports, and evaluation needs."),
                _f("recommendations_family", "Family / caregiver guidance", "textarea"),
                _f("strengths", "Strengths and interests", "textarea"),
                _f("reassessment", "Re-assessment interval", "text"),
                _f("process_note", "Clinician process note (not released)", "textarea", sens="process_note"),
            ],
        },
    ],
}


ADHD_EVAL = {
    "id": "adhd_eval",
    "name": "ADHD Diagnostic Evaluation",
    "cpt": "90791 + 96127",
    "description": "DSM-5-TR ADHD evaluation with cross-setting rating scales and rule-outs.",
    "sections": [
        {
            "id": "encounter",
            "title": "Evaluation Information",
            "fields": [
                _f("encounter_date", "Date of evaluation", "date", req=True),
                _f("referral_source", "Referral source and question", "textarea"),
                _f("informants", "Informants and records reviewed", "textarea", req=True,
                   help="DSM-5 requires evidence from two or more settings; name the reporters."),
            ],
        },
        {
            "id": "criteria",
            "title": "DSM-5-TR Criteria",
            "fields": [
                _f("inattentive_count", "Inattentive symptoms endorsed (of 9)", "number", req=True),
                _f("inattentive_detail", "Inattentive symptom examples", "textarea"),
                _f("hyperactive_count", "Hyperactive-impulsive symptoms endorsed (of 9)", "number", req=True),
                _f("hyperactive_detail", "Hyperactive-impulsive symptom examples", "textarea"),
                _f("onset_before_12", "Several symptoms present before age 12", "select",
                   options=["Yes", "No", "Unable to determine"], req=True),
                _f("two_settings", "Symptoms present in two or more settings", "select",
                   options=["Yes", "No"], req=True),
                _f("impairment", "Interference with functioning", "textarea", req=True),
                _f("not_better_explained", "Not better explained by another disorder", "textarea", req=True),
                _f("presentation", "Presentation", "select",
                   options=["Predominantly inattentive", "Predominantly hyperactive-impulsive", "Combined",
                            "Other specified", "Criteria not met"], req=True),
                _f("severity", "Severity", "select", options=["Mild", "Moderate", "Severe"]),
            ],
        },
        {
            "id": "instruments",
            "title": "Rating Scales & Testing",
            "fields": [
                _f("vanderbilt", "Vanderbilt (parent / teacher) results", "textarea"),
                _f("conners", "Conners-4 / CAARS results", "textarea"),
                _f("asrs", "ASRS-5 (adult) result", "textarea"),
                _f("cognitive_testing", "Cognitive / continuous performance testing", "textarea"),
                _f("academic", "Academic achievement and learning-disorder screening", "textarea"),
            ],
        },
        {
            "id": "medical",
            "title": "Medical & Risk Screening",
            "fields": [
                _f("medical_history", "Medical history", "textarea",
                   help="Sleep disorder, thyroid, anaemia, hearing/vision, head injury, seizure."),
                _f("cardiac_screen", "Cardiac history and family history of sudden death", "textarea", sens="genetic",
                   help="Required before stimulant initiation."),
                _f("substance_screen", "Substance use screening and diversion risk", "textarea", sens="sud"),
                _f("baseline_vitals", "Baseline height, weight, BP, HR", "textarea"),
            ],
        },
        MEASURES_SECTION,
        {
            "id": "formulation",
            "title": "Conclusions & Plan",
            "fields": [
                _f("differential", "Differential diagnosis", "textarea", req=True),
                _f("dsm_diagnoses", "Diagnoses with ICD-10-CM codes", "textarea", req=True),
                _f("summary", "Integrated summary", "textarea", req=True),
                _f("treatment_plan", "Treatment plan", "textarea", req=True),
                _f("recommendations_school", "School / workplace accommodations", "textarea"),
                _f("monitoring", "Monitoring plan", "textarea",
                   help="Growth, BP/HR, sleep, appetite, symptom scales at each titration step."),
                _f("process_note", "Clinician process note (not released)", "textarea", sens="process_note"),
            ],
        },
    ],
}


FORMS = {f["id"]: f for f in (ADULT_INITIAL, FOLLOW_UP, ASD_EVAL, ADHD_EVAL)}


def field_index(form_id: str) -> dict:
    """field_id -> field spec (with section metadata attached)."""
    form = FORMS[form_id]
    idx = {}
    for section in form["sections"]:
        for field in section["fields"]:
            item = dict(field)
            item["section_id"] = section["id"]
            item["section_title"] = section["title"]
            idx[field["id"]] = item
    return idx


ALL_FIELDS = {}
for _fid, _form in FORMS.items():
    for _f_id, _spec in field_index(_fid).items():
        ALL_FIELDS.setdefault(_f_id, _spec)


def sensitivity_of(field_id: str) -> str:
    spec = ALL_FIELDS.get(field_id)
    return spec["sens"] if spec else "general"


def label_of(field_id: str) -> str:
    spec = ALL_FIELDS.get(field_id)
    return spec["label"] if spec else field_id.replace("_", " ").title()


def required_fields(form_id: str) -> list:
    return [f["id"] for f in field_index(form_id).values() if f.get("req")]

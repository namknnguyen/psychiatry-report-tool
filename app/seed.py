"""Demonstration data.

Fictional patients written to exercise every template and every compliance
control: an adult with two visits, a child autism evaluation, an adult ADHD
evaluation, and a complex case carrying 42 CFR Part 2 substance use content
and elevated risk.  No real patient information appears here.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from . import audit, auth
from .db import Store, now


def _d(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


PATIENTS = [
    {
        "mrn": "MRN-00101",
        "tags": ["Mood disorders", "Telepsychiatry"],
        "demographics": {
            "first_name": "Maya", "last_name": "Ellison", "preferred_name": "Maya",
            "dob": "1991-04-18", "pronouns": "she/her", "sex_at_birth": "Female",
            "gender_identity": "Woman", "phone": "(555) 233-8890",
            "email": "m.ellison@example.com", "address": "44 Corliss Ave, Springfield",
            "preferred_language": "English",
            "emergency_contact": {"name": "Rosa Ellison (mother)", "phone": "(555) 233-8871"},
            "insurance": {"carrier": "Northstar Health", "member_id": "NH-4471902", "group_number": "GRP-88120"},
            "pcp": "Dr. A. Feld, Springfield Family Medicine",
        },
        "evaluations": [
            {"form_id": "adult_initial", "encounter_date": _d(52), "sign": True, "answers": {
                "encounter_date": _d(52),
                "encounter_setting": "Outpatient clinic",
                "encounter_duration": "60",
                "informants": "Patient (primary, reliable historian). Records from Springfield Family "
                              "Medicine reviewed with consent, including 2024 PHQ-9 scores and thyroid studies.",
                "interpreter": "No",
                "chief_complaint": "I can't get out of bed most mornings and I'm behind at work again.",
                "hpi": "Ms. Ellison is a 34-year-old marketing analyst presenting with a four-month "
                       "worsening of depressed mood, anhedonia and fatigue, on a background of two prior "
                       "depressive episodes at ages 22 and 28. The current episode began after a team "
                       "restructure in which she lost a project she had led for two years. She describes "
                       "low mood present most of the day, nearly every day, with loss of interest in "
                       "running and in seeing friends, initial insomnia with a two-hour sleep latency, "
                       "early morning waking at 04:30, appetite reduction with a 6 kg unintentional weight "
                       "loss, poor concentration, and guilt centred on 'letting the team down'. She "
                       "reports passive thoughts that she would not mind not waking up, without plan or "
                       "intent. Energy is lowest in the morning and improves slightly by evening. She has "
                       "tried increasing exercise and reducing caffeine without benefit.",
                "symptom_review": "Anxiety: prominent worry about job security with muscle tension and "
                                  "restlessness, present most days for six months. No panic attacks. "
                                  "No obsessions or compulsions. No history of manic or hypomanic "
                                  "symptoms on careful review, including no decreased need for sleep with "
                                  "increased goal-directed activity. No psychotic symptoms. No binge "
                                  "eating or purging. Negative for trauma-related re-experiencing.",
                "sleep": "Sleep latency ~2 hours, early morning waking at 04:30, total sleep 4-5 hours. "
                         "No snoring or witnessed apnoea. Uses phone in bed.",
                "appetite_weight": "Appetite reduced; 6 kg unintentional loss over four months. "
                                   "Current weight 61 kg, BMI 21.4.",
                "prior_diagnoses": "Major depressive disorder, recurrent (diagnosed 2013).",
                "prior_treatment": "Two prior outpatient episodes of care. No psychiatric "
                                   "hospitalisation, no ECT or TMS, no emergency department visits for "
                                   "psychiatric reasons.",
                "medication_trials": "Sertraline 50 mg daily (2013-2014): partial response, stopped when "
                                     "she felt well. Sertraline 100 mg daily (2019-2020): good response "
                                     "over 10 weeks, discontinued by mutual agreement after 12 months. "
                                     "Bupropion XL 150 mg (2020, 3 weeks): stopped for jitteriness and "
                                     "worsened sleep.",
                "psychotherapy_history": "Twelve sessions of CBT in 2019 with a good response; found "
                                         "behavioural activation and thought records most useful.",
                "adherence": "Good adherence historically. Concerned about weight change and sexual side "
                             "effects influencing her willingness to continue medication.",
                "alcohol": "2-3 glasses of wine on Friday and Saturday, unchanged over years. No morning "
                           "drinking, no withdrawal, no blackouts. AUDIT-C 3.",
                "tobacco": "Never smoked. No vaping.",
                "cannabis": "None in the last 5 years.",
                "stimulants_opioids": "No use of stimulants, opioids or other substances.",
                "rx_misuse": "No misuse of prescribed or over-the-counter medication or supplements.",
                "medical_conditions": "Iron deficiency anaemia (2022, resolved with supplementation). "
                                      "No thyroid, cardiac or neurological disease.",
                "current_medications": "Cetirizine 10 mg as needed for seasonal allergy. Combined oral "
                                       "contraceptive. Ferrous sulfate stopped 2023.",
                "allergies": "No known drug allergies.",
                "surgical_neuro": "Appendectomy 2011. No head injury, no seizures.",
                "vitals_labs": "BP 112/70, HR 68, weight 61 kg, BMI 21.4. TSH 1.8 mIU/L, CBC normal, "
                               "ferritin 42 ng/mL, B12 normal (all within the last 6 weeks).",
                "ros": "Negative except as above. No chest pain, palpitations, tremor or heat intolerance.",
                "family_psych_history": "Mother with recurrent depression, responded well to sertraline. "
                                        "Maternal uncle died by suicide at age 41. No known bipolar "
                                        "disorder or psychosis in the family.",
                "developmental": "Unremarkable developmental history; met milestones on time.",
                "education_work": "Bachelor's degree in communications. Marketing analyst for six years "
                                  "at the same firm; two promotions; currently on a performance "
                                  "improvement plan begun six weeks ago.",
                "relationships": "Lives with a long-term partner of five years, described as supportive. "
                                 "Close to her mother, who lives nearby. Two close friends she has been "
                                 "avoiding for two months.",
                "trauma_history": "No history of childhood abuse or neglect. Witnessed a serious motor "
                                  "vehicle collision at age 19 with brief distress that resolved without "
                                  "treatment.",
                "legal": "No legal involvement.",
                "cultural": "Second-generation, identifies strongly with her family's Portuguese "
                            "heritage. Explains her symptoms as 'burnout' and initially found the idea "
                            "of a psychiatric diagnosis shaming; this eased during the interview. Family "
                            "is a source of support and of pressure to appear well.",
                "social_determinants": "Stable housing, employer-sponsored insurance, reliable transport. "
                                       "Food secure.",
                "strengths": "Insightful, articulate about her own patterns, has responded well to "
                             "treatment before, strong partner and family support, motivated to return "
                             "to running.",
                "firearms_home": "No firearms in the home; none accessible elsewhere.",
                "mse_appearance": "Well-groomed woman appearing her stated age, casually dressed, "
                                  "cooperative, with reduced spontaneous eye contact.",
                "mse_attitude": "Cooperative",
                "mse_motor": "Psychomotor retardation",
                "mse_speech": "Reduced rate and volume, increased latency, normal prosody.",
                "mse_mood": "\"Flat and worn out\"",
                "mse_affect": "Constricted range, dysphoric, reactive to a brief moment of humour, "
                              "congruent with stated mood.",
                "mse_thought_process": "Linear and goal-directed",
                "mse_thought_content": "Preoccupied with job performance and being a burden. No "
                                       "delusions, no ideas of reference.",
                "mse_perception": "No hallucinations in any modality. No dissociative symptoms.",
                "mse_cognition": "Alert and oriented x4. Attention mildly reduced; serial sevens with two "
                                 "self-corrected errors. Registration 3/3, recall 2/3 at five minutes. "
                                 "Language and abstraction intact. MoCA not indicated.",
                "mse_insight": "Good",
                "mse_judgment": "Fair",
                "si_ideation": "Passive (wish to be dead)",
                "si_plan": "No plan. Has not researched methods, made no preparatory acts.",
                "si_intent": "None",
                "si_means": "No firearms in the home. Medication supply limited to a 30-day quantity by "
                            "agreement. Means restriction discussed with the patient and her partner.",
                "si_history": "No prior suicide attempts, no non-suicidal self-injury.",
                "hi_ideation": "None",
                "protective": "Strong therapeutic alliance, supportive partner and mother, prior "
                              "treatment response, future-oriented goals, care of a dog, no access to "
                              "firearms, states that her family is the reason she would never act.",
                "risk_level": "Low",
                "risk_rationale": "Passive ideation without plan or intent, no prior attempts, no "
                                  "substance misuse, no access to firearms, strong protective factors and "
                                  "engagement with care. Chronic risk is modestly elevated by family "
                                  "history of suicide and recurrent depression; acute risk is low.",
                "safety_plan": "Warning signs: waking before 05:00 with dread, cancelling plans two days "
                               "running. Internal coping: 20-minute walk, box breathing, shower. Social "
                               "contacts: partner Ana, mother Rosa. Professional contacts: clinic line "
                               "during hours, 988 after hours. Means: 30-day medication supply held by "
                               "her partner during the titration period.",
                "phq9": "18", "gad7": "13", "cssrs": "Positive for passive ideation, negative for "
                                                     "intent, plan or behaviour",
                "audit_c": "3", "dast10": "0", "mdq": "Negative", "pcl5": "8",
                "func_work_school": "Missing two to three deadlines per week; placed on a performance "
                                    "improvement plan six weeks ago. Takes twice as long to complete "
                                    "routine analyses. Has used four sick days in six weeks.",
                "func_social": "Withdrawn from friends for two months; declines invitations. Relationship "
                               "with partner strained by irritability but intact.",
                "func_selfcare": "Showering every second day. Cooking has stopped; relies on delivery. "
                                 "Stopped running, which had been four times weekly.",
                "func_cognitive": "Concentration reduced; loses the thread in meetings and rereads emails "
                                  "three or four times. Reports her pace is roughly half of baseline.",
                "func_impact_summary": "Moderate impairment across occupational, social and self-care "
                                       "domains, with objective corroboration from an employer "
                                       "performance plan and documented absences.",
                "formulation": "A 34-year-old woman with recurrent major depressive disorder presenting "
                               "with a third moderate-to-severe episode. Predisposing: family history of "
                               "depression and completed suicide, two prior episodes, perfectionistic "
                               "cognitive style. Precipitating: workplace restructure with loss of role "
                               "and status. Perpetuating: sleep disruption, withdrawal from exercise and "
                               "friendships, rumination about performance, ongoing performance plan. "
                               "Protective: prior treatment response, supportive partner and mother, "
                               "insight, no substance misuse, absence of firearms.",
                "differential": "Considered and excluded: bipolar disorder (no history of hypomania or "
                                "mania on careful review; MDQ negative), depression due to hypothyroidism "
                                "or anaemia (recent TSH, CBC and ferritin normal), adjustment disorder "
                                "(symptom count, duration and severity exceed the threshold), persistent "
                                "depressive disorder (episodes are discrete with full inter-episode "
                                "recovery), substance-induced mood disorder (AUDIT-C 3, no other use).",
                "dsm_diagnoses": "F33.1 Major depressive disorder, recurrent episode, moderate\n"
                                 "F41.1 Generalized anxiety disorder",
                "severity_specifiers": "Moderate severity, with anxious distress. Third lifetime episode.",
                "treatment_plan": "1. Sertraline 50 mg daily for one week, then 100 mg daily, targeting "
                                  "the dose that produced remission in 2019; review response at four "
                                  "weeks with repeat PHQ-9 and GAD-7.\n"
                                  "2. Referral for CBT, weekly, with behavioural activation as the "
                                  "initial focus.\n"
                                  "3. Sleep: consistent wake time, no phone in bed, morning light "
                                  "exposure, resume running three times weekly at a reduced target.\n"
                                  "4. Safety plan reviewed and given in writing; means restriction "
                                  "agreed with her partner.\n"
                                  "5. Return in two weeks, sooner if symptoms worsen or ideation changes.",
                "informed_consent": "Discussed the rationale for an SSRI, the expected two- to four-week "
                                    "onset, common adverse effects (nausea, sleep change, sexual side "
                                    "effects), the FDA boxed warning regarding suicidality in adults "
                                    "under 25 and the need to report any worsening or new ideation, "
                                    "serotonin syndrome, discontinuation symptoms, and the alternatives "
                                    "of psychotherapy alone or a different antidepressant class. "
                                    "Questions answered; patient consented.",
                "capacity": "Intact",
                "prognosis": "Good. Two prior episodes have remitted with an SSRI and CBT; the current "
                             "episode is of moderate severity with strong supports.",
                "followup": "2 weeks",
                "process_note": "Hypothesis to hold lightly: the performance plan may be functioning as "
                                "a repetition of a childhood dynamic around achievement and her mother's "
                                "approval. Not raised today - too early, and she was tearful.",
            }},
            {"form_id": "followup", "encounter_date": _d(24), "sign": True, "answers": {
                "encounter_date": _d(24),
                "encounter_setting": "Telepsychiatry",
                "encounter_duration": "25",
                "interval_history": "Four weeks on sertraline, now 100 mg daily for three weeks. Reports "
                                    "the mornings are 'less heavy' and she has resumed running twice "
                                    "weekly. Sleep latency down to about 40 minutes; early waking now "
                                    "05:45 rather than 04:30. Returned to two social engagements. Still "
                                    "behind at work but no missed deadlines in the last ten days. Weight "
                                    "stable, up 1 kg.",
                "target_symptoms": "Mood improved; anhedonia partially improved (running restarted, still "
                                   "little pleasure in it). Concentration improved but not at baseline. "
                                   "Guilt reduced.",
                "medication_current": "Sertraline 100 mg daily, taken each morning. Adherence complete by "
                                      "self-report and pill count.",
                "side_effects": "Mild nausea in week one, resolved. Delayed orgasm, present and bothersome "
                                "but she wishes to continue for now; options discussed.",
                "substance_interval": "Unchanged: two glasses of wine on Saturday only.",
                "psychosocial": "Performance improvement plan continues, with a review in three weeks. "
                                "Partner attended the last ten minutes of the visit at her request.",
                "mse_appearance": "Neatly dressed, appears at ease on camera, good eye contact.",
                "mse_attitude": "Cooperative", "mse_motor": "Normal",
                "mse_speech": "Normal rate, rhythm and volume.",
                "mse_mood": "\"Better - maybe sixty percent\"",
                "mse_affect": "Fuller range, brighter, reactive, congruent.",
                "mse_thought_process": "Linear and goal-directed",
                "mse_thought_content": "No preoccupations. No delusions.",
                "mse_perception": "No perceptual disturbance.",
                "mse_cognition": "Alert, oriented, attention improved; serial sevens without error.",
                "mse_insight": "Good", "mse_judgment": "Good",
                "si_ideation": "None", "si_intent": "None",
                "si_means": "No firearms. Partner continues to hold the medication supply; agreed to "
                            "return it to her at the next visit if stability continues.",
                "hi_ideation": "None",
                "protective": "Improving function, partner involvement, treatment response, return to "
                              "exercise.",
                "risk_level": "Low",
                "risk_rationale": "No current ideation, improving symptoms and function, intact supports "
                                  "and no access to firearms.",
                "safety_plan": "Existing plan reviewed and unchanged; she was able to recall all five "
                               "steps without prompting.",
                "phq9": "11", "gad7": "8",
                "assessment": "Partial response to sertraline 100 mg at week four, with improvement in "
                              "mood, sleep and function and full resolution of passive suicidal ideation. "
                              "PHQ-9 has fallen from 18 to 11 and GAD-7 from 13 to 8. Residual anhedonia, "
                              "concentration difficulty and sexual side effects.",
                "dsm_diagnoses": "F33.1 Major depressive disorder, recurrent episode, moderate\n"
                                 "F41.1 Generalized anxiety disorder",
                "treatment_plan": "Continue sertraline 100 mg daily for a further four weeks before "
                                  "considering an increase to 150 mg, given the trajectory of response. "
                                  "CBT started last week; continue weekly. Sexual side effects: watchful "
                                  "waiting for now, with dose timing and augmentation options discussed "
                                  "for the next visit if unchanged. Repeat PHQ-9 and GAD-7 at each visit.",
                "monitoring": "PHQ-9, GAD-7 each visit. Weight at each visit. No laboratory monitoring "
                              "indicated for sertraline in the absence of new symptoms.",
                "followup": "4 weeks",
            }},
        ],
        "authorizations": [
            {"recipient_name": "Rosa Ellison (mother)", "recipient_type": "Family member or caregiver",
             "scopes": [], "purpose": "Support person involved in care at the patient's request",
             "signed_date": _d(50), "expires_date": _d(-315)},
        ],
    },
    {
        "mrn": "MRN-00102",
        "tags": ["Neurodevelopmental", "Paediatric", "School liaison"],
        "demographics": {
            "first_name": "Daniel", "last_name": "Okafor", "preferred_name": "Danny",
            "dob": "2018-02-09", "pronouns": "he/him", "sex_at_birth": "Male",
            "phone": "(555) 771-2204", "email": "j.okafor@example.com",
            "address": "9 Marlin Court, Springfield", "preferred_language": "English",
            "guardian": {"name": "Joy Okafor (mother)", "relationship": "Mother", "phone": "(555) 771-2204"},
            "emergency_contact": {"name": "Joy Okafor", "phone": "(555) 771-2204"},
            "insurance": {"carrier": "Statewide Children's Plan", "member_id": "SC-7719044",
                          "group_number": "GRP-3320"},
            "school": "Brookline Elementary, 2nd grade",
            "language_preference": "person-first",
        },
        "evaluations": [
            {"form_id": "asd_eval", "encounter_date": _d(31), "sign": True, "answers": {
                "encounter_date": _d(31),
                "referral_source": "Referred by Dr. Lena Ortiz, paediatrics, at the request of Danny's "
                                   "mother and his 2nd-grade teacher, for evaluation of social "
                                   "communication difficulties, repetitive behaviour and difficulty with "
                                   "transitions in the classroom.",
                "informants": "Mother (Joy Okafor), primary informant across two sessions. Classroom "
                              "teacher questionnaire and a 45-minute classroom observation. School "
                              "records including the 1st-grade progress reports. Paediatric records "
                              "including hearing screening (passed, 6 months ago) and vision screening "
                              "(normal).",
                "chronological_age": "8 years 2 months",
                "prenatal_birth": "Full-term spontaneous vaginal delivery at 39 weeks. No prenatal "
                                  "exposures. Birth weight 3.4 kg. No neonatal intensive care.",
                "milestones": "Sat at 6 months, walked at 13 months. Babbled on time. First words at 14 "
                              "months, then a plateau: mother recalls he had about 10 words at 18 months "
                              "and no new words until 26 months. Phrase speech at 3 years 2 months. No "
                              "loss of previously acquired skills.",
                "language_dev": "Currently speaks in full sentences with a large vocabulary, "
                                "particularly for topics of interest. Pronoun reversal until age 5. "
                                "Delayed echolalia of film dialogue persists, used both playfully and "
                                "under stress. Conversation is largely one-directional.",
                "social_dev": "Limited spontaneous showing or sharing of objects as a toddler; brought "
                              "items to his mother for help but rarely to share interest. Preferred "
                              "parallel play until age 6. Now seeks out peers but directs play rigidly "
                              "and does not adapt when others lose interest. One reciprocal friendship "
                              "with a cousin who accommodates him.",
                "rrb_history": "Lining up vehicles by size from age 3, with distress when disturbed. "
                               "Hand-flapping when excited, present since age 3 and ongoing. Intense "
                               "interest in subway systems since age 5, with encyclopaedic knowledge of "
                               "the city network; conversation returns to it repeatedly.",
                "sensory_history": "Covers ears for hand dryers, fire drills and the cafeteria. Strong "
                                   "preference for soft waistbands, removes tags. Seeks deep pressure, "
                                   "asks to be squeezed between cushions. High pain threshold noted after "
                                   "a fall that required stitches.",
                "medical_history": "No seizures. Sleep onset difficulty most nights, taking 60-90 "
                                   "minutes; melatonin used intermittently with partial benefit. "
                                   "Constipation managed with diet. Selective eating with a repertoire of "
                                   "roughly 12 foods, no weight faltering. Hearing and vision screening "
                                   "both normal in the last year.",
                "genetic_workup": "Chromosomal microarray performed 4 months ago: normal. Fragile X "
                                  "testing: negative. No further genetic testing indicated at present.",
                "family_history": "Maternal cousin with an autism diagnosis. Father describes himself as "
                                  "'a quiet engineer type' with no diagnosis. No intellectual disability "
                                  "or psychosis in the family.",
                "school_history": "Currently in a general education 2nd-grade classroom with no formal "
                                  "supports. Reading is a relative strength (above grade level for "
                                  "decoding). Written expression is a weakness. Two incidents this term "
                                  "of leaving the classroom during fire drills. No IEP or 504 plan in "
                                  "place; the school suggested the family seek an evaluation.",
                "ados_module": "Module 3",
                "ados_scores": "ADOS-2 Module 3 administered. Social Affect total 11, Restricted and "
                               "Repetitive Behaviour total 4, Overall total 15, exceeding the autism "
                               "spectrum cut-off of 7 and the autism cut-off of 9. Comparison score 7 of "
                               "10, indicating a moderate level of autism-related symptoms relative to "
                               "same-age children with ASD.",
                "ados_observations": "Danny made limited and fleeting eye contact, which was not well "
                                     "integrated with speech or gesture. He described the subway network "
                                     "in extended monologue and did not adjust when the examiner showed "
                                     "reduced interest. He used few descriptive gestures. He showed "
                                     "clear enjoyment in a shared bubble activity but did not direct "
                                     "facial expression toward the examiner to share it. Hand-flapping "
                                     "was observed twice at moments of excitement. In the story task he "
                                     "described events accurately but offered no account of the "
                                     "characters' motivations.",
                "adir": "ADI-R administered with mother. Reciprocal social interaction 17 (cut-off 10); "
                        "communication, verbal 13 (cut-off 8); restricted, repetitive and stereotyped "
                        "behaviour 6 (cut-off 3); abnormality evident before 36 months, 3 (cut-off 1). "
                        "All four domains exceed the diagnostic algorithm cut-offs.",
                "rating_scales": "SRS-2 parent form: total T-score 74 (severe range), with Social "
                                 "Communication T 72 and Restricted Interests and Repetitive Behaviour T "
                                 "76. SRS-2 teacher form: total T-score 68 (moderate range). SCQ "
                                 "Lifetime: 19 (cut-off 15).",
                "cognitive": "WISC-V administered. Full Scale IQ 104. Verbal Comprehension 108, Visual "
                             "Spatial 112, Fluid Reasoning 106, Working Memory 91, Processing Speed 85. "
                             "The profile shows intact general reasoning with relative weakness in "
                             "working memory and processing speed.",
                "language_assessment": "CELF-5 core language score 98. Pragmatic language profile "
                                       "markedly below structural language: difficulty with topic "
                                       "maintenance, perspective-taking in conversation, and "
                                       "interpreting non-literal language.",
                "adaptive": "Vineland-3 parent interview: Adaptive Behaviour Composite 78 (low). "
                            "Communication 84, Daily Living Skills 82, Socialisation 71. The 26-point "
                            "gap between cognitive ability and socialisation is clinically significant.",
                "comorbid_screens": "Conners-4 parent and teacher forms elevated on inattention "
                                    "(T 68 and T 66) but not hyperactivity. Screening for anxiety (SCARED "
                                    "parent) elevated for separation and school avoidance subscales. "
                                    "These will be reassessed once supports are in place, as inattention "
                                    "in this context may be secondary to sensory and social load.",
                "a1": "Reduced social-emotional reciprocity. On the ADOS-2 he engaged in extended "
                      "one-sided monologue about subway systems and did not modify it in response to the "
                      "examiner's reduced interest. His mother reports he rarely asks others about "
                      "themselves and does not spontaneously share news of his day. He responds to "
                      "direct questions but does not sustain back-and-forth exchange beyond two turns "
                      "outside his areas of interest.",
                "a2": "Deficits in nonverbal communicative behaviour. Eye contact is present but brief "
                      "and poorly integrated with speech. Descriptive gestures are rare. Facial "
                      "expression is often not directed to a partner even during clear enjoyment, as "
                      "observed in the bubble activity. Personal space is not well calibrated; he stands "
                      "close to unfamiliar adults.",
                "a3": "Difficulty developing, maintaining and understanding relationships. He wants "
                      "friends and approaches peers, but directs play rigidly to his own script and does "
                      "not adjust when peers disengage. He has one reciprocal friendship, with a cousin "
                      "who accommodates his preferences. The classroom observation showed him playing "
                      "adjacent to, rather than with, a group of three boys for the full recess period.",
                "a_met": "Yes",
                "b1": "Hand-flapping at moments of excitement, observed twice during the ADOS-2 and "
                      "reported since age 3. Delayed echolalia of film dialogue, used under stress. "
                      "Lining up vehicles by size, present since age 3.",
                "b2": "Insistence on sameness: distress if the route to school changes, if his cars are "
                      "moved, or if the classroom schedule is altered. Two incidents this term of "
                      "leaving the classroom during unannounced fire drills. Requires advance warning "
                      "for transitions.",
                "b3": "Highly restricted and fixated interest in subway systems since age 5, unusual in "
                      "intensity, dominating conversation and free play.",
                "b4": "Hyperreactivity to auditory input (hand dryers, fire alarms, cafeteria noise) and "
                      "to clothing texture; sensory seeking for deep pressure; reduced pain reactivity.",
                "b_count": "4",
                "c_onset": "Symptoms were present in the early developmental period. Language plateau at "
                           "18 months, lining up of objects and hand-flapping from age 3, and parallel "
                           "play persisting to age 6. ADI-R 'abnormality evident before 36 months' score "
                           "of 3 exceeds the cut-off of 1.",
                "d_impairment": "Clinically significant impairment in social and educational "
                                "functioning. Vineland-3 socialisation standard score of 71 sits 33 "
                                "points below his Full Scale IQ of 104. He is not accessing peer "
                                "relationships at recess, has left the classroom twice during "
                                "unannounced drills, and written expression is significantly below the "
                                "level his reading and reasoning would predict.",
                "e_differential": "Not better explained by intellectual disability or global "
                                  "developmental delay. Full Scale IQ is 104 and structural language is "
                                  "age-appropriate (CELF-5 core 98); the social communication deficits "
                                  "are disproportionate to his overall developmental level.",
                "severity_social": "Level 1 - requiring support",
                "severity_rrb": "Level 2 - requiring substantial support",
                "specifiers": "Without accompanying intellectual impairment, Without accompanying "
                              "language impairment",
                "differential": "Social (pragmatic) communication disorder was considered and excluded by "
                                "the presence of four restricted and repetitive behaviour criteria. "
                                "Language disorder excluded: structural language is within normal limits. "
                                "Intellectual disability excluded: FSIQ 104 with adaptive weakness "
                                "specific to socialisation. ADHD symptoms are present and elevated on "
                                "Conners-4 but are better accounted for at this stage by sensory and "
                                "social load; this will be re-examined in six months once supports are "
                                "in place. Hearing impairment excluded by a normal screen. Anxiety is "
                                "present and likely secondary; selective mutism was excluded as speech "
                                "is unrestricted across settings.",
                "dsm_diagnoses": "F84.0 Autism spectrum disorder, without accompanying intellectual "
                                 "impairment, without accompanying language impairment; requiring "
                                 "support (Level 1) for social communication and substantial support "
                                 "(Level 2) for restricted, repetitive behaviours",
                "summary": "Danny is an 8-year-old boy of average cognitive ability who meets DSM-5-TR "
                           "criteria for autism spectrum disorder. Findings converged across a "
                           "standardised observation (ADOS-2 Module 3, overall total 15, comparison "
                           "score 7), a structured caregiver interview (ADI-R, all four domains above "
                           "cut-off), parent and teacher rating scales, direct classroom observation and "
                           "developmental history. His difficulties are concentrated in social "
                           "reciprocity, nonverbal communication, flexibility and sensory regulation, "
                           "against a background of strong verbal reasoning and reading. The gap between "
                           "his cognitive ability and his adaptive socialisation score is the clearest "
                           "signal that he needs support rather than higher expectations.",
                "recommendations_clinical": "1. Speech-language therapy targeting pragmatic language, "
                                            "twice monthly, with a focus on conversational repair and "
                                            "perspective-taking.\n"
                                            "2. Occupational therapy assessment for sensory regulation "
                                            "and a written sensory plan shared with the school.\n"
                                            "3. Parent-mediated intervention: an 8-session caregiver "
                                            "programme focused on transitions and predictability.\n"
                                            "4. Sleep: behavioural sleep plan first; melatonin only as a "
                                            "time-limited adjunct with paediatric oversight.\n"
                                            "5. No indication for psychotropic medication at this time.\n"
                                            "6. Re-screen for ADHD and anxiety in six months once "
                                            "supports are established.",
                "recommendations_school": "Predictability: a visual daily schedule at his desk, and "
                                          "advance warning of any change to routine, including at least "
                                          "one minute of notice before fire drills where possible, with "
                                          "a pre-agreed exit plan and a named adult.\n"
                                          "Sensory: access to ear defenders in the cafeteria and during "
                                          "assemblies; permission to leave a noisy environment to a "
                                          "designated quiet space without requesting permission each "
                                          "time; seating away from the hand dryers and the doorway.\n"
                                          "Communication: allow extra processing time after instructions "
                                          "(count to ten before repeating); check comprehension by asking "
                                          "him to restate rather than asking whether he understands; use "
                                          "literal language and explain idioms.\n"
                                          "Social: an adult-facilitated structured lunch club twice "
                                          "weekly built around a shared activity rather than free "
                                          "conversation; peer buddy for unstructured times.\n"
                                          "Academic: scribe or keyboard access for extended writing; "
                                          "break multi-step written tasks into numbered steps; use his "
                                          "interest in transit systems as a bridge for engagement in "
                                          "writing and mathematics.\n"
                                          "Behaviour: interpret leaving the room during a drill as "
                                          "sensory escape rather than defiance, and respond with the "
                                          "agreed exit plan rather than a disciplinary consequence.\n"
                                          "Evaluation: consider a school-based occupational therapy "
                                          "evaluation and a written expression assessment.",
                "recommendations_family": "Keep routines predictable and give advance notice of change. "
                                          "Use his subway interest as a way in rather than something to "
                                          "limit. Prepare him for new places with photographs beforehand. "
                                          "Expect more difficulty at the end of a school day, when his "
                                          "capacity for social effort is spent.",
                "strengths": "Excellent visual-spatial reasoning and decoding, an extraordinary memory "
                             "for systems and maps, honesty, persistence with problems that interest "
                             "him, and genuine warmth with familiar adults.",
                "reassessment": "12 months, or sooner if the school team requests input",
                "adjustments_made": "Appointments booked first of the day to avoid a waiting room; "
                                    "overhead lights off and a lamp used instead; same room and same "
                                    "clinician for both sessions; a photograph of the room sent to the "
                                    "family beforehand.",
                "co_occurring": "Diagnosed: none besides ASD. Suspected and monitored: ADHD (Conners-4 "
                                "elevated for inattention on both parent and teacher forms) and anxiety "
                                "(SCARED elevated for separation and school avoidance). Chronic "
                                "sleep-onset difficulty and functional constipation are documented and "
                                "managed by paediatrics.",
                "sensory_profile": "Sound: hyperreactive - hand dryers, fire alarms and the cafeteria "
                                   "are the reliable triggers. Touch: hyperreactive to seams and tags, "
                                   "which are removed; seeks deep pressure and asks to be squeezed "
                                   "between cushions. Taste and smell: repertoire of about twelve foods, "
                                   "strongly texture-driven. Interoception and pain: reduced reactivity - "
                                   "he did not report a cut that needed stitches. Movement: seeks "
                                   "spinning and swinging when dysregulated.",
                "sensory_supports": "Ear defenders available without having to ask. A known quiet space "
                                    "he may leave for. Seating away from the door and the hand dryers. "
                                    "Deep pressure before transitions. Soft waistbands, no tags.",
                "communication_profile": "Fluent speech and a large vocabulary, which leads adults to "
                                         "overestimate how much he has taken in. Needs about ten seconds "
                                         "of processing time; repeating the question early resets that "
                                         "clock. Interprets language literally. Delayed echolalia of "
                                         "film dialogue is communicative, and often signals that he is "
                                         "at capacity.",
                "aac": "None required. Written instructions and a visual schedule act as his "
                       "communication supports.",
                "communication_preferences": "Say his name first, then wait. One instruction at a time, "
                                             "in the order it will happen. Count silently to ten before "
                                             "repeating. Ask him to say it back rather than asking "
                                             "whether he understood - he will say yes either way. Use "
                                             "literal words: 'in five minutes we stop', not 'in a little "
                                             "while'. Do not require eye contact; he listens better "
                                             "without it.",
                "regulation_profile": "Hand-flapping when excited and rocking when concentrating. Both "
                                      "are regulating and should not be interrupted. Dysregulated by "
                                      "unannounced change, noise, and being hurried. Recovers with "
                                      "quiet, deep pressure and his subway maps.",
                "meltdown_shutdown": "The build-up is visible for several minutes: he goes quiet, stops "
                                     "answering, then covers his ears. If the demand continues he leaves "
                                     "the room, which the school has recorded as absconding. This is "
                                     "escape from sensory overload, not defiance. Afterwards he is "
                                     "exhausted and apologetic, and needs recovery rather than "
                                     "consequences.",
                "distress_signs": "Going quiet and still is the first sign, not compliance. He rarely "
                                  "reports pain; a sudden behaviour change has twice turned out to be "
                                  "physical - an ear infection, and constipation.",
                "masking": "Holds himself together across the school day and releases at home. Teachers "
                           "describe a child with no difficulties; his mother describes ninety minutes "
                           "of recovery every afternoon. Both accounts are accurate.",
                "burnout": "No full burnout episode. The second half of the autumn term saw reduced "
                           "tolerance and more frequent leaving of the classroom, following a period of "
                           "timetable changes.",
                "executive_daily": "Needs a visual sequence for morning routines. Transitions between "
                                   "activities are harder than the activities. Multi-step written tasks "
                                   "stall at step one unless numbered.",
                "special_interests": "The city subway network in extraordinary detail - lines, "
                                     "interchanges, rolling stock, historical closures. A genuine "
                                     "strength, a regulation support, and the most reliable way into "
                                     "engagement for reading and mathematics.",
                "support_needs": "In his mother's words, and his where he offered them: 'knowing what is "
                                 "going to happen', 'somewhere quiet at lunch', 'people not getting cross "
                                 "when he goes quiet', and help with writing.",
                "elopement": "Leaves the classroom during unannounced fire drills; twice this term. He "
                             "goes to a predictable place - the library corridor - and can be found "
                             "quickly. He does not leave the building and does seek a familiar adult. An "
                             "agreed exit plan with a named adult is in place.",
                "self_injury": "None. No head-banging, biting or scratching at home or school.",
                "si_ideation": "None",
                "risk_level": "Not applicable at this age",
                "risk_rationale": "No suicidal ideation, self-injury or intent at age 8 on direct enquiry "
                                  "with the child and his mother. Recorded because autistic children are "
                                  "screened as they grow, not because concern exists today.",
                "restraint_history": "No restraint or seclusion in school or healthcare settings. The "
                                     "family does not consent to physical intervention and this is "
                                     "documented in the school record.",
                "overshadowing": "Two findings warrant assessment in their own right rather than being "
                                 "attributed to autism: the inattention elevated on both Conners-4 forms, "
                                 "and the sleep-onset difficulty. Both to be reassessed in six months "
                                 "once supports are in place.",
                "process_note": "Mother was tearful at the feedback session but said the word 'relief' "
                                "three times. Father did not attend either session; she says he is 'not "
                                "sure about labels'. Worth offering him a separate appointment.",
            }},
        ],
        "authorizations": [
            {"recipient_name": "Brookline Elementary School - Student Services",
             "recipient_type": "School / educational team", "scopes": [],
             "purpose": "Educational planning and eligibility determination",
             "signed_date": _d(28), "expires_date": _d(-337)},
        ],
    },
    {
        "mrn": "MRN-00103",
        "tags": ["Neurodevelopmental", "Adult ADHD"],
        "demographics": {
            "first_name": "Priya", "last_name": "Raghavan", "preferred_name": "",
            "dob": "1998-11-03", "pronouns": "she/her", "sex_at_birth": "Female",
            "phone": "(555) 448-1120", "email": "p.raghavan@example.com",
            "address": "301 Vine Street Apt 12, Springfield", "preferred_language": "English",
            "emergency_contact": {"name": "Arun Raghavan (brother)", "phone": "(555) 448-2231"},
            "insurance": {"carrier": "Meridian PPO", "member_id": "MP-2299471", "group_number": "GRP-5510"},
            "employer": "Halversen Logistics - operations coordinator",
        },
        "evaluations": [
            {"form_id": "adhd_eval", "encounter_date": _d(17), "sign": True, "answers": {
                "encounter_date": _d(17),
                "referral_source": "Self-referred after a workplace performance conversation; her "
                                   "primary care physician supported the referral.",
                "informants": "Patient. Mother interviewed by telephone with consent regarding childhood "
                              "symptoms. Two elementary school report cards from ages 8 and 10 reviewed, "
                              "both noting 'careless errors' and 'difficulty staying on task'. Current "
                              "supervisor's written performance feedback provided by the patient.",
                "inattentive_count": "8",
                "inattentive_detail": "Careless errors in shipment paperwork most weeks; difficulty "
                                      "sustaining attention in meetings longer than 20 minutes; appears "
                                      "not to listen when spoken to directly, reported by both her "
                                      "partner and her supervisor; fails to finish tasks, with three "
                                      "half-completed projects on her desk; difficulty organising, with a "
                                      "system she rebuilds every few weeks; avoids tasks requiring "
                                      "sustained mental effort, particularly quarterly reconciliation; "
                                      "loses keys, badge and phone frequently; easily distracted by "
                                      "background conversation.",
                "hyperactive_count": "3",
                "hyperactive_detail": "Fidgets constantly with pens and hair ties; feels restless and "
                                      "unable to sit through a film; talks over others in meetings and "
                                      "then apologises.",
                "onset_before_12": "Yes",
                "two_settings": "Yes",
                "impairment": "Placed on a documented performance improvement plan two months ago after "
                              "three shipment errors. Has been late with rent twice this year through "
                              "disorganisation rather than shortage of funds. Reports two hours of unpaid "
                              "overtime most days to complete work others finish within hours.",
                "not_better_explained": "Symptoms are not better explained by a mood, anxiety, psychotic "
                                        "or substance use disorder. PHQ-9 of 6 and GAD-7 of 7 do not "
                                        "reach clinical thresholds, and the attentional difficulties "
                                        "long predate any mood symptoms. Sleep is adequate at 7 hours "
                                        "with no snoring. TSH and CBC normal within three months.",
                "presentation": "Predominantly inattentive",
                "severity": "Moderate",
                "vanderbilt": "Not applicable (adult presentation).",
                "conners": "CAARS self-report: Inattention/Memory Problems T 78, Hyperactivity/Restlessness "
                           "T 61, Impulsivity/Emotional Lability T 58, DSM-5 Inattentive Symptoms T 76. "
                           "Observer form completed by her partner: Inattention T 72.",
                "asrs": "ASRS-5 score 20 of 24, above the screening threshold of 14.",
                "cognitive_testing": "Not required for diagnosis. Brief screening showed intact "
                                     "orientation, language and recall.",
                "academic": "Completed an associate degree with reported difficulty; no formal learning "
                            "disorder evaluation has been done. Reading and arithmetic screening within "
                            "normal limits.",
                "medical_history": "No head injury, seizures or thyroid disease. Sleep 7 hours nightly "
                                   "with no snoring or witnessed apnoea. Hearing and vision normal.",
                "cardiac_screen": "No personal history of structural heart disease, arrhythmia, syncope "
                                  "or exertional chest pain. No family history of sudden cardiac death "
                                  "under 40 or of inherited cardiomyopathy. Baseline BP 118/74, HR 72. "
                                  "ECG not indicated by current guidance in the absence of red flags.",
                "substance_screen": "Alcohol: 1-2 drinks weekly, AUDIT-C 2. No cannabis or other "
                                    "substances. No history of stimulant misuse. Diversion risk "
                                    "discussed: she lives with a partner, no household members with a "
                                    "substance use disorder, and she agreed to a lockable storage box.",
                "baseline_vitals": "Height 163 cm, weight 64 kg, BP 118/74, HR 72.",
                "phq9": "6", "gad7": "7", "audit_c": "2",
                "other_measures": "WFIRS-S (functional impairment) elevated in the work and "
                                  "self-concept domains.",
                "differential": "Considered: major depressive disorder (PHQ-9 6; attentional symptoms "
                                "predate and persist independently of mood), generalised anxiety "
                                "disorder (GAD-7 7; worry is consequence rather than cause of the "
                                "performance problems), sleep-disordered breathing (no snoring, adequate "
                                "sleep duration, no daytime sleepiness on Epworth), substance-related "
                                "impairment (minimal use), thyroid disease (TSH normal), and a specific "
                                "learning disorder (screening within normal limits, though further "
                                "assessment could be considered if impairment persists after treatment).",
                "dsm_diagnoses": "F90.0 Attention-deficit/hyperactivity disorder, predominantly "
                                 "inattentive presentation, moderate",
                "summary": "Ms. Raghavan meets DSM-5-TR criteria for attention-deficit/hyperactivity "
                           "disorder, predominantly inattentive presentation, of moderate severity. "
                           "Eight of nine inattentive criteria are endorsed, with three "
                           "hyperactive-impulsive criteria. Onset before age 12 is corroborated by "
                           "maternal interview and by school reports from ages 8 and 10. Symptoms are "
                           "present at work and at home, and produce documented occupational impairment "
                           "including a current performance improvement plan.",
                "treatment_plan": "1. Begin a long-acting methylphenidate preparation at a low starting "
                                  "dose with weekly review, titrating to effect against a repeated "
                                  "CAARS and functional measures. Baseline height, weight, blood "
                                  "pressure and pulse recorded above.\n"
                                  "2. Controlled-substance agreement signed; single prescriber and "
                                  "single pharmacy; lockable storage.\n"
                                  "3. ADHD-focused skills coaching: externalised task capture, one "
                                  "system rather than several, time-blocking for reconciliation work.\n"
                                  "4. Workplace accommodations letter to be provided at her request.\n"
                                  "5. Review in 2 weeks, then monthly during titration.",
                "recommendations_school": "Written rather than verbal instructions for multi-step tasks, "
                                          "or a written follow-up to verbal instruction.\n"
                                          "A quiet workspace or noise-cancelling headphones for "
                                          "reconciliation and paperwork tasks.\n"
                                          "Scheduled uninterrupted blocks for detail work, with meetings "
                                          "grouped rather than scattered.\n"
                                          "Deadlines broken into checkpoints with brief written "
                                          "confirmation at each.\n"
                                          "Permission to use timers and to take short movement breaks "
                                          "between sustained tasks.",
                "monitoring": "Blood pressure, pulse and weight at each titration visit. Sleep and "
                              "appetite reviewed at each visit. CAARS repeated at 8 weeks. Any chest "
                              "pain, syncope or palpitations to prompt immediate reassessment and ECG.",
            }},
        ],
        "authorizations": [],
    },
    {
        "mrn": "MRN-00104",
        "tags": ["Mood disorders", "Co-occurring SUD", "High acuity"],
        "demographics": {
            "first_name": "Thomas", "last_name": "Whitfield", "preferred_name": "Tom",
            "dob": "1974-07-22", "pronouns": "he/him", "sex_at_birth": "Male",
            "phone": "(555) 902-3318", "email": "t.whitfield@example.com",
            "address": "77 Kestrel Lane, Springfield", "preferred_language": "English",
            "emergency_contact": {"name": "Denise Whitfield (wife)", "phone": "(555) 902-3319"},
            "insurance": {"carrier": "Northstar Health", "member_id": "NH-8820344", "group_number": "GRP-1109"},
        },
        "evaluations": [
            {"form_id": "adult_initial", "encounter_date": _d(9), "sign": False, "answers": {
                "encounter_date": _d(9),
                "encounter_setting": "Outpatient clinic",
                "encounter_duration": "75",
                "informants": "Patient, and his wife Denise with his consent for the final 20 minutes. "
                              "Discharge summary from Mercy General (psychiatric admission 14 months ago) "
                              "reviewed.",
                "interpreter": "No",
                "chief_complaint": "I went three nights without sleeping and spent money we don't have, "
                                   "and now I've crashed.",
                "hpi": "Mr. Whitfield is a 51-year-old contractor with bipolar I disorder, presenting "
                       "eight days into a depressive episode that followed a four-week period of "
                       "elevated mood. During that period he slept three to four hours nightly without "
                       "fatigue, took on two additional contracts, spent approximately $14,000 on "
                       "equipment his wife describes as unnecessary, and spoke rapidly enough that "
                       "colleagues commented. He stopped lithium about seven weeks ago because it made "
                       "him feel 'flat and slow'. Over the past eight days his mood has dropped sharply: "
                       "he is sleeping 12 hours and still exhausted, has withdrawn from work, and "
                       "describes intrusive thoughts that his family would be better off without him. He "
                       "has resumed daily alcohol use over the past three weeks.",
                "symptom_review": "Mood: current depression with hypersomnia, anergia, guilt and "
                                  "hopelessness, following a clear four-week manic episode with reduced "
                                  "need for sleep, grandiosity about business prospects, increased "
                                  "goal-directed activity and financially damaging impulsivity. Anxiety: "
                                  "situational. Psychosis: during the manic period he believed briefly "
                                  "that a competitor was tracking his vehicle; this resolved with the "
                                  "mood shift. No current hallucinations or delusions.",
                "sleep": "Currently 11-12 hours with unrefreshing sleep and daytime napping. During the "
                         "manic period, 3-4 hours nightly without fatigue.",
                "appetite_weight": "Appetite increased over the past week with 3 kg weight gain.",
                "prior_diagnoses": "Bipolar I disorder (diagnosed 2011). Alcohol use disorder, moderate.",
                "prior_treatment": "One psychiatric admission 14 months ago, seven days, for a manic "
                                   "episode with psychotic features. No ECT. Engaged intermittently with "
                                   "outpatient care; three no-shows in the last year.",
                "medication_trials": "Lithium carbonate 900 mg nightly (2011-present, intermittently "
                                     "adherent): effective for mania prophylaxis when levels were "
                                     "therapeutic (0.8 mmol/L); self-discontinued seven weeks ago citing "
                                     "cognitive dulling and tremor. Quetiapine 300 mg (2023): effective "
                                     "acutely, stopped for sedation and weight gain. Valproate (2015): "
                                     "stopped after transaminase elevation.",
                "psychotherapy_history": "Eight sessions of individual therapy in 2023, discontinued.",
                "adherence": "Partial. Discontinues mood stabilisers when euthymic or when side effects "
                             "emerge, without contacting the clinic. Identifies cognitive side effects "
                             "and the sense of losing his 'edge' at work as the main barriers.",
                "alcohol": "Three weeks of daily use, approximately 8-10 standard drinks per day, "
                           "increasing over the last week. Longstanding pattern of heavy use during mood "
                           "episodes with periods of abstinence between. Two prior withdrawal episodes "
                           "with tremor and sweating, no seizures and no delirium tremens. Last drink 14 "
                           "hours before this appointment. CIWA-Ar 6 at intake. AUDIT-C 9.",
                "tobacco": "Half a pack of cigarettes daily for 25 years. Interested in cessation but "
                           "not at present.",
                "cannabis": "Occasional, roughly monthly.",
                "stimulants_opioids": "No use of stimulants, opioids or other substances. No injection "
                                      "drug use.",
                "rx_misuse": "No misuse of prescribed or over-the-counter medications.",
                "sud_treatment": "One outpatient alcohol programme in 2019, completed, followed by "
                                 "14 months of abstinence. No residential treatment.",
                "tox_screen": "Urine drug screen negative for all substances tested. Breath alcohol 0.00 "
                              "at the time of the visit. GGT 88 U/L, AST 52 U/L, ALT 44 U/L, MCV 98 fL.",
                "medical_conditions": "Hypertension, treated. Hepatic steatosis on ultrasound 2024.",
                "current_medications": "Lisinopril 10 mg daily. No psychotropic medication at present.",
                "allergies": "No known drug allergies.",
                "surgical_neuro": "No head injury, no seizures. Rotator cuff repair 2018.",
                "vitals_labs": "BP 138/88, HR 84, weight 96 kg, BMI 29.6. Lithium level not obtained "
                               "(off medication seven weeks). Creatinine 0.9 mg/dL, eGFR >90, TSH 2.4 "
                               "mIU/L. LFTs as above. ECG: normal sinus rhythm, QTc 418 ms.",
                "ros": "Mild tremor. No chest pain, palpitations, or focal neurological symptoms.",
                "family_psych_history": "Father with bipolar disorder and alcohol dependence, died at 58. "
                                        "Paternal grandmother with 'nervous breakdowns' requiring "
                                        "hospitalisation.",
                "developmental": "Unremarkable.",
                "education_work": "High school, then apprenticeship. Self-employed contractor for 20 "
                                  "years, employing four people. Business currently at risk after the "
                                  "recent spending.",
                "relationships": "Married 19 years; wife Denise is engaged and supportive but describes "
                                 "herself as 'running out'. Two children aged 14 and 17 at home.",
                "trauma_history": "Witnessed his father's psychiatric crises through childhood, "
                                  "including a police involvement he found frightening. No physical or "
                                  "sexual abuse.",
                "legal": "No current legal involvement. One DUI in 2009, licence restored.",
                "firearms_home": "Two hunting rifles kept in the home, previously unlocked in a wardrobe.",
                "cultural": "Identifies work and providing for his family as the core of who he is; "
                            "views needing medication as a personal failure. Attends church "
                            "intermittently and finds it steadying.",
                "social_determinants": "Housing stable but the mortgage is at risk. Insured through his "
                                       "own business policy. Transport available.",
                "strengths": "Skilled and respected in his trade, deeply attached to his children, "
                             "responded well to lithium when at a therapeutic level, wife willing to be "
                             "involved in care.",
                "mse_appearance": "Casually dressed man appearing older than his stated age, "
                                  "unshaven, mildly tremulous, cooperative but slow to engage.",
                "mse_attitude": "Cooperative",
                "mse_motor": "Psychomotor retardation",
                "mse_speech": "Slow, low volume, increased latency.",
                "mse_mood": "\"Empty. Ashamed.\"",
                "mse_affect": "Restricted, dysphoric, tearful twice, congruent.",
                "mse_thought_process": "Linear and goal-directed",
                "mse_thought_content": "Guilt about the financial damage and about his children. "
                                       "Hopelessness about the business. Passive and at times active "
                                       "thoughts of suicide as described below. No delusions currently; "
                                       "the persecutory belief from the manic period has fully resolved "
                                       "and he now regards it as untrue.",
                "mse_perception": "No hallucinations.",
                "mse_cognition": "Alert and oriented x4. Attention reduced. Recall 2/3 at five minutes. "
                                 "No evidence of delirium; CIWA-Ar 6 with mild tremor only.",
                "mse_insight": "Fair",
                "mse_judgment": "Limited",
                "si_ideation": "Active with method, no intent",
                "si_plan": "Has thought about using one of his rifles. Has not written a note, has not "
                           "set a time, has taken no preparatory steps beyond the thought itself.",
                "si_intent": "Ambivalent",
                "si_means": "Two hunting rifles in the home. Means restriction discussed at length with "
                            "the patient and his wife together: both agreed that Denise will transfer "
                            "both rifles and the ammunition to his brother's house today and will "
                            "confirm by telephone to the clinic before 18:00. Alcohol as a disinhibiting "
                            "factor also discussed.",
                "si_history": "No prior suicide attempts. One episode of passive ideation during the "
                              "2011 depressive episode.",
                "hi_ideation": "None",
                "protective": "Strong attachment to his two children, wife actively engaged in care and "
                              "present today, past response to treatment, employed and skilled, "
                              "willingness to accept means restriction, faith community, agreed to "
                              "return in 48 hours.",
                "risk_level": "High",
                "risk_rationale": "Active suicidal ideation with a considered method and access to "
                                  "firearms, in the context of a post-manic depressive episode, "
                                  "escalating daily alcohol use, acute financial loss, shame, male sex, "
                                  "and a family history of psychiatric illness. Risk is mitigated by "
                                  "ambivalence rather than intent, absence of preparatory behaviour, an "
                                  "engaged spouse, immediate agreement to remove firearms, and "
                                  "willingness to return within 48 hours. He does not currently meet "
                                  "criteria for involuntary hospitalisation and voluntary admission was "
                                  "declined; the plan below reflects that.",
                "safety_plan": "Warning signs: drinking before midday, avoiding Denise, going to the "
                               "workshop alone at night. Internal coping: walking the dog, working in "
                               "the garage with the door open, calling his brother. Social contacts: "
                               "Denise (present at all times over the next 72 hours by agreement), "
                               "brother Ray. Professional contacts: clinic direct line during hours, 988 "
                               "after hours, Mercy General emergency department. Means restriction: both "
                               "rifles and ammunition removed to his brother's home today; alcohol in "
                               "the house removed by Denise. Reasons for living: his daughter's "
                               "graduation in June, his son's football season.",
                "duty_to_warn": "No identified third party at risk. No homicidal ideation. No duty to "
                                "warn arises.",
                "phq9": "22", "gad7": "14",
                "cssrs": "Positive: active ideation with method, without specific plan or intent "
                         "(category 3). Behaviour subscale negative.",
                "audit_c": "9", "dast10": "1", "mdq": "Positive (9 items, clustering, moderate problem)",
                "ymrs": "6 (currently depressed; peak estimated 28 during the recent episode)",
                "func_work_school": "Has not attended his own job sites for eight days; two contracts at "
                                    "risk and four employees without direction. Business finances "
                                    "materially damaged by the manic-phase spending.",
                "func_social": "Withdrawn from his wife and children; declines contact with his brother "
                               "out of shame.",
                "func_selfcare": "Not shaving or showering regularly. Eating irregularly. Sleeping 12 "
                                 "hours and napping.",
                "func_cognitive": "Cannot follow the paperwork for a bid he would normally complete in "
                                  "an hour. Attention and pace markedly reduced from baseline.",
                "func_impact_summary": "Severe impairment across occupational, social and self-care "
                                       "domains, with objective corroboration from an eight-day work "
                                       "absence and documented financial loss.",
                "formulation": "A 51-year-old man with bipolar I disorder and a moderate alcohol use "
                               "disorder, presenting in a depressive episode following an untreated "
                               "manic episode precipitated by self-discontinuation of lithium seven "
                               "weeks ago. Predisposing: strong family history, early exposure to a "
                               "parent's untreated illness, and a self-concept organised around being "
                               "the provider that makes medication feel like failure. Precipitating: "
                               "lithium discontinuation, then the financial and relational consequences "
                               "of the manic episode. Perpetuating: daily alcohol use, shame, sleep "
                               "disruption, business jeopardy, and access to firearms. Protective: an "
                               "engaged spouse, two children he is strongly attached to, a documented "
                               "past response to lithium at a therapeutic level, and his willingness "
                               "today to accept means restriction and rapid follow-up.",
                "differential": "Bipolar I disorder, current episode depressed, is the primary "
                                "diagnosis; the recent episode met full criteria for mania with "
                                "psychotic features by history. Substance-induced mood disorder was "
                                "considered: alcohol use is heavy but began after the mood shift and has "
                                "not been present during previous documented episodes at this severity. "
                                "Major depressive disorder is excluded by the clear manic history. "
                                "Hypothyroidism excluded (TSH 2.4). Delirium excluded on examination.",
                "dsm_diagnoses": "F31.4 Bipolar I disorder, current episode depressed, severe, without "
                                 "psychotic features\n"
                                 "F10.20 Alcohol use disorder, moderate\n"
                                 "F17.200 Nicotine dependence, cigarettes",
                "severity_specifiers": "Severe; with anxious distress; most recent manic episode with "
                                       "psychotic features (by history), currently in remission.",
                "treatment_plan": "1. Restart lithium carbonate 600 mg nightly, with a level, "
                                  "creatinine and TSH in five days; target 0.6-0.8 mmol/L given his "
                                  "sensitivity to cognitive effects, and address tremor with dose timing "
                                  "before considering a dose reduction.\n"
                                  "2. Quetiapine 50 mg nightly, titrating to 150-300 mg as tolerated, "
                                  "for the depressive episode and sleep, with metabolic monitoring at "
                                  "baseline, 12 weeks and annually.\n"
                                  "3. Alcohol: CIWA-Ar 6 with no history of seizure or delirium tremens; "
                                  "suitable for outpatient management. Thiamine 100 mg daily and folate. "
                                  "Naltrexone deferred until liver enzymes are rechecked in two weeks. "
                                  "Referred to the intensive outpatient co-occurring programme, "
                                  "assessment appointment in three days.\n"
                                  "4. Safety: firearms removed today as documented above, with "
                                  "telephone confirmation required before 18:00; alcohol removed from "
                                  "the home; wife present continuously for 72 hours; return visit in 48 "
                                  "hours; written safety plan given.\n"
                                  "5. Voluntary hospitalisation offered and declined; criteria for "
                                  "involuntary admission are not met at present. Threshold for "
                                  "re-evaluation made explicit to both.\n"
                                  "6. Wife given psychoeducation about post-manic depression and the "
                                  "specific signs that should prompt an emergency call.",
                "informed_consent": "Discussed lithium (renal and thyroid monitoring, toxicity signs, "
                                    "NSAID and dehydration interactions, teratogenicity not applicable), "
                                    "quetiapine (sedation, weight gain, metabolic effects, the class "
                                    "warning regarding elderly patients with dementia, which does not "
                                    "apply to him), the interaction between alcohol and both agents, and "
                                    "the alternative of hospitalisation. Both he and his wife asked "
                                    "questions, which were answered. He consented.",
                "capacity": "Intact",
                "prognosis": "Guarded in the short term given active ideation, firearm access now "
                             "mitigated, and daily alcohol use; fair over six months if lithium is "
                             "re-established at a therapeutic level and the co-occurring programme is "
                             "engaged, based on his documented response in 2011-2022.",
                "followup": "48 hours, then twice weekly for two weeks",
                "process_note": "He said 'my father did this to us and now I'm doing it to them' and "
                                "could not continue. That sentence is the treatment, if we can get to "
                                "it once he is safe.",
            }},
        ],
        "authorizations": [
            {"recipient_name": "Northstar Health - Behavioral Utilisation Review",
             "recipient_type": "Insurance company / utilisation review", "scopes": ["sud"],
             "purpose": "Prior authorisation for intensive outpatient co-occurring treatment",
             "signed_date": _d(8), "expires_date": _d(-357)},
            {"recipient_name": "Denise Whitfield (spouse)", "recipient_type": "Family member or caregiver",
             "scopes": ["risk", "sud"],
             "purpose": "Safety planning and involvement in care at the patient's request",
             "signed_date": _d(8), "expires_date": _d(-357)},
        ],
    },
    {
        "mrn": "MRN-00105",
        "tags": ["Autism", "Adult diagnosis", "Healthcare access"],
        "demographics": {
            "first_name": "Elena", "last_name": "Duarte", "preferred_name": "",
            "dob": "1997-03-22", "pronouns": "she/her", "sex_at_birth": "Female",
            "phone": "(555) 660-1188", "email": "e.duarte@example.com",
            "address": "12 Sefton Row, Springfield", "preferred_language": "English",
            "language_preference": "identity-first",
            "emergency_contact": {"name": "Tomas Ruiz (partner)", "phone": "(555) 660-1190"},
            "insurance": {"carrier": "Meridian PPO", "member_id": "MP-5583201", "group_number": "GRP-5510"},
            "employer": "Cadence Analytics - data engineer",
        },
        "evaluations": [
            {"form_id": "asd_eval", "encounter_date": _d(63), "sign": True, "answers": {
                "encounter_date": _d(63),
                "referral_source": "Self-referred. Her younger sister was diagnosed autistic last year, "
                                   "and Ms. Duarte recognised the description of herself. Referral was "
                                   "supported by her primary care physician after three months of sick "
                                   "leave that had been attributed to depression.",
                "informants": "Ms. Duarte, primary informant across three sessions. Her partner, with "
                              "her consent, for the final session. School reports from ages 7 and 11, "
                              "which she had kept. Her mother declined to take part, which is noted "
                              "because a developmental history from a caregiver was therefore "
                              "unavailable.",
                "chronological_age": "29 years",
                "adjustments_made": "Questions sent in writing a week ahead. Appointments at 08:00 in a "
                                    "room without overhead fluorescent lighting. Written follow-up after "
                                    "each session. She was told she did not need to make eye contact.",
                "milestones": "Motor and language milestones met on time by her own report and the "
                              "school records. Read fluently at four. No speech delay - a common reason "
                              "autistic girls are missed.",
                "language_dev": "No delay. Precocious vocabulary, described in a school report at age 7 "
                                "as 'talks like a small adult'.",
                "social_dev": "One intense friendship at a time throughout childhood, each ending "
                              "abruptly and without her understanding why. Played alongside rather than "
                              "with groups. Scripted conversations in advance from adolescence, a "
                              "strategy she still uses.",
                "rrb_history": "Lined up and catalogued objects as a child. Re-reads the same books "
                               "dozens of times. Has eaten the same lunch daily for six years. Distress "
                               "at unplanned change was labelled 'sensitive' rather than investigated.",
                "sensory_history": "Cut labels out of clothing from age five. Could not tolerate school "
                                   "assemblies. Covered her ears at hand dryers, which the school "
                                   "recorded as attention-seeking.",
                "school_history": "Academically strong throughout, which is the main reason no "
                                  "assessment was sought. Reports from ages 7 and 11 both note "
                                  "'daydreaming', 'oversensitive' and 'does not join in'. No special "
                                  "educational provision at any point.",
                "co_occurring": "Diagnosed: generalised anxiety disorder (2019). Irritable bowel "
                                "syndrome (2021). Hypermobility, under rheumatology. Chronic insomnia. "
                                "Marked alexithymia on interview - she identifies distress by physical "
                                "sensation rather than by emotion, which is relevant to how she will "
                                "report symptoms to any clinician.",
                "genetic_workup": "Not indicated. No dysmorphic features, no intellectual disability, "
                                  "no seizures.",
                "family_history": "Younger sister diagnosed autistic at 26. Father described by the "
                                  "family as 'exactly the same but never assessed'.",
                "ados_module": "Module 4",
                "ados_scores": "ADOS-2 Module 4: Social Affect 8, Restricted and Repetitive Behaviour 2, "
                               "overall 10, meeting the autism spectrum cut-off. Recorded with the "
                               "caveat that Module 4 under-identifies adults who have spent decades "
                               "learning to compensate; the score is a floor, not a ceiling.",
                "ados_observations": "Eye contact was present, evenly timed and visibly effortful - she "
                                     "later described counting to three before looking away. Gesture was "
                                     "sparse and not integrated with speech. She answered questions "
                                     "fully and asked none. Descriptions of relationships were accurate "
                                     "about events and thin about motive.",
                "adir": "Not administered. No caregiver was available to give a developmental history; "
                        "school reports from ages 7 and 11 were used instead and are quoted above.",
                "rating_scales": "SRS-2 self-report: total T-score 71. Partner-report SRS-2: T-score 68.",
                "adult_instruments": "RAADS-R 156 (cut-off 65). AQ 38 (cut-off 32). CAT-Q 142, with the "
                                     "compensation and masking subscales both in the top decile - the "
                                     "clearest single finding in this assessment.",
                "cognitive": "Not indicated. Degree-level education and current employment as a data "
                             "engineer.",
                "language_assessment": "Not indicated. Structural language intact; pragmatic difficulty "
                                       "reported and observed.",
                "adaptive": "Not formally administered. Functional interview: independent for work and "
                            "finances, significant difficulty with unscheduled demands, phone calls, "
                            "and self-care during high-demand periods.",
                "comorbid_screens": "PHQ-9 11, GAD-7 14. Both elevated, and both fell during the "
                                    "assessment period as demands reduced - which supports the "
                                    "formulation that they are secondary.",
                "a1": "Reduced social-emotional reciprocity, masked by preparation. Conversation is "
                      "sustained by rehearsed questions; she reports running scripts and monitoring her "
                      "own face throughout. She does not spontaneously share news, and describes "
                      "reciprocal small talk as 'a second job'.",
                "a2": "Nonverbal communication is learned rather than intuitive. Eye contact is timed "
                      "deliberately. Gesture is sparse. She reports being told she looks 'flat' or "
                      "'annoyed' when she is neither.",
                "a3": "Difficulty developing and maintaining relationships. A pattern of one intense "
                      "friendship at a time, each ending without her understanding the cause. She "
                      "maintains her relationship with her partner through explicit agreements about "
                      "routine and plans.",
                "a_met": "Yes",
                "b1": "Re-reads the same books repeatedly. Repetitive finger movements under the table "
                      "during the assessment, which she stopped when she noticed me looking - masking "
                      "observed in the room.",
                "b2": "Insistence on sameness: the same lunch for six years, the same route, the same "
                      "supermarket. Unplanned change produces immediate distress and a day of reduced "
                      "capacity afterwards.",
                "b3": "Deep, sustained interests in railway timetabling and in textile weaving, both "
                      "pursued to expert level.",
                "b4": "Hyperreactivity to fluorescent light, hand dryers and open-plan office noise. "
                      "Hyporeactivity to interoceptive signals - she does not notice hunger, thirst or "
                      "needing the bathroom until it is urgent, and did not recognise the onset of her "
                      "own burnout.",
                "b_count": "4",
                "c_onset": "Present from early childhood. School reports at ages 7 and 11 independently "
                           "record sensory sensitivity, not joining in, and being 'oversensitive'. "
                           "Absence of a caregiver history does not weaken this; the contemporaneous "
                           "documents are stronger evidence than recollection would have been.",
                "d_impairment": "Clinically significant. Three months of sick leave, a job now at risk, "
                                "withdrawal from all social contact outside her partner, and loss of "
                                "self-care during the burnout period.",
                "e_differential": "Not better explained by intellectual disability or global "
                                  "developmental delay. Neither is present.",
                "severity_social": "Level 1 - requiring support",
                "severity_rrb": "Level 1 - requiring support",
                "specifiers": "Without accompanying intellectual impairment, Without accompanying language impairment",
                "differential": "Social anxiety disorder was considered and does not account for the "
                                "sensory profile, the insistence on sameness, or the early school "
                                "records; her anxiety is about specific social consequences she has "
                                "learned to expect, and postdates the traits. Complex PTSD considered - "
                                "no trauma history meeting criterion A. ADHD considered and remains "
                                "possible; inattention is currently better explained by burnout and will "
                                "be reassessed. Depression is present and secondary, improving as "
                                "demands reduced without any change in the underlying profile. Borderline "
                                "personality disorder had been suggested by a previous clinician; the "
                                "stable sense of self, absence of interpersonal fear of abandonment, and "
                                "lifelong sensory and routine profile do not support it, and this "
                                "mislabelling is common in autistic women.",
                "dsm_diagnoses": "F84.0 Autism spectrum disorder, without accompanying intellectual "
                                 "impairment, without accompanying language impairment; requiring "
                                 "support (Level 1) for social communication and for restricted, "
                                 "repetitive behaviours\n"
                                 "F41.1 Generalized anxiety disorder",
                "summary": "Ms. Duarte is a 29-year-old autistic woman, diagnosed at 29 after a working "
                           "life spent compensating. The evidence converges: RAADS-R 156, AQ 38, CAT-Q "
                           "142 with masking in the top decile, ADOS-2 Module 4 above the spectrum "
                           "cut-off despite decades of practice at appearing otherwise, and school "
                           "reports from ages 7 and 11 describing the same child. Her anxiety, low mood "
                           "and insomnia are best understood as the cost of sustained masking rather "
                           "than as primary conditions, and the recent sick leave has the shape of "
                           "autistic burnout rather than a depressive episode. She does not need to "
                           "become less autistic; her environment needs to ask less of her "
                           "performance and more of her actual strengths.",
                "recommendations_clinical": "1. No medication change for autism, which medication does "
                                            "not treat. Continue sertraline for anxiety at the current "
                                            "dose and review against function rather than mood alone.\n"
                                            "2. Burnout recovery plan: reduced demand, protected "
                                            "recovery time, and no new commitments for eight weeks.\n"
                                            "3. Post-diagnostic support: a structured programme for "
                                            "adults diagnosed late, and a peer group of autistic adults.\n"
                                            "4. Workplace adjustments letter, provided.\n"
                                            "5. Healthcare communication passport, provided, after two "
                                            "episodes of care in which her pain was not recognised.\n"
                                            "6. Re-screen for ADHD once burnout has resolved.",
                "recommendations_family": "Her partner asked what helps. Give notice of change. Accept "
                                          "written communication on hard days. Understand that going "
                                          "quiet is depletion, not withdrawal from him. Protect the "
                                          "recovery time rather than filling it.",
                "recommendations_school": "For her employer: predictable hours, written instructions, a "
                                          "low-sensory workspace, and meetings with an agenda in "
                                          "advance. Detail in the adjustments letter.",
                "strengths": "Exceptional pattern recognition and precision, which is why her employer "
                             "values her. Honest, loyal, and entirely without pretence. Deep expertise "
                             "in two fields. Articulate about her own experience once given time to "
                             "prepare.",
                "special_interests": "Railway timetabling, and textile weaving, which she describes as "
                                     "the only activity that reliably quiets her.",
                "sensory_profile": "Sound: hyperreactive - open-plan office noise, hand dryers, "
                                   "overlapping conversation. Light: hyperreactive to fluorescent "
                                   "lighting, which triggers migraine. Touch: seams and labels "
                                   "intolerable. Interoception: hyporeactive - she does not register "
                                   "hunger, thirst or pain until they are severe. This is the single "
                                   "most important item for any clinician seeing her.",
                "sensory_supports": "Noise-cancelling headphones, worn most of the working day. Natural "
                                    "light or a desk lamp rather than overhead fluorescents. Same "
                                    "clothing repeated. Weighted blanket for recovery. Weaving.",
                "communication_profile": "Fluent and articulate in prepared contexts. Under pressure, or "
                                         "when tired, speech becomes effortful and she may lose it "
                                         "altogether for short periods - situational mutism, which she "
                                         "finds humiliating when treated as refusal. Strongly prefers "
                                         "written communication. Interprets questions literally and will "
                                         "answer the question asked rather than the one intended.",
                "aac": "None formally. Text and email are her functional AAC; a note on her phone is "
                       "used when speech is unavailable.",
                "communication_preferences": "Ask one question at a time and allow silence. Offer to "
                                             "take answers in writing, particularly if she has stopped "
                                             "speaking - that is not refusal. Say what will happen and "
                                             "in what order. Avoid 'how are you feeling?', which she "
                                             "cannot answer; ask about the body instead - sleep, "
                                             "appetite, pain, energy. Do not require eye contact. Send a "
                                             "written summary afterwards.",
                "regulation_profile": "Repetitive finger movements and weaving are regulating and should "
                                      "not be discouraged. Dysregulated by noise, unplanned change, "
                                      "phone calls and open-plan environments. Recovers with silence, "
                                      "darkness, weighted pressure and time alone.",
                "meltdown_shutdown": "Shutdown rather than meltdown: she becomes still, stops speaking "
                                     "and cannot initiate. Previously recorded as 'uncooperative' in a "
                                     "healthcare setting. The build-up is hours long and she can "
                                     "usually name it in writing if asked early.",
                "distress_signs": "Stillness and loss of speech, not agitation. Because she does not "
                                  "register pain reliably, a change in behaviour may be the only sign "
                                  "of a physical problem.",
                "masking": "CAT-Q 142, with compensation and masking in the top decile. Rehearses "
                           "conversations, mirrors others' expressions, and monitors her own face "
                           "continuously. She estimates the effort as equivalent to a second job, and "
                           "it is the direct cause of the burnout described below.",
                "burnout": "Three-month episode this year: exhaustion, loss of speech for periods, loss "
                           "of cooking and self-care skills she has had for a decade, and inability to "
                           "tolerate previously manageable noise. Preceded by an office move to "
                           "open-plan and a team restructure. Treated elsewhere as a depressive episode "
                           "and did not respond to an antidepressant increase; began to lift only when "
                           "demands were removed. Distinguishing this from depression is the single "
                           "most useful thing in this report for her future care.",
                "executive_daily": "Task initiation is the bottleneck, not ability. Phone calls are "
                                   "avoided entirely. Unscheduled demands derail a day. During burnout "
                                   "she lost cooking, laundry and appointment-keeping.",
                "support_needs": "In her own words: 'stop making me do the social part of the job', "
                                 "'somewhere to work that is not open-plan', 'let me answer in writing', "
                                 "and 'believe me about pain'.",
                "elopement": "Not applicable. No history of leaving unsafe.",
                "self_injury": "Skin picking on the hands during high-demand periods, to the point of "
                               "bleeding. Function is regulation and it is not suicidal in intent. She "
                               "asked that it be recorded accurately because a previous clinician "
                               "treated it as a suicide attempt.",
                "si_ideation": "Passive (wish to be dead)",
                "risk_level": "Moderate",
                "risk_rationale": "Passive ideation during the burnout period, without plan, intent or "
                                  "preparatory behaviour, and reducing as demands lifted. Chronic risk "
                                  "is elevated: autistic adults without intellectual disability have "
                                  "substantially higher rates of suicide than the general population, "
                                  "and her alexithymia means distress will be under-reported and may "
                                  "not look like distress. Protective: a stable relationship, work she "
                                  "values, her sister, and the relief of an explanation. Acute risk is "
                                  "currently moderate and falling.",
                "safety_plan": "Written rather than verbal, at her request, and kept in a note on her "
                               "phone. Warning signs: losing speech, skin picking, cancelling on her "
                               "sister. Internal coping: weaving, weighted blanket, dark room. Contacts: "
                               "partner Tomas, sister Ana - both told they can ask directly, and that "
                               "she will answer in writing. Professional: clinic line, 988. Means: no "
                               "firearms; medication held in weekly quantities by agreement during the "
                               "burnout period.",
                "restraint_history": "None.",
                "overshadowing": "Two years of abdominal pain were attributed to anxiety before IBS was "
                                 "diagnosed. A dental abscess was missed because she did not present as "
                                 "in pain. Any new physical symptom warrants the same investigation it "
                                 "would receive in a non-autistic patient - this is recorded because it "
                                 "has already gone wrong twice.",
                "reassessment": "6 months, or sooner at her request",
                "followup": "4 weeks",
                "process_note": "She cried once, at 'you have been doing all of this on purpose, every "
                                "day, since you were seven'. Not a question for today: how much of the "
                                "anxiety diagnosis was ever anxiety.",
            }},
            {"form_id": "asd_review", "encounter_date": _d(12), "sign": True, "answers": {
                "encounter_date": _d(12),
                "encounter_setting": "Telehealth",
                "informants": "Ms. Duarte, by video with camera off at her request, which is her "
                              "preference and not a sign of deterioration. Written notes sent by her "
                              "the evening before.",
                "adjustments_made": "Camera optional. Agenda sent in advance. Summary sent in writing "
                                    "afterwards.",
                "interval_history": "Seven weeks since the adjustments letter. She has returned to work "
                                    "at three days a week with a desk in the quiet room. Speech has not "
                                    "been lost since the move. She has resumed weaving and has seen her "
                                    "sister twice.",
                "supports_in_place": "Working: the quiet desk, written instructions, meetings with "
                                     "agendas, and the agreement that she may answer in writing. Not "
                                     "working: the 'buddy check-in' the employer added, which she "
                                     "experiences as another social demand - recommend it is dropped. "
                                     "Never implemented: the promised noise assessment of the open-plan "
                                     "area.",
                "demands_environment": "Phased return agreed to four days from next month. She has "
                                       "asked that it not go to five. I support that.",
                "burnout": "Substantially recovered. Cooking and laundry have returned. She describes "
                           "capacity at 'seventy percent of before, and before was not sustainable'.",
                "masking": "Reduced at work since disclosing to her manager, which she describes as the "
                           "single biggest change. Still high with clients.",
                "co_occurring": "GAD improved: GAD-7 down from 14 to 8. IBS stable. Insomnia improved "
                                "with a consistent wake time. ADHD re-screen deferred to the next "
                                "review now that burnout has lifted.",
                "medication_current": "Sertraline 100 mg daily, targeting anxiety, not autism. Judged "
                                      "against function - phone calls attempted, meetings attended - "
                                      "rather than mood score alone.",
                "side_effects": "None reported at this dose.",
                "sensory_profile": "Unchanged. The quiet desk has removed the main daily exposure.",
                "sensory_supports": "Headphones now needed only for client calls.",
                "communication_profile": "No episodes of situational mutism in seven weeks.",
                "communication_preferences": "Unchanged, and now documented with her employer.",
                "regulation_profile": "Weaving most evenings. Skin picking has stopped.",
                "meltdown_shutdown": "No shutdown since the desk move.",
                "executive_daily": "Task initiation remains the main difficulty; a written daily order "
                                   "of tasks from her manager has helped more than any clinical "
                                   "intervention.",
                "special_interests": "Weaving; has started teaching it to her sister.",
                "support_needs": "'Keep the quiet desk. Drop the buddy scheme. Do not push me to five "
                                 "days.'",
                "strengths": "Precision, honesty, expertise, and - her words - 'knowing why now'.",
                "self_injury": "Stopped.",
                "si_ideation": "None",
                "risk_level": "Low",
                "risk_rationale": "No ideation in seven weeks, burnout resolving, supports in place and "
                                  "working, relationships resumed. Chronic elevation remains and will be "
                                  "screened at each review, with the alexithymia in mind.",
                "safety_plan": "Reviewed, unchanged, still on her phone.",
                "overshadowing": "No new physical symptoms this interval.",
                "assessment": "Autistic burnout substantially resolved following environmental change "
                              "rather than medication change, which is the finding worth carrying "
                              "forward. Anxiety improved secondarily. The support plan is working where "
                              "it removed demand and failing where it added a social one.",
                "dsm_diagnoses": "F84.0 Autism spectrum disorder, Level 1 for social communication and "
                                 "for restricted, repetitive behaviours\n"
                                 "F41.1 Generalized anxiety disorder",
                "treatment_plan": "1. Keep the quiet desk permanently; this is the intervention that "
                                  "worked.\n"
                                  "2. Drop the buddy check-in scheme.\n"
                                  "3. Support a phased return to four days, not five.\n"
                                  "4. Chase the noise assessment that was agreed and never done.\n"
                                  "5. Continue sertraline unchanged.\n"
                                  "6. Re-screen for ADHD at the next review.",
                "recommendations_school": "Employer: make the quiet desk permanent rather than "
                                          "temporary, drop the buddy scheme, keep agendas in advance, "
                                          "and hold the return at four days.",
                "recommendations_family": "Her partner has asked for nothing further. Recovery time "
                                          "continues to be protected at home.",
                "followup": "3 months",
                "process_note": "She asked whether she should tell her mother. We left it open.",
            }},
        ],
        "authorizations": [
            {"recipient_name": "Cadence Analytics - People Team",
             "recipient_type": "Education or employment support service", "scopes": [],
             "purpose": "Reasonable adjustments in the workplace",
             "signed_date": _d(60), "expires_date": _d(-305)},
            {"recipient_name": "Tomas Ruiz (partner)", "recipient_type": "Family member or caregiver",
             "scopes": ["risk"],
             "purpose": "Involvement in care and safety planning at the patient's request",
             "signed_date": _d(60), "expires_date": _d(-305)},
        ],
    },
]

USERS = [
    ("dr.chen", "Demo!Pass1", "Dr. Amara Chen", "clinician", "MD", "1457893021"),
    ("dr.reyes", "Demo!Pass2", "Dr. Miguel Reyes", "supervisor", "MD, MPH", "1902334876"),
    ("frontdesk", "Demo!Pass3", "Sam Okonkwo", "staff", "", ""),
    ("compliance", "Demo!Pass4", "Priya Nair", "auditor", "CHC", ""),
]


def seed(store: Store) -> None:
    if store.one("SELECT id FROM users LIMIT 1"):
        return
    ids = {}
    for username, password, name, role, credentials, npi in USERS:
        ids[username] = auth.create_user(store, username, password, name, role, credentials, npi)
    clinician = {"id": ids["dr.chen"], "username": "dr.chen", "display_name": "Dr. Amara Chen",
                 "credentials": "MD", "npi": "1457893021", "role": "clinician"}

    for spec in PATIENTS:
        patient_id = store.insert_sealed("patients", {
            "mrn": spec["mrn"], "tags": json.dumps(spec["tags"]), "status": "active",
            "created_by": clinician["id"], "created_at": now(), "updated_at": now(),
        }, spec["demographics"])
        audit.log(store, clinician, "patient.create", "patient", patient_id, patient_id, "seed")
        for ev in spec["evaluations"]:
            eval_id = store.insert_sealed("evaluations", {
                "patient_id": patient_id, "form_id": ev["form_id"],
                "encounter_date": ev["encounter_date"], "status": "signed" if ev["sign"] else "draft",
                "created_by": clinician["id"],
                "signed_by": clinician["id"] if ev["sign"] else None,
                "signed_at": now() if ev["sign"] else None,
                "created_at": now(), "updated_at": now(),
            }, {"answers": ev["answers"]})
            audit.log(store, clinician, "evaluation.create", "evaluation", eval_id, patient_id,
                      ev["form_id"])
        for authorization in spec["authorizations"]:
            store.insert_sealed("authorizations", {
                "patient_id": patient_id, "recipient_type": authorization["recipient_type"],
                "scopes": json.dumps(authorization["scopes"]),
                "signed_date": authorization["signed_date"],
                "expires_date": authorization["expires_date"],
                "obtained_by": clinician["id"], "created_at": now(),
            }, {"recipient_name": authorization["recipient_name"],
                "purpose": authorization["purpose"]})
            audit.log(store, clinician, "authorization.create", "authorization", None, patient_id,
                      authorization["recipient_type"])

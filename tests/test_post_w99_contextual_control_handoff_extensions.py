import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PostW99ContextualControlHandoffExtensionIntegrationTests(unittest.TestCase):
    def test_wave45_open_editor_requires_unique_enabled_guardar_fecha(self):
        handoff = (ROOT / "web" / "contextual-control-handoff.js").read_text(encoding="utf-8")
        activity = (ROOT / "web" / "activity-reschedule-control.js").read_text(encoding="utf-8")
        wave45 = (ROOT / "web" / "followup-reschedule.js").read_text(encoding="utf-8")
        self.assertIn("function controlHandoffSingleGroup", handoff)
        self.assertIn("controls.length===0", handoff)
        self.assertIn("controls.length>1", handoff)
        self.assertIn("controls[0].disabled", handoff)
        self.assertIn("controlHandoffSingleGroup(editors,text=>text==='Guardar fecha'", activity)
        self.assertNotIn("controlHandoffSingle(editors,activityRescheduleMeta", activity)
        self.assertIn("Guardar fecha", wave45)
        self.assertIn("save.disabled=true", wave45)
        self.assertIn("save.disabled=false", wave45)

    def test_activity_extension_precedes_base_activity_fallback(self):
        handoff = (ROOT / "web" / "contextual-control-handoff.js").read_text(encoding="utf-8")
        activity = (ROOT / "web" / "activity-reschedule-control.js").read_text(encoding="utf-8")
        self.assertIn("targetKind==='ACTIVITY'&&kind==='crm_unscheduled'", handoff)
        self.assertIn("const activityRescheduleBaseResolveControl=globalThis.controlHandoffResolveControl", activity)
        self.assertIn("globalThis.controlHandoffResolveControl=function", activity)
        self.assertIn("crm_unscheduled", activity)
        self.assertIn("pipeline_unscheduled_followup", activity)
        self.assertIn("OPEN_WAVE45_RESCHEDULE", activity)
        self.assertIn("WAVE45_RESCHEDULE_EDITOR", activity)
        self.assertIn("return activityRescheduleBaseResolveControl.apply(this,arguments)", activity)

    def test_activity_decision_group_remains_two_human_choices(self):
        activity = (ROOT / "web" / "activity-reschedule-control.js").read_text(encoding="utf-8")
        self.assertIn("RESOLVE_EXISTING_ACTIVITY", activity)
        self.assertIn("Completar o reprogramar seguimiento", activity)
        self.assertIn("controlHandoffSingle(groups", activity)
        self.assertNotIn("controlHandoffSingleGroup(groups", activity)

    def test_w52_prepared_decision_requires_unique_enabled_canonical_submit(self):
        handoff = (ROOT / "web" / "contextual-control-handoff.js").read_text(encoding="utf-8")
        results = (ROOT / "web" / "campaign-results-owner-handoff.js").read_text(encoding="utf-8")
        learning = (ROOT / "web" / "learning-loop.js").read_text(encoding="utf-8")
        self.assertIn("function controlHandoffSingleGroup", handoff)
        self.assertIn("controlHandoffSingleGroup([form],text=>text==='Registrar decisión local'", results)
        self.assertNotIn("return controlHandoffSingle([form],campaignResultsOwnerMeta('W52_SUBMIT_CAMPAIGN_DECISION'", results)
        self.assertIn("Registrar decisión local", learning)
        self.assertIn("save.disabled=true", learning)
        self.assertIn("save.disabled=false", learning)

    def test_campaign_results_extension_preserves_exact_optional_ai_and_human_prepare(self):
        results = (ROOT / "web" / "campaign-results-owner-handoff.js").read_text(encoding="utf-8")
        self.assertIn("PREPARE_W52_CAMPAIGN_DECISION", results)
        self.assertIn("Preparar decisión para esta campaña", results)
        self.assertIn("W52_SUBMIT_CAMPAIGN_DECISION", results)
        self.assertIn("W65_OPTIONAL_AI", results)
        self.assertIn("Analizar con IA", results)
        self.assertNotIn("OPEN_INTELLIGENCE_NEXT_OWNER", results)
        self.assertIn("return campaignResultsOwnerBaseResolveControl.apply(this,arguments)", results)

    def test_base_hardening_preserves_exact_campaign_media_and_publication_semantics(self):
        handoff = (ROOT / "web" / "contextual-control-handoff.js").read_text(encoding="utf-8")
        for marker in (
            "DEFINE_CAMPAIGN_CHANNELS",
            "REQUEST_OPTIONAL_AI_ANALYSIS",
            "MANAGE_PUBLICATION_PANEL",
            "No se promueve un control destructivo",
            "El submit canónico está deshabilitado en el owner",
        ):
            self.assertIn(marker, handoff)

    def test_terminal_docs_include_all_owner_extensions_and_frozen_boundary(self):
        docs = (ROOT / "docs" / "POST_W99_CONTEXTUAL_CONTROL_HANDOFF.md").read_text(encoding="utf-8")
        dev = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text(encoding="utf-8")
        expected = (
            "Today → Execution Return → Contextual Deep Linking → Evidence Observability → "
            "Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → "
            "Existing Activity Reschedule Control → Campaign Results Owner Handoff"
        )
        self.assertIn(expected, docs)
        self.assertIn(expected, dev)
        self.assertIn("Guardar fecha", docs)
        self.assertIn("Registrar decisión local", docs)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("No constituye W100", docs)


if __name__ == "__main__":
    unittest.main()
